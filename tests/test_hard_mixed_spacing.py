"""The Orcia timing candidate preserves the fourth version's individual commissions."""

import json
import unittest

from memorybenchmark.prototypes.composition_lab import experience_keys
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.build_hard_calibration import validate
from scripts.build_hard_mixed_spacing import BASE, build, experience_history, repeat_gap


class HardMixedSpacingTests(unittest.TestCase):
    def test_reorder_preserves_commissions_and_third_encounter_gaps(self):
        original = json.loads(BASE.read_bytes())
        earlier = experience_history(original)
        for schedule in ("mixed-spacing", "staged-composition"):
            with self.subTest(schedule=schedule):
                candidate = build(schedule)
                self.assertEqual(candidate["tasks"], original["tasks"])
                self.assertNotEqual(list(candidate["tasks"]), list(original["tasks"]))
                self.assertEqual(
                    candidate["private_interfaces"], original["private_interfaces"]
                )
                original_public = dict(
                    original["public"], version=candidate["design_id"]
                )
                self.assertEqual(candidate["public"], original_public)
                self.assertEqual(
                    candidate["native_session_budget"],
                    original["native_session_budget"],
                )
                later = experience_history(candidate)
                for key, occurrences in later.items():
                    self.assertEqual(
                        [task for task, _ in occurrences],
                        [task for task, _ in earlier[key]],
                    )
                    if len(occurrences) == 3:
                        self.assertEqual(
                            repeat_gap(occurrences, 3), repeat_gap(earlier[key], 3)
                        )

    def test_original_mixed_spacing_preserves_both_short_and_long_encounters(self):
        gaps = build()["evaluation"]["allocation"]["repeat_gap_histogram"]["2"]
        self.assertEqual(sum(n for gap, n in gaps.items() if gap <= 7), 16)
        self.assertEqual(sum(n for gap, n in gaps.items() if gap >= 15), 16)

    def test_staged_schedule_introduces_six_materials_and_keeps_gap_variation(self):
        candidate = build("staged-composition")
        interfaces = world(candidate)
        tasks = list(candidate["tasks"].values())
        introduction = [item(part) for task in tasks[:12] for part in task["stages"]]
        self.assertTrue(all(part.mode != "combined" for part in introduction))
        keys = {
            key for part in introduction for key in experience_keys(part, interfaces)
        }
        materials = {key[0] for key in keys}
        self.assertEqual(len(materials), 6)
        for material in materials:
            self.assertEqual(sum(key[0] == material for key in keys), 4)
        self.assertTrue(
            all(item(part).mode == "combined" for part in tasks[12]["stages"])
        )
        gaps = candidate["evaluation"]["allocation"]["repeat_gap_histogram"]["2"]
        self.assertEqual(sum(n for gap, n in gaps.items() if 2 <= gap <= 7), 14)
        self.assertEqual(sum(n for gap, n in gaps.items() if 8 <= gap <= 14), 20)
        self.assertEqual(sum(n for gap, n in gaps.items() if gap >= 15), 6)

    def test_combination_requires_the_other_goal_to_have_been_taught_too(self):
        candidate = build()
        candidate["tasks"]["T16"] = candidate["tasks"].pop("T16")
        with self.assertRaisesRegex(ValueError, "T21.*both goals"):
            experience_history(candidate)

    def test_reference_uses_earlier_delivered_feedback_at_both_repetitions(self):
        for schedule in ("mixed-spacing", "staged-composition"):
            with self.subTest(schedule=schedule):
                proof = validate(build(schedule), feedback_only_repeats=True)
                self.assertEqual(proof["successes"], 36)
                self.assertEqual(proof["required_operations"], 96)
                self.assertLessEqual(proof["maximum_reference_actions"], 352)
                self.assertEqual(
                    proof["feedback_only_repeat_operations_by_encounter"],
                    {"2": 40, "3": 16},
                )


if __name__ == "__main__":
    unittest.main()
