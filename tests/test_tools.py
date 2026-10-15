from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.analysis import commute_graph, diagnose
from memorybenchmark.game import Game, ProtocolError
from memorybenchmark.validation import validate, reference_route
from memorybenchmark.tool_calibration import calibrate_tools


def play(adapter, *targets):
    for target in targets:
        adapter.action("move", target)


class ToolGameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()
        self.adapter = GameAdapter(self.game)
        self.adapter.dispatch({"command": "start", "task_id": "T1"})

    def test_arrival_maps_automatically_and_omits_risk_layer(self):
        play(self.adapter, "J", "A")
        self.assertIn("A", self.game.surveyed)
        self.assertEqual(self.game.effort, 16)
        self.assertEqual(self.game.stamina, 44)
        self.assertNotIn("hazards", self.game.observation()["map"])
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])
        with self.assertRaises(ProtocolError):
            self.adapter.action("survey")

    def test_stock_hidden_until_arrival_and_take_is_nonmovement(self):
        self.assertEqual(self.game.observation()["available_tools"], [])
        self.assertEqual(self.game.evidence, [])
        self.assertFalse(any("工具点" in n["name"] for n in self.game.observation()["map"]["nodes"]))
        play(self.adapter, "J", "D")
        stock = self.game.observation()["available_tools"]
        self.assertEqual([t["id"] for t in stock], ["snow_kit"])
        moves = len(commute_graph(self.game.events, self.game.task_run_id)["edges"])
        self.adapter.action("take", "snow_kit")
        self.assertEqual(self.game.inventory, {"snow_kit"})
        self.assertEqual(len(commute_graph(self.game.events, self.game.task_run_id)["edges"]), moves)
        self.assertEqual(self.adapter.action("take", "snow_kit")["outcome"], "already_carried")

    def test_protection_changes_effort_on_same_geographic_edge(self):
        bare = deepcopy(self.game.snapshot())
        play(self.adapter, "J", "A")
        event_without = self.game.events[-1]
        self.game.restore(bare)
        self.game.inventory.add("snow_kit")  # Controlled fixture, not a learned-memory condition.
        play(self.adapter, "J", "A")
        event_with = self.game.events[-1]
        self.assertEqual((event_without["from"], event_without["to"]), ("J", "A"))
        self.assertEqual((event_without["hazard_cost"], event_with["hazard_cost"]), (12, 2))
        self.assertEqual(event_with["equipment_used"], "snow_kit")
        self.assertEqual(event_with["effort_cost"], 4)

    def test_first_hazard_does_not_grant_unknown_tool_effect(self):
        play(self.adapter, "J", "A")
        evidence = self.game.evidence[-1]
        self.assertEqual(evidence["claim"], "hazard_encountered")
        self.assertIsNone(evidence["equipment_used"])
        decision = diagnose(self.game.events, self.game.task_run_id)["hazard_decisions"][0]
        self.assertEqual(decision["prior_same_condition_evidence"], [])
        self.assertEqual(decision["prior_relevant_tool_sources"], [])

    def test_failure_preserves_evidence_and_resets_physical_state(self):
        self.game.stamina = 3
        play(self.adapter, "J", "A")
        self.assertTrue(self.game.done)
        self.assertFalse(self.game.success)
        self.assertIn("A", self.game.surveyed)
        count = len(self.game.evidence)
        self.adapter.dispatch({"command": "start", "task_id": "T2"})
        self.assertEqual(len(self.game.evidence), count)
        self.assertEqual(self.game.inventory, set())
        self.assertEqual(self.game.stamina, 32)
        self.assertEqual(self.game.surveyed, {"S"})

    def test_hazard_conditions_are_evaluated_at_arrival(self):
        self.game.world["hazards"]["A"]["conditions"] = {"weather": "rain"}
        self.game.clock = 34
        play(self.adapter, "J", "A")  # Arrival t=38, rain starts t=37.
        self.assertEqual(self.game.events[-1]["hazard_cost"], 12)
        self.assertEqual(self.game.events[-1]["conditions_before"]["weather"], "clear")
        self.assertEqual(self.game.events[-1]["arrival_conditions"]["weather"], "rain")

    def test_known_tool_at_initial_depot_is_registered(self):
        self.adapter.action("abandon")
        self.adapter.dispatch({"command": "start", "task_id": "T6"})
        play(self.adapter, "A")
        decision = diagnose(self.game.events, self.game.task_run_id)["hazard_decisions"][0]
        self.assertTrue(decision["prior_relevant_tool_sources"])

    def test_reference_solver_paths_replay_and_tool_is_not_always_best(self):
        report = validate(self.game.world, self.game.tasks)
        self.assertEqual(report["T2"]["with_tool_options"]["effort"], 10)
        self.assertEqual(report["T6"]["with_tool_options"]["effort"], 9)
        self.assertFalse(any(a["type"] == "take" for a in report["T6"]["with_tool_options"]["actions"]))
        for task_id, row in report.items():
            game = Game()
            adapter = GameAdapter(game)
            adapter.dispatch({"command": "start", "task_id": task_id})
            for action in row["with_tool_options"]["actions"]:
                adapter.action(action["type"], action.get("target"))
            self.assertTrue(game.success, task_id)
            self.assertEqual(game.effort, row["with_tool_options"]["effort"], task_id)

    def test_static_solver_rejects_dynamic_conditions(self):
        self.game.world["hazards"]["A"]["conditions"] = {"weather": "rain"}
        with self.assertRaises(ValueError):
            reference_route(self.game.world, self.game.tasks["T1"])

    def test_reference_solver_respects_action_budget_when_choosing_route(self):
        task = {**self.game.tasks["T2"], "start":"J", "max_steps":3}
        route = reference_route(self.game.world, task)
        self.assertEqual(route["effort"], 10)
        self.assertEqual(len(route["actions"]), 3)
        game = Game(tasks={"short":task})
        adapter = GameAdapter(game)
        adapter.dispatch({"command":"start", "task_id":"short"})
        for action in route["actions"]:
            adapter.action(action["type"], action.get("target"))
        self.assertTrue(game.success)

    def test_four_successful_behaviors_have_distinct_preparation_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            results = calibrate_tools(Path(directory))
        self.assertTrue(all(r["success"] for r in results.values()))
        self.assertEqual({k:r["effort"] for k,r in results.items()},
                         {"prepared":10,"unprepared":18,"avoid_hazard":12,"belated_preparation":26})
        unprepared = results["unprepared"]["diagnostics"]["hazard_decisions"][0]
        self.assertTrue(unprepared["prior_same_condition_evidence"])
        self.assertTrue(unprepared["prior_relevant_tool_sources"])
        self.assertFalse(unprepared["protected"])


if __name__ == "__main__":
    unittest.main()
