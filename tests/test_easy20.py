"""Map feasibility, real evidence boundaries and human adapter lifecycle."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.game import ProtocolError
from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design, map_world
from memorybenchmark.prototypes.station_routes import feedback_policy, schedule, walk
from memorybenchmark.prototypes.station_session import EASY20_DESIGN, StationSession


class Easy20Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(EASY20_DESIGN)

    def test_sparse_map_and_interleaved_commissions_have_long_and_short_reuse_gaps(self):
        d = self.design
        self.assertEqual((len(d["tasks"]), len(d["public"]["locations"]), len(d["public"]["edges"])), (20, 22, 21))
        self.assertEqual(len(d["private_worlds"]), 16)
        rows = schedule(d)
        self.assertEqual({g: sum(r["group"] == g for r in rows) for g in d["public"]["capability_groups"]}, {"AB": 5, "DE": 5, "FG": 5, "HK": 5})
        self.assertEqual(next(r for r in rows if r["id"] == "T17")["intervening_tasks_since_same_group"], 8)
        self.assertTrue(any(r["intervening_tasks_since_same_group"] == 1 for r in rows))

    def test_twenty_tasks_complete_in_every_assignment_with_or_without_past_feedback(self):
        for world in self.design["private_worlds"]:
            for retain in (True, False):
                game = StationGame(world, self.design)
                for task in self.design["tasks"]:
                    game.start_task(task); feedback_policy(game, retain_history=retain)
                    self.assertTrue(game.state.success)
                    self.assertLessEqual(game.steps, 13)
                    self.assertIn(game.distance, (10, 14))

    def test_free_exploration_can_reveal_another_groups_fact_before_its_commission(self):
        game = StationGame("omega_1111", self.design)
        game.start_task("T1");walk(game, "D");game.step({"type": "inspect"});feedback_policy(game)
        self.assertTrue(game.state.success)
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 4)
        self.assertLessEqual(game.steps, 18)
        next_task = StationSession(game, "T2")
        self.assertEqual(next_task.initial["feedback"], {"kind": "started"})
        self.assertNotIn("private_worlds", json.dumps(next_task.initial))
        self.assertNotIn("T20", json.dumps(next_task.initial))
        for command in ("design", "next_task", "world"):
            self.assertIn("error", next_task.dispatch({"command": command}))

    def test_failed_task_only_confers_information_actually_delivered(self):
        game = StationGame("omega_1010", self.design)
        game.start_task("T1");game.step({"type": "abandon"})
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 16)
        game.start_task("T3");walk(game, "A");game.step({"type": "inspect"});game.step({"type": "abandon"})
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 8)
        game.start_task("T8");feedback_policy(game)
        self.assertEqual(game.distance, 10)

    def test_native_runner_selects_twenty_tasks_and_forks_only_clear_probes(self):
        from memorybenchmark.ga_runtime import copy_memory
        from memorybenchmark.prototypes.station_pilot import pilot
        starts = []
        inputs = []
        class ScriptedSessionFixture:
            def __init__(self, *args, **kwargs):pass
            def probe(self, baseline, output):
                output.mkdir(); (output / "summary.json").write_text("{}")
            def run(self, game, task, memory, output, model, *, condition):
                output.mkdir(parents=True)
                marker = memory / "fixture-experience.txt"
                inputs.append(marker.read_text() if marker.exists() else None)
                session = StationSession(game, task)
                starts.append((task, condition, session.initial["observation"]["steps"]))
                feedback_policy(game, retain_history=condition != "clear")
                copy_memory(memory, output / "memory-after")
                (output / "memory-after/fixture-experience.txt").write_text(task + ":" + condition)
                result = {"task_id":task,"success":game.state.success,"distance":game.distance,
                          "llm_calls":0,"content_changed":[],"infrastructure_ok":True}
                (output / "summary.json").write_text(json.dumps(result))
                (output / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in game.events))
                return result
        def source_fixture(archive, destination):
            source = destination / "GenericAgent"; (source / "memory").mkdir(parents=True)
            return source
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / "fixture.tar"; archive.write_bytes(b"scripted fixture")
            with patch("memorybenchmark.prototypes.station_pilot.extract_native", source_fixture), \
                 patch("memorybenchmark.prototypes.station_pilot.make_support", lambda p:p.mkdir()), \
                 patch("memorybenchmark.prototypes.station_pilot.StationNativeSessions", ScriptedSessionFixture), \
                 redirect_stdout(io.StringIO()):
                report = pilot(archive, root / "pilot", None, None, design_path=EASY20_DESIGN)
            self.assertEqual(report["design_id"], self.design["design_id"])
            self.assertEqual(report["world"], map_world(self.design))
            self.assertEqual(report["world_sampling"], "fixed map assignment; no runtime sampling")
            self.assertEqual(len(report["map_configuration_sha256"]), 64)
            self.assertEqual(len(report["station_assignment_sha256"]), 64)
            self.assertEqual(report["tasks"], list(self.design["tasks"]))
            self.assertEqual(len(report["sessions"]), 40)
            self.assertTrue(report["clear_first_task"])
            self.assertEqual(starts[:2], [('T1','prefix',0),('T1','clear',0)])
            self.assertEqual(inputs[:4], [None, None, 'T1:prefix', None])
            self.assertTrue(all(row["success"] for row in report["sessions"]))
            self.assertTrue(all(steps == 0 for _, _, steps in starts))
            self.assertEqual(starts[-2:],[('T20','retain',0),('T20','clear',0)])

    def test_human_design_view_is_explicit_read_only_and_advance_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FieldService(Path(directory), self.design)
            data = service.start({}); token = data["instance_id"]
            self.assertNotIn("capabilities", data)
            self.assertNotIn("private_worlds", json.dumps(data))
            game = service.instances[token]["game"]
            before = deepcopy(game.events)
            view = service.design_view(token)
            self.assertEqual(len(view["tasks"]), 20)
            self.assertEqual(len(view["triggers"]), 8)
            self.assertEqual(game.events, before)
            with self.assertRaises(ProtocolError):
                service.advance({"instance_id":token,"request_id":"early","task_run_id":data["task_run_id"],"expected_revision":0})
            with self.assertRaises(ProtocolError):service.start({"world":"omega_0000"})
            # Human requests go through the same current-task StationSession.
            station = next(s for s, k in view["capabilities"].items() if k == "profile")
            from memorybenchmark.prototypes.station_routes import shortest_route
            for target in ("P", station, "C"):
                for n in shortest_route(self.design, game.state.position, target)[0][1:]:
                    data = service.action({"instance_id": token, "task_run_id":data["task_run_id"], "request_id": f"r-{game.steps}", "expected_revision": data["observation"]["revision"], "action": {"type":"move","target":n}})
                if target == station:
                    data = service.action({"instance_id": token, "task_run_id":data["task_run_id"], "request_id":"process","expected_revision":data["observation"]["revision"],"action":{"type":"process"}})
            submit = {"instance_id": token, "task_run_id":data["task_run_id"], "request_id":"submit","expected_revision":data["observation"]["revision"],"action":{"type":"submit"}}
            data = service.action(submit)
            self.assertTrue(data["observation"]["success"])
            self.assertEqual(len(service.action(submit)["completed"]), 1)
            request = {"instance_id":token,"request_id":"next","task_run_id":data["task_run_id"],"expected_revision":data["observation"]["revision"]}
            second = service.advance(request)
            self.assertEqual(second, service.advance(request))
            with self.assertRaises(ProtocolError):service.action(submit)
            self.assertEqual(second["task_index"], 2)
            self.assertEqual(second["current_actions"], [])
            self.assertEqual(second["trace"]["edges"], [])
            self.assertEqual(second["feedback"], {"kind":"started"})
            self.assertEqual(second["observation"]["revision"], 0)


if __name__ == "__main__":
    unittest.main()
