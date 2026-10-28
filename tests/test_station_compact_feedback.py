"""Compact presentation must preserve rules, new evidence and public map access."""
from copy import deepcopy
import json
import unittest

from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_routes import shortest_route
from memorybenchmark.prototypes.station_session import EASY20_LINKED_DESIGN, StationSession


class CompactStationFeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(EASY20_LINKED_DESIGN)

    def test_initial_and_explicit_read_keep_map_without_repeating_it_after_moves(self):
        game = StationGame("omega_3051", self.design)
        session = StationSession(game, "T1", feedback_mode="compact")
        self.assertEqual(session.initial["observation"]["environment"], self.design["public"])
        result = session.dispatch({"command": "action", "request_id": "move", "action": {"type": "move", "target": "J"}})
        self.assertNotIn("environment", result["observation"])
        self.assertNotIn("公开能力范围", result["text"])
        self.assertTrue(result["observation"]["neighbors"])
        before = deepcopy(game.events), game.steps, session.revision
        read = session.dispatch({"command": "read"})
        self.assertEqual(read["observation"]["environment"], self.design["public"])
        self.assertEqual(read["observation"]["location"], "J")
        self.assertEqual(read["feedback"], {"kind": "current_observation"})
        self.assertEqual((game.events, game.steps, session.revision), before)
        self.assertNotIn("private_worlds", json.dumps(read))
        self.assertNotIn("omega_3051", json.dumps(read))

    def test_both_stages_and_failed_processing_match_full_feedback_exactly(self):
        full_game, compact_game = [StationGame("omega_3051", self.design) for _ in range(2)]
        full = StationSession(full_game, "T1")
        compact = StationSession(compact_game, "T1", feedback_mode="compact")
        results = []
        def action(value):
            request = {"command": "action", "request_id": str(full.revision), "action": value}
            a,b = full.dispatch(request), compact.dispatch(request)
            self.assertEqual(a["feedback"], b["feedback"])
            self.assertEqual(full_game.events, compact_game.events)
            for key in ("task", "location", "raw", "processed", "steps", "distance", "time", "done", "success", "stage_index", "stage_count", "stages_completed", "available_actions", "revision"):
                self.assertEqual(a["observation"][key], b["observation"][key])
            self.assertLess(len(json.dumps(b)), len(json.dumps(a)))
            results.append(b)
        def move(target):
            for node in shortest_route(self.design, full_game.state.position, target)[0][1:]:
                action({"type": "move", "target": node})
        move("P"); move("A"); action({"type": "process"})
        self.assertEqual(results[-1]["feedback"]["result"], "unsupported")
        self.assertTrue(results[-1]["observation"]["raw"])
        move("B"); action({"type": "process"})
        after_first = results[-1]
        self.assertEqual(after_first["feedback"]["next_stage"], 2)
        self.assertEqual(after_first["observation"]["task"]["required_kind"], "bearing")
        self.assertEqual(after_first["observation"]["task"]["target"], "R")
        self.assertFalse(after_first["observation"]["raw"])
        self.assertFalse(after_first["observation"]["done"])
        self.assertIn("当前第 2/2 段", after_first["text"])
        move("R"); move("D"); action({"type": "process"}); move("C"); action({"type": "submit"})
        self.assertTrue(results[-1]["observation"]["success"])

    def test_read_and_new_session_do_not_replay_station_capability(self):
        game = StationGame("omega_3051", self.design)
        session = StationSession(game, "T1", feedback_mode="compact")
        for node in shortest_route(self.design, "C", "A")[0][1:]:
            session.dispatch({"command": "action", "request_id": str(session.revision), "action": {"type": "move", "target": node}})
        info = session.dispatch({"command": "action", "request_id": "inspect", "action": {"type": "inspect"}})
        self.assertEqual(info["feedback"]["capability"], "shore")
        read = session.dispatch({"command": "read"})
        self.assertNotIn('"capability":', json.dumps(read))
        self.assertNotIn("station_information", json.dumps(read))
        session.dispatch({"command": "action", "request_id": "end", "action": {"type": "abandon"}})
        next_task = StationSession(game, "T3", feedback_mode="compact")
        self.assertNotIn('"capability":', json.dumps(next_task.initial))
        self.assertEqual(next_task.initial["feedback"], {"kind": "started"})

    def test_delivery_recording_and_retries_do_not_add_actions(self):
        delivered = []
        game = StationGame("omega_3051", self.design)
        session = StationSession(game, "T1", feedback_mode="compact", on_delivery=lambda request,response: delivered.append((request,response)))
        request = {"command": "action", "request_id": "one", "action": {"type": "move", "target": "J"}}
        first = session.dispatch(request)
        self.assertEqual(session.dispatch(request), first)
        self.assertEqual(game.steps, 1)
        delivered[-1][1]["observation"]["location"] = "mutated_log"
        self.assertEqual(session.dispatch(request)["observation"]["location"], "J")
        terminal = session._public(game.finish_incomplete("model_budget"))
        self.assertTrue(terminal["observation"]["done"])
        self.assertNotIn("environment", terminal["observation"])
        self.assertEqual(len(delivered), 5)


if __name__ == "__main__":
    unittest.main()
