"""Metric contract tests use actual game feedback, with no model/API calls."""
from copy import deepcopy
from pathlib import Path
import unittest

from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_metrics import Evidence, compare_streams, fraction, score_stream, summarize_stages, summarize_stream
from memorybenchmark.prototypes.station_routes import feedback_policy, walk

# Historical metrics include inspect-based 1.1 traces; new live maps use 1.2.
DESIGN = Path(__file__).resolve().parents[1] / "memorybenchmark/data/history/nessie_easy20_1_1.json"


class StationMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(DESIGN)

    def game_with_history(self, stations=("A1", "C1")):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T1")
        for station in stations:
            walk(game, station)
            game.step({"type": "inspect"})
        game.step({"type": "abandon"})
        return game

    def score(self, game, condition="retain"):
        return score_stream(self.design, game.events, condition=condition)

    def test_zero_denominator_is_missing(self):
        self.assertEqual(fraction(0, 0), {"numerator": 0, "denominator": 0, "value": None})

    def complete_profile_vegetation_task(self, game):
        walk(game, "Q"); walk(game, "C1"); game.step({"type": "process"})
        walk(game, "V"); walk(game, "A1"); game.step({"type": "process"})
        walk(game, "C"); game.step({"type": "submit"})

    def test_visits_and_queries_do_not_count_as_submission_attempts(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T3")
        walk(game, "B1"); game.step({"type": "inspect"}); game.step({"type": "inspect"})
        self.complete_profile_vegetation_task(game)
        scored = self.score(game)
        self.assertFalse(scored["tasks"][0]["strict_success"])
        self.assertEqual(scored["tasks"][0]["processing_accuracy"], fraction(2, 2))
        self.assertEqual(len(scored["processing_attempts"]), 2)
        self.assertTrue(all(a["correct"] for a in scored["processing_attempts"]))

    def test_each_failed_process_retry_counts_even_at_the_same_station(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T3"); walk(game, "Q"); walk(game, "A1")
        game.step({"type": "process"}); game.step({"type": "process"})
        self.complete_profile_vegetation_task(game)
        scored = self.score(game)
        task = scored["tasks"][0]
        self.assertEqual(task["processing_accuracy"], fraction(2, 4))
        self.assertEqual(task["unsupported_processing_count"], 2)
        self.assertEqual([a["correct"] for a in scored["processing_attempts"]], [False, False, True, True])

    def test_submission_accuracy_pools_attempts_instead_of_averaging_task_rates(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T3"); self.complete_profile_vegetation_task(game)
        game.start_task("T9"); walk(game, "Q"); walk(game, "A1")
        game.step({"type": "process"}); game.step({"type": "process"})
        self.complete_profile_vegetation_task(game)
        summary = summarize_stream(self.score(game))["all_tasks"]
        self.assertEqual(summary["processing_accuracy"], fraction(4, 6))
        self.assertEqual(summary["completion_rate"], fraction(2, 2))

    def test_no_submission_attempts_are_missing_accuracy_and_failed_completion(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T3"); game.step({"type": "abandon"})
        summary = summarize_stream(self.score(game))["all_tasks"]
        self.assertEqual(summary["processing_accuracy"], fraction(0, 0))
        self.assertEqual(summary["completion_rate"], fraction(0, 1))
        self.assertEqual(summary["tasks_without_processing_attempts"], 1)

    def test_failure_and_unreached_stages_remain_in_denominator(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T1"); game.step({"type": "abandon"})
        scored = self.score(game)
        summary = summarize_stages(scored["stages"])
        self.assertEqual(summary["first_any_accuracy"], fraction(0, 2))
        self.assertEqual(summary["missing_first_choices"], 2)
        self.assertEqual(scored["tasks"][0]["physical_efficiency"], 0)
        self.assertFalse(scored["tasks"][0]["strict_success"])
        self.assertEqual(summarize_stream(scored)["all_tasks"]["strict_success_rate"], fraction(0, 1))
        self.assertIsNone(summary["negative_selection_feedback"]["first_repeat_error_rate"]["value"])

    def test_a_wrong_unqueried_visit_is_not_corrective_feedback(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T1"); walk(game, "A1"); game.step({"type": "abandon"})
        scored = self.score(game)
        self.assertFalse(scored["stages"][0]["first_any"]["correct"])
        self.assertEqual(scored["negative_feedback_sources"], [])
        self.assertFalse(scored["tasks"][0]["strict_success"])
        self.assertEqual(scored["tasks"][0]["strict_failure_reason"], "wrong_station_entry")

    def test_wrong_entry_is_not_rescued_by_later_successful_submission(self):
        game = self.game_with_history()
        game.start_task("T3")
        walk(game, "B1"); game.step({"type": "inspect"})
        feedback_policy(game)
        task = self.score(game)["tasks"][-1]
        self.assertTrue(task["success"])
        self.assertFalse(task["strict_success"])
        self.assertEqual(task["first_wrong_station_entry"]["station"], "B1")
        self.assertFalse(task["first_wrong_station_entry"]["collected_before_choice"])

    def test_correct_first_choice_cannot_hide_a_later_wrong_station(self):
        game = self.game_with_history()
        game.start_task("T3")
        walk(game, "Q"); walk(game, "C1"); game.step({"type": "inspect"})
        walk(game, "B1"); game.step({"type": "inspect"})
        feedback_policy(game)
        scored = self.score(game)
        stage = [s for s in scored["stages"] if s["task_id"] == "T3"][0]
        self.assertTrue(stage["first_any"]["correct"])
        self.assertTrue(scored["tasks"][-1]["success"])
        self.assertFalse(scored["tasks"][-1]["strict_success"])

    def test_any_matching_instance_is_valid_for_strict_success(self):
        for profile_station, vegetation_station in (("C1", "A1"), ("C2", "A2")):
            with self.subTest(stations=(profile_station, vegetation_station)):
                game = StationGame(map_world(self.design), self.design)
                game.start_task("T3")
                walk(game, "Q"); walk(game, profile_station); game.step({"type": "process"})
                walk(game, "V"); walk(game, vegetation_station); game.step({"type": "process"})
                walk(game, "C"); game.step({"type": "submit"})
                task = self.score(game)["tasks"][0]
                self.assertTrue(task["strict_success"])
                self.assertEqual(task["wrong_station_entry_count"], 0)
                self.assertIsNone(task["strict_failure_reason"])

    def test_matching_stations_without_submission_still_fail(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T3")
        walk(game, "Q"); walk(game, "C1"); game.step({"type": "process"})
        walk(game, "V"); walk(game, "A1"); game.step({"type": "process"})
        game.step({"type": "abandon"})
        task = self.score(game)["tasks"][0]
        self.assertEqual(task["wrong_station_entry_count"], 0)
        self.assertFalse(task["strict_success"])
        self.assertEqual(task["strict_failure_reason"], "task_not_completed")

    def test_failed_source_with_feedback_can_support_future_use(self):
        game = self.game_with_history()
        game.start_task("T3"); feedback_policy(game)
        scored = self.score(game)
        self.assertFalse(scored["tasks"][0]["success"])
        later = [s for s in scored["stages"] if s["task_id"] == "T3"]
        self.assertTrue(all(s["historical_matching_opportunity"] for s in later))
        self.assertTrue(all(s["historical_unreacquired_first_match"] for s in later))

    def test_first_stage_processing_is_not_automatically_a_second_stage_refresh(self):
        game = self.game_with_history()
        game.start_task("T3"); feedback_policy(game)
        stage = self.score(game)["stages"][-1]
        self.assertEqual(stage["required_kind"], "vegetation")
        self.assertFalse(stage["current_session_independently_determines_answer"])

    def test_actual_same_session_answer_is_separated_from_historical_reuse(self):
        game = self.game_with_history()
        game.start_task("T3")
        walk(game, "Q"); walk(game, "A1"); game.step({"type": "inspect"})
        walk(game, "C1"); game.step({"type": "process"})
        feedback_policy(game)
        stage = self.score(game)["stages"][-1]
        self.assertTrue(stage["first_any"]["correct"])
        self.assertTrue(stage["current_session_independently_determines_answer"])
        self.assertFalse(stage["historical_unreacquired_first_match"])

    def test_precollection_inspect_mismatch_counts_for_first_any_sensitivity(self):
        game = self.game_with_history()
        game.start_task("T3")
        walk(game, "B1"); game.step({"type": "inspect"})
        feedback_policy(game)
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertFalse(stage["first_any"]["correct"])
        self.assertTrue(stage["first_postcollection"]["correct"])

    def test_inferred_evidence_is_eligible_but_has_no_invented_direct_source_gap(self):
        game = self.game_with_history(("A1", "B1", "D1"))
        game.start_task("T3"); feedback_policy(game)
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertTrue(stage["historical_matching_opportunity"])
        self.assertTrue(stage["matching_known_only_by_inference"])
        self.assertIsNone(stage["environment_feedback_gap"])
        self.assertFalse(stage["unrefreshed_direct_source_opportunity"])

    def test_repeated_error_requires_an_earlier_session_and_same_material_type_pair(self):
        game = self.game_with_history()
        game.start_task("T3"); walk(game, "A1"); game.step({"type": "inspect"})
        game.step({"type": "abandon"})
        scored = self.score(game)
        old = scored["stages"][0]
        later = [s for s in scored["stages"] if s["task_id"] == "T3"][0]
        self.assertFalse(old["negative_selection_feedback"]["has_prior_error_feedback"])
        self.assertTrue(later["negative_selection_feedback"]["first_choice_repeats_error"])
        self.assertFalse(later["negative_process_feedback"]["has_prior_error_feedback"])

    def test_closed_known_nonmatching_spurs_use_actual_nonoverlapping_graph_edges(self):
        game = self.game_with_history(("A1", "B1", "C1"))
        game.start_task("T3"); walk(game, "Q"); walk(game, "B1")
        game.step({"type": "inspect"}); feedback_policy(game)
        scored = self.score(game)
        trips = [t for t in scored["station_trips"] if t["task_id"] == "T3" and t["historically_redundant_nonmatching"]]
        self.assertTrue(trips)
        chosen = [e for t in trips for e in t["move_event_ids"]]
        self.assertEqual(len(chosen), len(set(chosen)))
        by_id = {e["event_id"]: e for e in game.events}
        self.assertEqual(sum(t["distance"] for t in trips), sum(by_id[e]["movement_cost"] for e in chosen))
        self.assertTrue(all(t["historical_information_gain_bits"] == 0 and not t["task_progressed"] for t in trips))
        self.assertGreaterEqual(scored["tasks"][-1]["other_distance_excess_over_physical_bound"], 0)

    def test_a_repeated_bad_station_query_is_not_a_repeated_failed_process(self):
        game = self.game_with_history()
        game.start_task("T3"); walk(game, "A1"); game.step({"type": "inspect"})
        feedback_policy(game)
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertTrue(stage["negative_selection_feedback"]["any_entry_repeats_error"])
        self.assertFalse(stage["negative_selection_feedback"]["any_process_repeats_error"])

    def test_actual_repeated_unsupported_processing_is_counted_separately(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T1"); walk(game, "P"); walk(game, "A1")
        game.step({"type": "process"}); game.step({"type": "abandon"})
        game.start_task("T3"); walk(game, "Q"); walk(game, "A1")
        game.step({"type": "process"}); game.step({"type": "abandon"})
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertTrue(stage["negative_process_feedback"]["any_process_repeats_error"])

    def test_intervening_logical_rediscovery_is_a_retention_refresh(self):
        game = self.game_with_history()
        game.start_task("T2")
        for station in ("A1", "B1", "D1"):
            walk(game, station); game.step({"type": "inspect"})
        game.step({"type": "abandon"})
        game.start_task("T3"); feedback_policy(game)
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertEqual(stage["last_direct_source_task"], "T1")
        self.assertEqual(stage["environment_feedback_gap"], 1)
        self.assertTrue(stage["intervening_feedback_independently_refreshes_answer"])
        self.assertFalse(stage["unrefreshed_direct_source_opportunity"])

    def test_informative_exploration_is_not_a_redundant_memory_spur(self):
        game = self.game_with_history(("C1",))
        game.start_task("T3"); walk(game, "Q"); walk(game, "B1")
        game.step({"type": "inspect"}); feedback_policy(game)
        trips = [t for t in self.score(game)["station_trips"] if t["task_id"] == "T3" and t["station"] == "B1"]
        self.assertTrue(trips)
        self.assertTrue(trips[0]["novel_information_nonmatching"])
        self.assertFalse(trips[0]["historically_redundant_nonmatching"])

    def test_source_gap_uses_session_order_not_numeric_task_names(self):
        game = self.game_with_history()
        game.start_task("T3"); feedback_policy(game)
        stage = [s for s in self.score(game)["stages"] if s["task_id"] == "T3"][0]
        self.assertEqual(stage["environment_feedback_gap"], 0)

    def test_trace_identity_and_condition_labels_cannot_create_memory_gain(self):
        game = self.game_with_history(); game.start_task("T3"); feedback_policy(game)
        a, b = self.score(game, "retain"), self.score(game, "clear")
        self.assertEqual(summarize_stages(a["stages"]), summarize_stages(b["stages"]))
        for cohort in compare_streams(a, b)["cohorts"].values():
            self.assertEqual(cohort["mean_signed_physical_efficiency_lift"], 0)
            self.assertEqual(cohort["both_success_distance_reduction"], 0)
            self.assertEqual(cohort["strict_success_rate_lift"], 0)
            self.assertEqual(cohort["processing_accuracy_lift"], 0)

    def test_signed_contrast_changes_sign_on_label_swap(self):
        game = self.game_with_history(); game.start_task("T3"); feedback_policy(game)
        a = self.score(game)
        b = deepcopy(a)
        b["condition"] = "clear"
        b["tasks"][-1]["physical_efficiency"] *= .5
        b["tasks"][-1]["distance"] += 8
        b["tasks"][-1]["strict_success"] = False
        b["tasks"][-1]["processing_attempt_count"] += 1
        forward, reverse = compare_streams(a, b), compare_streams(b, a)
        for key in ("mean_signed_physical_efficiency_lift", "mean_signed_distance_saved_per_physical_bound",
                    "strict_success_rate_lift", "processing_accuracy_lift"):
            self.assertEqual(forward["cohorts"]["followup"][key], -reverse["cohorts"]["followup"][key])

    def test_inconsistent_feedback_is_rejected_instead_of_granting_an_opportunity(self):
        ev = Evidence(self.design)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            ev.worlds((("A1", "profile"), ("A1", "vegetation")))


if __name__ == "__main__":
    unittest.main()
