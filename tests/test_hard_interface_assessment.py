"""Candidate assessment must remain isolated from production experiment maps."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest

from scripts.assess_hard_interfaces import POLICY, assessment


ROOT = Path(__file__).resolve().parents[1]


class HardInterfaceAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.source = ROOT / cls.policy["geography_design"]
        cls.before = sha256(cls.source.read_bytes()).hexdigest()
        cls.result = assessment(cls.policy)

    def test_old_hard_cartesian_product_has_no_interface_restriction(self):
        result = self.result["current_hard_cartesian_property"]
        self.assertGreater(result["locally_valid_station_pairs"], 0)
        self.assertEqual(
            result["compatible_pairs"], result["locally_valid_station_pairs"]
        )

    def test_original_orcia_routes_fit_without_editing_roads_or_targets(self):
        result = self.result["orcia_route_projection"]
        self.assertEqual(result["tasks_with_a_reference_route_inside_budget"], 36)
        self.assertFalse(result["roads_changed"])
        self.assertFalse(result["task_targets_changed"])
        self.assertTrue(
            all(r["reference_actions"] <= r["budget"] for r in result["tasks"])
        )
        self.assertEqual(sha256(self.source.read_bytes()).hexdigest(), self.before)

    def test_diagnostic_is_not_an_agent_result_or_a_launch_authorization(self):
        self.assertEqual(self.result["model_calls"], 0)
        self.assertIsNone(self.result["target_model_gap_observed"])
        self.assertFalse(self.policy["calibration"]["launch_authorized_by_this_file"])
        self.assertTrue(
            self.result["candidate"][
                "choice_enumeration_is_not_a_policy_or_agent_score"
            ]
        )
        self.assertEqual(self.result["candidate"]["fully_informed_stage_successes"], 72)

    def test_target_review_preserves_geography_and_original_collection_counts(self):
        review = self.result["orcia_target_review"]
        self.assertTrue(review["original_target_multiset_preserved"])
        self.assertFalse(review["roads_changed"])
        self.assertFalse(review["model_outcomes_used_for_target_search"])
        self.assertGreaterEqual(
            review["strict_shortest_route_useful_stations"],
            self.result["orcia_route_projection"][
                "strict_shortest_route_useful_stations"
            ],
        )
        original = [
            x
            for row in self.result["orcia_route_projection"]["tasks"]
            for x in row["targets"]
        ]
        proposed = [x for row in review["tasks"] for x in row["targets"]]
        self.assertEqual(sorted(original), sorted(proposed))
        self.assertEqual(sha256(self.source.read_bytes()).hexdigest(), self.before)

    def test_other_geographies_and_silent_allocation_changes_are_rejected(self):
        changed = deepcopy(self.policy)
        changed["geography_review"] = "all"
        with self.assertRaisesRegex(ValueError, "individual"):
            assessment(changed)
        changed = deepcopy(self.policy)
        changed["materials"] = 12
        with self.assertRaisesRegex(ValueError, "contract"):
            assessment(changed)
