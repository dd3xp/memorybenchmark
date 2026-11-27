import unittest

from memorybenchmark.prototypes.composition_lab import (
    SEAL_MATCH,
    Stage,
    input_for_stage,
)
from memorybenchmark.prototypes.station_interfaces import world
from scripts.build_lunatic_independent_seals import assess, build, source_design


class IndependentSealsTests(unittest.TestCase):
    def test_only_four_verifier_seals_and_version_metadata_change(self):
        source = source_design()
        candidate = build()
        self.assertEqual(list(candidate["tasks"]), list(source["tasks"]))
        before = source["private_interfaces"]["seal_comparison"].pop("verify")
        after = candidate["private_interfaces"]["seal_comparison"].pop("verify")
        self.assertEqual(
            {
                (material, station)
                for material, by_station in before.items()
                for station, seal in by_station.items()
                if seal != after[material][station]
            },
            {("lithology", "E"), ("lithology", "O"), ("shore", "Q"), ("shore", "T")},
        )
        for design in (source, candidate):
            for field in ("design_id", "status", "fixed_world", "provenance"):
                del design[field]
            del design["public"]["version"]
        self.assertEqual(candidate, source)

    def test_guessed_inversion_now_fails_for_two_materials(self):
        for design, expected in ((source_design(), 4), (build(), 2)):
            rules = world(design)
            inverted_formats = sum(
                input_for_stage(
                    rules,
                    Stage(
                        material,
                        "combined",
                        "standard-1",
                        delivery_condition=SEAL_MATCH,
                    ),
                )
                != input_for_stage(
                    rules,
                    Stage(
                        material,
                        "combined",
                        "standard-2",
                        delivery_condition=SEAL_MATCH,
                    ),
                )
                for material in rules.verifier_seals
            )
            self.assertEqual(inverted_formats, expected)

    def test_real_game_prior_feedback_and_unchanged_fully_informed_travel(self):
        proof = assess(build())
        self.assertEqual(proof["successes"], 20)
        self.assertEqual(proof["required_operations"], 56)
        self.assertEqual(
            proof["feedback_only_repeat_operations_by_encounter"], {"2": 24, "3": 8}
        )
        self.assertTrue(proof["actual_prior_feedback_for_every_combined_operation"])
        self.assertEqual(proof["valid_standard_wrong_relation_routes"], 32)
        self.assertEqual(
            proof["fully_informed_travel_distance_v46"],
            proof["fully_informed_travel_distance_v47"],
        )


if __name__ == "__main__":
    unittest.main()
