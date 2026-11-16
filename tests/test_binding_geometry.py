"""A route review cannot silently alter geography or claim an agent score."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.assess_binding_geometry import assess
from scripts.build_hard_calibration import build


class BindingGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "memorybenchmark/data/orcia_hard36.json"
            ).read_text(encoding="utf-8")
        )
        cls.candidate = build(seed=61501, variant="binding", full=True)

    def test_known_paths_and_global_optima_are_distinct_readonly_endpoints(self):
        before = deepcopy(self.candidate)
        result = assess(self.candidate, self.original)
        self.assertEqual(self.candidate, before)
        self.assertEqual(result["model_calls"], 0)
        self.assertTrue(result["is_not_a_model_score"])
        self.assertTrue(result["targets_unchanged"])
        self.assertLessEqual(
            result["on_a_fully_informed_shortest_path"],
            result["useful_given_a_known_valid_type_path"],
        )
        self.assertLessEqual(result["maximum_fully_informed_actions"], 352)

    def test_an_unreviewed_road_change_is_rejected_instead_of_compared_as_orcia(self):
        changed = deepcopy(self.candidate)
        changed["public"]["edges"][0][2] += 1
        with self.assertRaisesRegex(ValueError, "unchanged Orcia"):
            assess(changed, self.original)


if __name__ == "__main__":
    unittest.main()
