"""Verify naturally acquired opportunities, failure handling, and privacy."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design, map_world
from memorybenchmark.prototypes.station_experience import experience_opportunities, experience_schedule
from memorybenchmark.prototypes.station_routes import feedback_policy, walk
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN, StationSession
from scripts.build_easy20_reuse_map import build


class ExperienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(EASY20_REUSE_DESIGN)

    def test_success_dependencies_are_balanced_and_do_not_prescribe_stations(self):
        self.assertEqual(build(), json.loads(EASY20_REUSE_DESIGN.read_text(encoding="utf-8")))
        rows = experience_schedule(self.design)
        stages = [s for r in rows for s in r["stages"]]
        self.assertEqual(len(stages), 40)
        self.assertEqual(sum(s["has_success_conditioned_predecessor"] for s in stages), 32)
        self.assertEqual(set(Counter(s["required_kind"] for s in stages).values()), {5})
        self.assertEqual(set(Counter(s["target"] for s in stages).values()), {5})
        self.assertEqual([r["exact_repeat_of"] for r in rows[8:12]], ["T3", "T4", "T7", "T8"])
        for row in rows:
            for stage in row["stages"]:
                for source in stage["earlier_same_kind_stages"]:
                    old = self.design["tasks"][source["task_id"]]["stages"][source["stage_index"]]
                    self.assertEqual(old["required_kind"], stage["required_kind"])
                    self.assertLess(int(source["task_id"][1:]), int(row["task_id"][1:]))
        for task in self.design["tasks"].values():
            self.assertTrue(all(set(s) == {"target", "required_kind"} for s in task["stages"]))

    def test_fixed_actual_map_preserves_unknown_candidates_and_all_live_entries_agree(self):
        self.assertEqual(map_world(self.design), "omega_15_05")
        self.assertEqual(map_world(self.design, "omega_15_05"), "omega_15_05")
        with self.assertRaisesRegex(ValueError, "fixed station assignment"):
            map_world(self.design, "omega_00_00")
        from memorybenchmark.prototypes.station_pilot import pilot
        for agent in ("ga", "hermes"):
            with self.assertRaisesRegex(ValueError, "fixed station assignment"):
                pilot(None, "unused", None, None, agent=agent, design_path=EASY20_REUSE_DESIGN, world="omega_00_00")
        self.assertEqual(len(compatible_worlds(self.design, [])), 576)
        with tempfile.TemporaryDirectory() as directory:
            for unused in range(2):
                service = FieldService(Path(directory))
                first = service.start({}); second = service.start({})
                for public in (first, second):
                    game = service.instances[public["instance_id"]]["game"]
                    self.assertEqual(game._world_id, map_world(self.design))
                    self.assertNotIn("fixed_world", public["observation"]["environment"])
                    self.assertNotIn("private_worlds", public["observation"]["environment"])

    def test_any_successful_matching_station_supplies_the_later_opportunity(self):
        # Both matching alternatives work; a designer does not select one in advance.
        for station in ("A1", "A2"):
            with self.subTest(station=station):
                game = StationGame("omega_00_00", self.design)
                game.start_task("T1"); walk(game, "P"); walk(game, station)
                result = game.step({"type": "process"})
                self.assertEqual(result["feedback"]["result"], "processed")
                game.step({"type": "abandon"})  # Overall failure does not erase stage evidence.
                session = StationSession(game, "T3", feedback_mode="compact")
                record = experience_opportunities(self.design, game.events, game.task_run_id)["stages"][0]
                self.assertTrue(record["has_prior_matching_opportunity"])
                self.assertEqual(record["directly_observed_matching_stations"], [station])
                self.assertEqual(record["matching_stations_known_from_type"], ["A1", "A2"])
                self.assertEqual(record["directly_observed_matching_types"], ["A"])
                self.assertEqual(record["previous_successful_same_kind_processing"][0]["station"], station)
                self.assertFalse(record["choice_observed"])
                self.assertIsNone(record["first_branch_choice"])
                serialized = json.dumps(session.initial)
                self.assertNotIn("evaluation", serialized)
                self.assertNotIn("experience_dependencies", serialized)
                self.assertNotIn("station_information", serialized)
                self.assertEqual(session.initial["feedback"], {"kind": "started"})

    def test_merely_visiting_a_station_does_not_create_exposure(self):
        game = StationGame("omega_00_00", self.design)
        game.start_task("T1"); walk(game, "A1"); game.step({"type": "abandon"})
        game.start_task("T3")
        record = experience_opportunities(self.design, game.events, game.task_run_id)["stages"][0]
        self.assertFalse(record["has_prior_matching_opportunity"])
        self.assertEqual(record["direct_matching_feedback"], [])
        self.assertTrue(record["planned_predecessor_stages"])

    def test_failed_processing_can_supply_a_different_later_requirement(self):
        game = StationGame("omega_23_23", self.design)
        game.start_task("T1"); walk(game, "P"); walk(game, "A1")
        self.assertEqual(game.step({"type": "process"})["feedback"]["result"], "unsupported")
        game.step({"type": "abandon"}); game.start_task("T6")
        record = experience_opportunities(self.design, game.events, game.task_run_id)["stages"][0]
        self.assertEqual(record["planned_predecessor_stages"], [])
        self.assertTrue(record["has_prior_matching_opportunity"])
        self.assertEqual(record["direct_matching_feedback"][0]["result"], "unsupported")
        self.assertEqual(record["previous_successful_same_kind_processing"], [])

    def test_inference_is_separate_from_direct_station_feedback(self):
        game = StationGame("omega_00_00", self.design)
        game.start_task("T1")
        for station in ("B1", "C1", "D1"):
            walk(game, station); game.step({"type": "inspect"})
        game.step({"type": "abandon"}); game.start_task("T3")
        record = experience_opportunities(self.design, game.events, game.task_run_id)["stages"][0]
        self.assertEqual(record["directly_observed_matching_stations"], [])
        self.assertEqual(record["matching_stations_known_only_by_inference"], ["A1", "A2"])
        self.assertEqual(record["matching_stations_known_from_type"], [])
        self.assertTrue(record["has_prior_matching_opportunity"])

    def test_current_session_reacquisition_does_not_become_cross_session_exposure(self):
        game = StationGame("omega_00_00", self.design)
        game.start_task("T1"); game.step({"type": "abandon"}); game.start_task("T3")
        walk(game, "A1"); game.step({"type": "inspect"}); walk(game, "Q"); walk(game, "A1")
        record = experience_opportunities(self.design, game.events, game.task_run_id)["stages"][0]
        self.assertFalse(record["has_prior_matching_opportunity"])
        self.assertTrue(record["choice_observed"])
        self.assertTrue(record["current_session_feedback_before_choice"])

    def test_clear_and_retain_share_exposure_eligibility_not_claimed_model_knowledge(self):
        game = StationGame("omega_11_17", self.design)
        for task in ("T1", "T2"):
            game.start_task(task); feedback_policy(game)
        for condition in ("retain", "clear"):
            branch = deepcopy(game); branch.start_task("T3")
            feedback_policy(branch, retain_history=condition == "retain")
            analysis = analyze_trace(self.design, branch.events, branch.task_run_id, exact_references=False)
            stages = analysis["experience_opportunities"]["stages"]
            self.assertTrue(all(s["previous_successful_same_kind_processing"] for s in stages))
            self.assertTrue(all(s["choice_observed"] for s in stages))

    def test_only_explicit_human_design_view_exposes_future_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FieldService(Path(directory)); initial = service.start({})
            token = initial["instance_id"]; game = service.instances[token]["game"]
            self.assertEqual(initial["observation"]["environment"]["version"], "lanting-easy20-fixed-types-v5")
            before = deepcopy(game.events)
            review = service.design_view(token)
            self.assertEqual(game.events, before)
            self.assertEqual(len(review["tasks"]), 20)
            self.assertTrue(review["tasks"][2]["experience_dependencies"]["stages"][0]["earlier_same_kind_stages"])
            for public in (initial, service.read(token)):
                self.assertNotIn("experience_dependencies", json.dumps(public))
                self.assertNotIn("experience_opportunities", json.dumps(public))

    def test_other_instance_is_a_valid_new_site_for_previously_observed_type(self):
        game=StationGame("omega_00_00",self.design)
        game.start_task("T1");walk(game,"P");walk(game,"A1");game.step({"type":"process"});game.step({"type":"abandon"})
        session=StationSession(game,"T13",feedback_mode="compact")
        self.assertNotIn("station_information",json.dumps(session.initial))
        walk(game,"U");walk(game,"A2");game.step({"type":"process"})
        stage=experience_opportunities(self.design,game.events,game.task_run_id)["stages"][0]
        self.assertTrue(stage["first_branch_choice"]["new_station_of_previously_observed_type"])
        self.assertEqual(stage["first_branch_choice"]["station_type"],"A")
        self.assertEqual(stage["first_branch_choice"]["same_type_prior_feedback"][0]["station"],"A1")
        self.assertEqual(stage["unvisited_matching_stations_of_observed_types"],["A2"])

    def test_public_type_labels_do_not_reveal_the_random_capability_mapping(self):
        observations=[]
        for world in ("omega_00_00","omega_23_23"):
            game=StationGame(world,self.design);session=StationSession(game,"T1")
            public=session.initial["observation"]["environment"]
            self.assertEqual(len(public["station_types"]),8)
            self.assertTrue(all(len(t["stations"])==2 for t in public["station_types"].values()))
            self.assertNotIn("private_worlds",json.dumps(session.initial))
            self.assertNotIn("capability",public["locations"]["A1"])
            observations.append(session.initial)
        self.assertEqual(observations[0],observations[1])
        self.assertNotEqual(self.design["private_worlds"]["omega_00_00"]["A1"],self.design["private_worlds"]["omega_23_23"]["A1"])
        for world in self.design["private_worlds"].values():
            for t in self.design["public"]["station_types"].values():
                self.assertEqual(len({world[s] for s in t["stations"]}),1)

    def test_wrong_public_station_family_is_still_an_observed_choice(self):
        game=StationGame("omega_00_00",self.design);game.start_task("T3")
        walk(game,"Q");walk(game,"E1");game.step({"type":"process"})
        stage=experience_opportunities(self.design,game.events,game.task_run_id)["stages"][0]
        self.assertTrue(stage["choice_observed"])
        self.assertEqual(stage["first_branch_choice"]["station"],"E1")
        self.assertEqual(stage["first_branch_choice"]["historical_status"],"known_nonmatch")


if __name__ == "__main__":
    unittest.main()
