from copy import deepcopy
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.analysis import commute_graph
from memorybenchmark.game import Game, ProtocolError
from memorybenchmark.validation import validate, reference_route
from memorybenchmark.worlds import load_scenario


def move(adapter, *locations):
    for location in locations:
        adapter.action("move", location)


class LochNessTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="loch-ness")
        self.adapter = GameAdapter(self.game)

    def test_first_task_is_survivable_without_tools_but_needs_camp(self):
        self.game.start_task("T1")
        move(self.adapter, "E1", "E2", "P1")
        self.assertEqual(self.adapter.action("submit")["outcome"], "not_at_camp")
        self.assertFalse(self.game.done)
        self.assertEqual(self.game.observer_atlas()["nodes"], [])
        move(self.adapter, "C1")
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])
        self.assertEqual(self.game.effort, 44)
        self.assertEqual(sum(e.get("hazard_cost", 0) > 0 for e in self.game.events), 1)

    def test_second_unprotected_encounter_is_fatal_and_next_task_still_starts(self):
        self.game.start_task("T2")
        move(self.adapter, "E1", "E2", "P1", "C1", "N1", "C1")
        result = self.adapter.action("move", "P1")
        self.assertEqual(result["outcome"], "exhausted")
        self.assertEqual(self.game.stamina, 0)
        self.assertFalse(self.game.success)
        self.assertEqual(self.game.observer_atlas()["nodes"], [])
        evidence = deepcopy(self.game.evidence)
        self.game.start_task("T3")
        self.assertEqual(self.game.position, "C0")
        self.assertEqual(self.game.inventory, set())
        self.assertEqual(self.game.stamina, 70)
        self.assertEqual(self.game.evidence, evidence)

    def test_wrong_tool_does_not_mitigate_and_camps_do_not_refill_midtask(self):
        self.game.start_task("T1")
        self.game.inventory.add("stream_kit")  # Controlled physics fixture.
        move(self.adapter, "E1", "E2", "P1")
        self.assertEqual(self.game.events[-1]["hazard_cost"], 38)
        self.assertIsNone(self.game.events[-1]["equipment_used"])
        remaining = self.game.stamina
        move(self.adapter, "C1")
        self.assertEqual(self.game.stamina, remaining - 2)

    def test_submitted_atlas_is_not_an_agent_observation_or_future_completion(self):
        self.game.start_task("T1")
        move(self.adapter, "E1", "E2", "P1", "C1")
        self.adapter.action("submit")
        atlas = self.game.observer_atlas()
        self.assertIn("P1", atlas["surveyed"])
        self.assertNotIn("U2", atlas["surveyed"])  # Adjacent, but never visited.
        self.assertEqual(len(atlas["edges"]), 4)
        self.assertNotIn("hazards", atlas)
        response = self.adapter.dispatch({"command": "start", "task_id": "T2"})
        self.assertNotIn("atlas", response)
        self.assertNotIn("P1", {n["id"] for n in response["observation"]["map"]["nodes"]})
        self.assertFalse(response["observation"]["objective"]["targets"][0]["recorded"])
        self.assertIn("P1", self.game.observer_atlas()["surveyed"])

    def test_multi_goal_task_cannot_submit_early_or_at_wrong_camp(self):
        self.game.start_task("T8")
        self.assertEqual(self.adapter.action("submit")["outcome"], "not_at_camp")
        self.game.world["hazards"] = {}  # Isolate submission rules from survival.
        move(self.adapter, "E1", "E2", "P1", "C1", "N1", "P2", "N2", "W1", "C2")
        result = self.adapter.action("submit")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertFalse(result["observation"]["success"])
        move(self.adapter, "W2", "R1", "S1", "R2", "S2", "P3", "S2", "R2", "S1", "R1", "W2", "C2")
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])

    def test_sparse_world_and_optional_tool_branches(self):
        world, tasks = load_scenario("loch-ness")
        self.assertEqual(len(world["locations"]), 31)
        self.assertEqual(len(world["edges"]), 31)
        reached, pending = set(), ["C0"]
        while pending:
            location = pending.pop()
            if location in reached:
                continue
            reached.add(location)
            pending.extend(n["target"] for n in self.game.neighbors(location))
        self.assertEqual(reached, set(world["locations"]))
        for depot in world["depots"]:
            self.assertEqual(len(self.game.neighbors(depot)), 1)
            self.assertFalse(any(depot in task.get("goals", []) for task in tasks.values()))
        for task in tasks.values():
            self.assertIn(task["start"], world["camps"])
            self.assertTrue(set(task["submit_at"]) <= set(world["camps"]))
            self.assertFalse(set(task["goals"]) & set(world["camps"]))

    def test_all_reference_routes_replay_with_progressively_more_hazards(self):
        world, tasks = load_scenario("loch-ness")
        report = validate(world, tasks)
        counts = []
        campaign = Game(scenario="loch-ness")
        adapter = GameAdapter(campaign)
        for task_id, row in report.items():
            campaign.start_task(task_id)
            for action in row["with_tool_options"]["actions"]:
                adapter.action(action["type"], action.get("target"))
            self.assertTrue(campaign.success, task_id)
            self.assertEqual(campaign.effort, row["with_tool_options"]["effort"])
            graph = commute_graph(campaign.events, campaign.task_run_id)
            counts.append(sum(e["hazard_cost"] > 0 for e in graph["edges"]))
            self.assertTrue(all(e["equipment_used"] for e in graph["edges"] if e["hazard_cost"]))
            if task_id != "T1":
                self.assertFalse(row["without_taking_tools"]["within_stamina"])
        self.assertEqual(counts, list(range(1, 9)))

    def test_curriculum_transitions_from_one_tool_to_both_tools(self):
        world,tasks=load_scenario('loch-ness')
        costs={}
        for tool in ('grip_kit','stream_kit'):
            variant=deepcopy(world)
            variant['depots']={n:[t for t in stock if t==tool] for n,stock in world['depots'].items()}
            costs[tool]={task:reference_route(variant,definition)['effort'] for task,definition in tasks.items()}
        self.assertLess(costs['grip_kit']['T2'],70)
        self.assertEqual(costs['grip_kit']['T3'],61)
        self.assertGreaterEqual(costs['stream_kit']['T3'],70)
        for task in list(tasks)[3:]:
            self.assertTrue(all(rows[task]>=70 for rows in costs.values()),task)

    def test_invalid_noncamp_spawn_rejected_before_mutation(self):
        self.game.tasks["T1"]["start"] = "P1"
        before = self.game.snapshot()
        with self.assertRaises(ProtocolError):
            self.game.start_task("T1")
        self.assertEqual(self.game.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
