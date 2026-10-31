"""Separate ownership, longitudinal histories, memory resets and bounded recovery."""
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
from memorybenchmark.ga_runtime import memory_manifest
from memorybenchmark.prototypes.station_independent import PROTOCOL, execute, experiment, ownership
from memorybenchmark.watch import atomic_json as save_json
from scripts.audit_station_native import audit
from tests import test_station_parallel as fixtures


class IndependentStationTests(unittest.TestCase):
    def make_run(self, root, condition):
        parent = root / condition
        parent.mkdir()
        output = fixtures.ParallelStationTests().make_run(parent)
        report = json.loads((output / "pilot.json").read_text())
        report.update(protocol=PROTOCOL, experiment_mode="independent", experiment_id=condition,
            memory_condition=condition, baseline_memory=memory_manifest(output / "baseline"),
            transport_retries=2, transport_failure_limit=8, attempt_history=[])
        save_json(output / "pilot.json", report)
        return output

    def fixture(self, **options):
        base, *rest = fixtures.ParallelStationTests().fixture(**options)
        class Sessions(base):
            parallel_tasks = set()
        return Sessions, *rest

    def test_each_condition_advances_its_own_history_and_only_retain_inherits_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retain, clear = (self.make_run(root, c) for c in ("retain", "clear"))
            fixture, calls, inputs, histories, _ = self.fixture()
            with patch("memorybenchmark.prototypes.station_independent.StationNativeSessions", fixture), redirect_stdout(io.StringIO()):
                for run in (retain, clear):
                    self.assertEqual(execute(run, None, None, retry_delay=0)["status"], "completed")
            self.assertEqual(len(calls), 6)
            self.assertEqual(inputs["T2", "retain"], "T1:retain")
            self.assertEqual(inputs["T3", "retain"], "T2:retain")
            self.assertTrue(all(v is None for (t, c), v in inputs.items() if c == "clear"))
            self.assertNotEqual(histories["T2", "clear"], histories["T2", "retain"])
            self.assertIn('"to": "B"', histories["T3", "clear"])
            self.assertNotIn('"to": "A"', histories["T3", "clear"])
            # Every fixture abandons its task. These valid game failures still
            # advance each run, never trigger another execution, and audit alone.
            for run in (retain, clear):
                p = json.loads((run / "pilot.json").read_text())
                self.assertEqual(len(p["sessions"]), 3)
                for row in p["sessions"]:
                    folder = run / "sessions" / row["name"]
                    summary = json.loads((folder / "summary.json").read_text())
                    summary["session_id"] = row["name"]
                    summary["initial_session"]["native_tool_registry_unchanged"] = True
                    save_json(folder / "summary.json", summary)
                result = audit(run)
                self.assertEqual(result["canonical_tasks"], 3)
                self.assertEqual(result["sessions"], 3)

    def test_stalled_peer_does_not_block_another_run_finishing_all_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retain, clear = (self.make_run(root, c) for c in ("retain", "clear"))
            fixture, *_ = self.fixture()
            entered, release = threading.Event(), threading.Event()
            errors = []
            class Slow(fixture):
                def run(self, *args, **kwargs):
                    if kwargs["condition"] == "retain":
                        entered.set()
                        if not release.wait(timeout=15):
                            raise RuntimeError("fixture timed out")
                    return super().run(*args, **kwargs)
            def background():
                try:
                    experiment(retain, None, None, resume=True)
                except BaseException as error:
                    errors.append(error)
            with patch("memorybenchmark.prototypes.station_independent.StationNativeSessions", Slow), redirect_stdout(io.StringIO()):
                worker = threading.Thread(target=background)
                worker.start()
                try:
                    self.assertTrue(entered.wait(timeout=5))
                    result = experiment(clear, None, None, resume=True)
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(len(result["sessions"]), 3)
                    p = json.loads((retain / "pilot.json").read_text())
                    self.assertEqual(len(p["sessions"]), 0)
                finally:
                    release.set()
                    worker.join(timeout=15)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def test_failure_and_retry_touch_only_this_run_and_reuse_saved_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retain, clear = (self.make_run(root, c) for c in ("retain", "clear"))
            peer_digest = sha256((retain / "pilot.json").read_bytes()).hexdigest()
            fixture, calls, *_ = self.fixture(fail=("T2", "clear"))
            with patch("memorybenchmark.prototypes.station_independent.StationNativeSessions", fixture), redirect_stdout(io.StringIO()):
                result = execute(clear, None, None, retry_delay=0)
                self.assertEqual(len(result["attempt_history"]), 1)
                self.assertEqual(calls.count(("T2", "clear")), 2)
                self.assertEqual(calls.count(("T1", "clear")), 1)
                count = len(calls)
                result["status"] = "interrupted"
                result["sessions"].pop()  # Simulate a host crash before registration.
                save_json(clear / "pilot.json", result)
                self.assertEqual(execute(clear, None, None, retry_delay=0)["status"], "completed")
                self.assertEqual(len(calls), count)
            self.assertEqual(sha256((retain / "pilot.json").read_bytes()).hexdigest(), peer_digest)

    def test_retry_budget_is_not_reset_by_resume_and_other_run_can_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            retain, clear = (self.make_run(root, c) for c in ("retain", "clear"))
            fixture, calls, *_ = self.fixture(fail=("T1", "retain"))
            class AlwaysFail(fixture):
                def run(self, *args, **kwargs):
                    # Reuse first-attempt fixture on each retry.
                    if kwargs["condition"] == "retain":
                        calls[:] = [c for c in calls if c != ("T1", "retain")]
                    return super().run(*args, **kwargs)
            with patch("memorybenchmark.prototypes.station_independent.StationNativeSessions", AlwaysFail), redirect_stdout(io.StringIO()):
                for attempt in range(2):
                    with self.assertRaisesRegex(InfrastructureError, "retry budget"):
                        execute(retain, None, None, retry_delay=0)
                p = json.loads((retain / "pilot.json").read_text())
                self.assertEqual(len(p["attempt_history"]), 2)
                self.assertEqual(execute(clear, None, None, retry_delay=0)["status"], "completed")

    def test_ownership_is_per_run_and_duplicate_owner_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = (Path(directory) / name for name in ("a", "b"))
            with ownership(a), ownership(b):
                with self.assertRaisesRegex(RuntimeError, "already has an owner"):
                    with ownership(a):
                        self.fail("duplicate owner acquired lock")
            with ownership(a):
                pass

    def test_paired_data_cannot_be_relabelled_as_an_independent_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = fixtures.ParallelStationTests().make_run(Path(directory))
            with self.assertRaisesRegex(ValueError, "paired"):
                execute(output, None, None)

    def test_condition_and_budgets_cannot_change_when_resuming(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.make_run(Path(directory), "clear")
            for options in ({"condition": "retain"}, {"max_turns": 1}, {"agent": "hermes"}, {"unexpected_option": True}):
                with self.assertRaisesRegex(ValueError, "configuration"):
                    experiment(output, None, None, resume=True, **options)


if __name__ == "__main__":
    unittest.main()
