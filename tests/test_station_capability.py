from copy import deepcopy
from fractions import Fraction
import unittest

from memorybenchmark.analysis import commute_graph
from memorybenchmark.prototypes.station_capability import (
    ReferencePlanner, StationGame, compatible_worlds, load_design, replay_policy,
)


def move(game, *nodes):
    for node in nodes:
        game.step({"type": "move", "target": node})


class StationCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design()

    def test_public_inputs_are_identical_until_an_informative_operation(self):
        a, b = (StationGame(world, self.design) for world in self.design["private_worlds"])
        self.assertEqual(a.start_task("profile"), b.start_task("profile"))
        for target in ("J", "P", "J", "A"):
            self.assertEqual(a.step({"type": "move", "target": target}), b.step({"type": "move", "target": target}))
        self.assertEqual(len(compatible_worlds(self.design, a.events)), 2)
        left, right = a.step({"type": "process"}), b.step({"type": "process"})
        self.assertNotEqual(left["feedback"]["capability"], right["feedback"]["capability"])
        self.assertEqual({left["feedback"]["result"], right["feedback"]["result"]}, {"processed", "unsupported"})

    def test_wrong_station_preserves_data_and_allows_success(self):
        game = StationGame("omega_1", self.design)
        game.start_task("profile")
        move(game, "J", "P", "J", "A")
        self.assertEqual(game.step({"type": "process"})["feedback"]["result"], "unsupported")
        self.assertTrue(game.state.raw)
        self.assertFalse(game.state.processed)
        move(game, "J", "B")
        game.step({"type": "process"})
        move(game, "J", "C")
        self.assertTrue(game.step({"type": "submit"})["observation"]["success"])
        graph = commute_graph(game.events, game.task_run_id)
        self.assertEqual((game.distance, graph["distance"], len(graph["edges"])), (12, 12, 8))

    def test_failure_keeps_evidence_but_next_session_resets_physical_state(self):
        game = StationGame("omega_0", self.design)
        game.start_task("profile")
        move(game, "J", "A")
        game.step({"type": "inspect"})
        game.step({"type": "abandon"})
        self.assertFalse(game.state.success)
        self.assertEqual(compatible_worlds(self.design, game.events), ("omega_0",))
        response = game.start_task("shore")
        self.assertEqual((game.state.position, game.state.raw, game.state.processed, game.steps), ("C", False, False, 0))
        self.assertNotIn("capability", str(response["observation"]["environment"]["locations"]))
        self.assertNotIn("private_worlds", response["observation"]["environment"])
        self.assertNotIn("events", response["observation"])
        self.assertEqual(game.step({"type": "move", "target": "J"})["observation"]["location"], "J")

    def test_visiting_station_does_not_count_as_learning_its_capability(self):
        game = StationGame("omega_0", self.design)
        game.start_task("profile")
        move(game, "J", "A")
        game.step({"type": "abandon"})
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 2)
        # A private evaluator annotation must not invent delivered knowledge.
        game.events[-1]["evidence_delivered"] = [{"station": "A", "capability": "profile"}]
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 2)

    def test_budget_failure_still_delivers_the_last_informative_feedback(self):
        design = deepcopy(self.design)
        design["tasks"]["profile"]["max_steps"] = 3
        game = StationGame("omega_0", design)
        game.start_task("profile")
        move(game, "J", "A")
        result = game.step({"type": "inspect"})
        self.assertEqual(result["feedback"]["termination"], "budget_exhausted")
        self.assertTrue(game.state.done)
        self.assertFalse(game.state.success)
        self.assertEqual(compatible_worlds(design, game.events), ("omega_0",))
        game.start_task("shore")
        self.assertEqual(game.task["max_steps"], 16)

    def test_unknown_world_policy_has_an_unavoidable_expected_extra_visit(self):
        planner = ReferencePlanner(self.design, "shore")
        worlds = tuple(self.design["private_worlds"])
        self.assertEqual(planner.initial(worlds).distance, Fraction(10))
        distances = []
        for world in worlds:
            self.assertEqual(planner.initial((world,)).distance, Fraction(8))
            game = StationGame(world, self.design)
            game.start_task("shore")
            replay_policy(game, planner, worlds)
            distances.append(game.distance)
        self.assertEqual(sorted(distances), [8, 12])
        self.assertEqual(Fraction(sum(distances), 2), planner.initial(worlds).distance)

    def test_processing_and_submission_require_current_task_data(self):
        game = StationGame("omega_0", self.design)
        game.start_task("profile")
        self.assertEqual(game.step({"type": "submit"})["feedback"]["kind"], "not_ready")
        move(game, "J", "A")
        before = game.steps
        with self.assertRaises(ValueError):
            game.step({"type": "process"})
        self.assertEqual(game.steps, before)
        game.step({"type": "abandon"})
        game.start_task("shore")
        move(game, "J", "P")
        self.assertFalse(game.state.raw)

    def test_impossible_or_empty_reference_information_is_rejected(self):
        planner = ReferencePlanner(self.design, "shore")
        with self.assertRaises(ValueError):
            planner.initial(())
        with self.assertRaises(ValueError):
            planner.initial(("not_a_world",))
        fake = [{"delivered": {"feedback": {"kind": "station_information", "station": "A", "capability": "impossible"}}}]
        with self.assertRaises(ValueError):
            compatible_worlds(self.design, fake)


if __name__ == "__main__":
    unittest.main()
