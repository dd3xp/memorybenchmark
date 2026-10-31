"""Concurrent fork equivalence, recovery, and non-destructive live handoff."""
from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from memorybenchmark.errors import InfrastructureError
from memorybenchmark.ga_runtime import copy_memory, memory_manifest
from memorybenchmark.prototypes.station_capability import load_design
from memorybenchmark.prototypes.station_parallel import reserve_handoff, release_handoff, resume_parallel
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN, StationSession
from memorybenchmark.watch import atomic_json as save_json


class ParallelStationTests(unittest.TestCase):
    def make_run(self, root):
        output = root / "pilot"
        (output / "baseline").mkdir(parents=True)
        (output / "baseline/native.txt").write_text("original native memory")
        (output / "sessions").mkdir()
        (output / "probe").mkdir()
        save_json(output / "probe/summary.json", {"infrastructure_ok": True})
        frozen = root / "frozen.py"
        frozen.write_text("# unchanged inner experiment\n")
        save_json(output / "design.json", load_design(DEFAULT_DESIGN))
        report = {"agent": "ga", "status": "running", "world": "omega_00", "tasks": ["T1", "T2", "T3"],
            "clear_first_task": True, "action_policy": "single", "movement_mode": "step", "game_access": "native",
            "feedback_mode": "compact", "model_alias": "fixture", "seed": 9,
            "max_turns": 100, "final_turns": 6, "wall_seconds": 3600,
            "implementation_sha256": {str(frozen): sha256(frozen.read_bytes()).hexdigest()}, "sessions": []}
        save_json(output / "pilot.json", report)
        return output

    def fixture(self, *, fail=None):
        calls, inputs, histories = [], {}, {}
        lock = threading.Lock()
        barrier = threading.Barrier(2)
        counters = {"active": 0, "peak": 0}
        class Sessions:
            parallel_tasks = {"T1", "T2", "T3"}
            def __init__(self, *args, **kwargs):
                pass
            def run(self, game, task, memory, output, model, *, condition):
                output.mkdir(parents=True, exist_ok=False)
                marker = memory / "learned.txt"
                before = memory_manifest(memory)
                save_json(output / "memory-before.json", before)
                save_json(output / "prior-events.json", game.events)
                with lock:
                    calls.append((task, condition))
                    inputs[task, condition] = marker.read_text() if marker.exists() else None
                    histories[task, condition] = json.dumps(game.events, sort_keys=True)
                    counters["active"] += 1
                    counters["peak"] = max(counters["peak"], counters["active"])
                if task in self.parallel_tasks:
                    barrier.wait(timeout=10)
                StationSession(game, task)
                walk(game, "B" if condition == "clear" else "A")
                game.step({"type": "inspect"})
                broken = (task, condition) == fail and calls.count((task, condition)) == 1
                if not broken:
                    game.step({"type": "abandon"})  # A valid game failure must never be retried.
                    copy_memory(memory, output / "memory-after")
                    (output / "memory-after/learned.txt").write_text(task + ":" + condition)
                report = {"task_id": task, "condition": condition, "infrastructure_ok": not broken,
                    "success": None if broken else False, "distance": game.distance, "llm_calls": 0,
                    "content_changed": ["learned.txt"], "infrastructure_error": "gateway_transport_error" if broken else None}
                save_json(output / "summary.json", report)
                (output / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in game.events), encoding="utf-8")
                with lock:
                    counters["active"] -= 1
                return report
        return Sessions, calls, inputs, histories, counters

    def test_pairs_overlap_and_only_retained_memory_and_history_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.make_run(Path(directory))
            fixture, calls, inputs, histories, counters = self.fixture()
            with patch("memorybenchmark.prototypes.station_parallel.StationNativeSessions", fixture), redirect_stdout(io.StringIO()):
                report = resume_parallel(output, None, None)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(counters["peak"], 2)
            self.assertEqual(len(calls), 6)
            self.assertEqual(inputs["T2", "retain"], "T1:prefix")
            self.assertEqual(inputs["T3", "retain"], "T2:retain")
            self.assertTrue(all(value is None for (task, condition), value in inputs.items() if condition == "clear"))
            self.assertTrue(all(histories[t, "clear"] == histories[t, "prefix" if t == "T1" else "retain"] for t in ("T1", "T2", "T3")))
            self.assertNotIn('"to": "B"', histories["T3", "retain"])
            self.assertEqual([r["name"] for r in report["sessions"]], ["01-T1-prefix", "01-T1-clear", "02-T2-retain", "02-T2-clear", "03-T3-retain", "03-T3-clear"])

    def test_transport_recovery_reuses_completed_peer_and_preserves_valid_game_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.make_run(Path(directory))
            fixture, calls, *_ = self.fixture(fail=("T2", "clear"))
            with patch("memorybenchmark.prototypes.station_parallel.StationNativeSessions", fixture), redirect_stdout(io.StringIO()):
                with self.assertRaises(InfrastructureError):
                    resume_parallel(output, None, None)
            completed = output / "sessions/02-T2-retain/summary.json"
            digest = sha256(completed.read_bytes()).hexdigest()
            # On retry only clear T2 needs to run; T3 still has both branches.
            class Recovery(fixture):
                parallel_tasks = {"T3"}
            with patch("memorybenchmark.prototypes.station_parallel.StationNativeSessions", Recovery), redirect_stdout(io.StringIO()):
                result = resume_parallel(output, None, None)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(calls.count(("T2", "retain")), 1)
            self.assertEqual(calls.count(("T2", "clear")), 2)
            self.assertEqual(sha256(completed.read_bytes()).hexdigest(), digest)
            self.assertEqual(len(result["attempt_history"]), 1)

    def test_handoff_blocks_only_next_unopened_session_and_refuses_to_remove_real_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.make_run(Path(directory))
            (output / "sessions/01-T1-prefix").mkdir()
            reservation = reserve_handoff(output)
            self.assertEqual(reservation["reserved_session"], "01-T1-clear")
            folder = output / "sessions/01-T1-clear"
            with self.assertRaises(FileExistsError):folder.mkdir(exist_ok=False)
            (folder / "real-worker-data.txt").write_text("preserve")
            with self.assertRaises(ValueError):release_handoff(output, reservation)
            (folder / "real-worker-data.txt").unlink()
            release_handoff(output, reservation)
            self.assertFalse(folder.exists())

    def test_source_mismatch_stops_before_any_branch_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.make_run(Path(directory))
            (Path(directory) / "frozen.py").write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "Frozen"):
                resume_parallel(output, None, None)
            self.assertEqual(list((output / "sessions").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
