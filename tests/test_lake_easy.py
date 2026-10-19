from copy import deepcopy
import json
from pathlib import Path
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.analysis import commute_graph
from memorybenchmark.game import Game, ProtocolError
from memorybenchmark.validation import validate, reference_route
from memorybenchmark.worlds import load_scenario


def move(adapter, *locations):
    for location in locations:
        adapter.action("move", location)


class LakeEasyTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="lake-easy")
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

    def test_second_unprotected_encounter_respawns_and_next_task_resets_recovery(self):
        self.game.start_task("T2")
        move(self.adapter, "E1", "E2", "P1", "C1", "N1", "C1")
        result = self.adapter.action("move", "P1")
        self.assertEqual(result["outcome"], "respawned")
        self.assertEqual(self.game.position, "C0")
        self.assertEqual(self.game.stamina, 70)
        self.assertFalse(self.game.done)
        self.assertEqual(self.game.deaths, 1)
        self.assertFalse(self.game.success)
        self.assertEqual(self.game.observer_atlas()["nodes"], [])
        evidence = deepcopy(self.game.evidence)
        self.adapter.action("abandon")
        self.game.start_task("T3")
        self.assertEqual(self.game.position, "C2")
        self.assertEqual(self.game.inventory, set())
        self.assertEqual(self.game.stamina, 70)
        self.assertEqual(self.game.evidence, evidence)
        self.assertEqual(self.game.deaths, 0)
        self.assertEqual(self.game.recovery_history, [])

    def test_wrong_tool_does_not_mitigate_and_camps_do_not_refill_midtask(self):
        self.game.start_task("T1")
        self.game.inventory.add("stream_kit")  # Controlled physics fixture.
        move(self.adapter, "E1", "E2", "P1")
        self.assertEqual(self.game.events[-1]["hazard_cost"], 38)
        self.assertIsNone(self.game.events[-1]["equipment_used"])
        remaining = self.game.stamina
        move(self.adapter, "C1")
        self.assertEqual(self.game.stamina, remaining - 2)

    def test_shared_geography_is_in_agent_text_but_does_not_complete_new_goals(self):
        self.game.start_task("T1")
        move(self.adapter, "E1", "E2", "P1", "C1")
        self.adapter.action("submit")
        atlas = self.game.observer_atlas()
        self.assertIn("P1", atlas["surveyed"])
        self.assertNotIn("U2", atlas["surveyed"])  # Adjacent, but never visited.
        self.assertEqual(len(atlas["edges"]), 4)
        self.assertNotIn("hazards", atlas)
        self.game.tasks['T2']['goals']=['P1']
        response = self.adapter.dispatch({"command": "start", "task_id": "T2"})
        self.assertIn("P1", {n["id"] for n in response["observation"]["map"]["nodes"]})
        self.assertIn('P1',response['observation']['map']['charted'])
        self.assertNotIn('P1',response['observation']['map']['surveyed'])
        self.assertIn('P1',response['text'])
        self.assertIn('共享地理图地点',response['text'])
        self.assertIn({'source':'E2','target':'P1','distance':1},response['observation']['map']['distances'])
        self.assertNotIn('hazard_cost',json.dumps(response['observation']['map']))
        self.assertFalse(response["observation"]["objective"]["targets"][0]["recorded"])
        self.assertEqual(self.adapter.action('submit')['outcome'],'incomplete')
        self.assertIn("P1", self.game.observer_atlas()["surveyed"])

    def test_multi_goal_task_cannot_submit_early_or_at_wrong_camp(self):
        self.game.tasks['T4']['goals']=['R1','S1']
        self.game.start_task("T4")
        self.assertEqual(self.adapter.action("submit")["outcome"], "incomplete")
        self.game.world["hazards"] = {}  # Isolate submission rules from survival.
        move(self.adapter, "W2", "R1", "W2", "C2")
        result = self.adapter.action("submit")
        self.assertEqual(result["outcome"], "incomplete")
        self.assertFalse(result["observation"]["success"])
        move(self.adapter, "W2", "R1", "S1", "R1", "W2", "C2")
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])

    def test_sparse_world_and_optional_tool_branches(self):
        world, tasks = load_scenario("lake-easy")
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

    def test_easy_curriculum_has_only_one_or_two_required_encounters(self):
        world, tasks = load_scenario("lake-easy")
        report = validate(world, tasks)
        counts = []
        campaign = Game(scenario="lake-easy")
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
            if task_id not in ("T1","T3"):
                self.assertFalse(row["without_taking_tools"]["within_stamina"])
            else:
                self.assertTrue(row["without_taking_tools"]["within_stamina"])
        self.assertEqual(counts, [1,2,1,2,2,2,2,2])

    def test_each_reuse_task_needs_the_corresponding_tool_to_avoid_death(self):
        world,tasks=load_scenario('lake-easy')
        costs={}
        for tool in ('grip_kit','stream_kit'):
            variant=deepcopy(world)
            variant['depots']={n:[t for t in stock if t==tool] for n,stock in world['depots'].items()}
            costs[tool]={task:reference_route(variant,definition)['effort'] for task,definition in tasks.items()}
        for task in ('T2', 'T5', 'T7'):
            self.assertLess(costs['grip_kit'][task],70)
            self.assertGreaterEqual(costs['stream_kit'][task],70)
        for task in ('T4', 'T6', 'T8'):
            self.assertLess(costs['stream_kit'][task],70)
            self.assertGreaterEqual(costs['grip_kit'][task],70)

    def test_agent_facing_world_and_every_response_use_only_fictional_names(self):
        world,tasks=load_scenario('lake-easy')
        forbidden=('loch','ness','scottish','尼斯','多里斯','厄克特','阿布里亚','因弗莫里斯顿','福耶斯')
        report=validate(world,tasks)
        alias=Game(scenario='loch-ness')
        self.assertEqual(alias.start_task('T1')['observation']['environment']['id'],'lake-easy')
        for task,row in report.items():
            game=Game(scenario='lake-easy'); adapter=GameAdapter(game)
            responses=[adapter.dispatch({'command':'start','task_id':task})]
            for action in row['with_tool_options']['actions']:
                responses.append(adapter.action(action['type'],action.get('target')))
            for response in responses:
                encoded=json.dumps(response,ensure_ascii=False).lower()
                self.assertFalse(any(term in encoded for term in forbidden))
        for asset in (Path(__file__).resolve().parents[1]/'memorybenchmark/static').iterdir():
            if asset.is_file():
                text=asset.read_text(encoding='utf-8').lower()
                self.assertFalse(any(term in text for term in ('loch ness','loch-ness','尼斯湖','scottish highlands')),asset.name)

    def test_paired_initial_maps_match_without_carrying_tool_or_hazard_experience(self):
        self.game.start_task('T1')
        move(self.adapter,'E1','U1','D1')
        self.adapter.action('take','grip_kit')
        move(self.adapter,'U1','E1','E2','P1','C1')
        self.adapter.action('submit')
        checkpoint=self.game.snapshot()
        branches=[]
        for _ in ('retain','clear'):
            game=Game();game.restore(checkpoint)
            response=GameAdapter(game).dispatch({'command':'start','task_id':'T2'})
            branches.append(response)
            encoded=json.dumps(response,ensure_ascii=False)
            self.assertIn('D1',response['observation']['map']['charted'])
            self.assertNotIn('grip_kit',encoded)
            self.assertNotIn('湿滑岩坡',encoded)
            self.assertNotIn('extra_effort',encoded)
            self.assertEqual(response['observation']['available_tools'],[])
        self.assertEqual(branches[0]['text'],branches[1]['text'])
        self.assertEqual(branches[0]['observation']['map'],branches[1]['observation']['map'])

    def test_invalid_noncamp_spawn_rejected_before_mutation(self):
        self.game.tasks["T1"]["start"] = "P1"
        before = self.game.snapshot()
        with self.assertRaises(ProtocolError):
            self.game.start_task("T1")
        self.assertEqual(self.game.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
