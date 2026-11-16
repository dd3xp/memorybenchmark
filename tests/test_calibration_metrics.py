"""Do not turn missing prior facts or a different goal scope into forgetting."""

from copy import deepcopy
import unittest

from memorybenchmark.experiments.calibration import summarize, choose_followup


def fixture():
    rows = []
    for i in range(2):
        operations = [
            {
                "stage_index": 0,
                "material": "kind",
                "operation": "catalogue",
                "scope_format": "F1",
                "goal": "F1" if i == 0 else "standard-1",
                "first_processing_correct": True,
                "prior_matching_feedback": i > 0,
            }
        ]
        stages = [
            {"stage_index": 0, "combined": False, "whole_stage_first_correct": True}
        ]
        if i:
            operations.append(
                {
                    "stage_index": 0,
                    "material": "kind",
                    "operation": "verify",
                    "scope_format": "F1",
                    "goal": "standard-1",
                    "first_processing_correct": False,
                    "prior_matching_feedback": False,
                }
            )
            stages = [
                {"stage_index": 0, "combined": True, "whole_stage_first_correct": False}
            ]
        rows.append(
            {
                "processing_operations": operations,
                "necessary_operation_denominator": len(operations),
                "stage_outcomes": stages,
            }
        )
    return {
        "status": "completed_and_audited",
        "tasks": 2,
        "successes": 1,
        "condition": "retain",
        "rows": rows,
        "totals": {"distance": 10, "llm_calls": 8, "unsupported_processing_count": 1},
    }


class CalibrationMetricTests(unittest.TestCase):
    def test_catalogue_goal_and_final_standard_are_not_two_different_experiences(self):
        value = summarize(fixture())
        self.assertEqual(value["goal_classes"], 2)
        self.assertEqual(value["after_first_planned_goal_encounter"]["denominator"], 1)

    def test_missing_prior_feedback_is_not_scored_as_forgotten_experience(self):
        value = summarize(fixture())
        self.assertEqual(
            value["combined_with_both_prior_actual_facts"]["denominator"], 0
        )
        self.assertIsNone(value["combined_with_both_prior_actual_facts"]["rate"])
        self.assertEqual(value["combinations_without_both_prior_actual_facts"], 1)
        self.assertEqual(
            value["all_first_goal_compatible_operations"]["denominator"], 3
        )

    def test_unattempted_required_operation_cannot_be_dropped(self):
        result = fixture()
        result["rows"][1]["processing_operations"].pop()
        with self.assertRaisesRegex(ValueError, "omitted"):
            summarize(result)

    def test_missing_transport_costs_remain_unknown_not_zero(self):
        value = summarize(fixture())
        self.assertIsNone(value["infrastructure_costs"])

    def test_saturated_retained_pilot_selects_binding_and_gap_selects_confirmation(
        self,
    ):
        value = {
            "condition": "retain",
            "tasks": {"denominator": 12},
            "combined_with_both_prior_actual_facts": {"denominator": 8, "rate": 1.0},
            "after_first_planned_goal_encounter": {"denominator": 24, "rate": 0.85},
        }
        self.assertEqual(choose_followup(value)["variant"], "binding")
        value["combined_with_both_prior_actual_facts"]["rate"] = 0.75
        self.assertEqual(choose_followup(value)["variant"], "interface-confirmation")

    def test_one_combination_error_without_repeat_gap_does_not_pass_screening(self):
        value = {
            "condition": "retain",
            "tasks": {"denominator": 12},
            "combined_with_both_prior_actual_facts": {"denominator": 8, "rate": 0.875},
            "after_first_planned_goal_encounter": {"denominator": 24, "rate": 23 / 24},
        }
        self.assertEqual(choose_followup(value)["variant"], "binding")
