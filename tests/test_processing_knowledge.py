"""Check the private rule table against actual environment feedback."""

import json
import unittest

from memorybenchmark.map_catalog import map_detail, station_design
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_routes import walk
from operations.processing_knowledge import observed_processing, processing_table


class ProcessingKnowledgeTests(unittest.TestCase):
    def test_four_tiers_share_columns_while_preserving_native_rule_shapes(self):
        for map_id, outputs, count in (
            ("capulin-easy", {"processed"}, 8),
            ("nessie-normal", {"processed"}, 24),
            ("orcia-hard", {"catalogued", "verified"}, 48),
            ("scandinavia-lunatic", {"F-1", "F-2", "standard-1", "standard-2"}, 128),
        ):
            with self.subTest(map_id=map_id):
                design = load_design(station_design(map_id))
                table = processing_table(design)
                self.assertEqual({r["output_spec"] for r in table["rules"]}, outputs)
                self.assertEqual(len(table["rules"]), count)
                self.assertEqual(
                    table["processing_table_sha256"],
                    processing_table(load_design(station_design(map_id)))[
                        "processing_table_sha256"
                    ],
                )
                self.assertNotIn(
                    "processing_table_sha256", json.dumps(map_detail(map_id))
                )

    def test_full_capability_disclosure_and_later_first_reuse_are_distinct(self):
        design = load_design(station_design("capulin-easy"))
        table = processing_table(design)
        game = StationGame(map_world(design), design)
        stage = design["tasks"]["T1"]["stages"][0]
        rule = next(
            r for r in table["rules"] if r["material"] == stage["required_kind"]
        )
        wrong = next(r for r in table["rules"] if r["material"] != rule["material"])

        def process(route):
            walk(game, table["operators"][route["operator"]][0])
            return game.step({"type": "process"})["feedback"]["result"]

        for task_number in range(2):
            game.start_task("T1")
            walk(game, stage["target"])
            game.step({"type": "survey"})
            if task_number == 0:
                self.assertEqual(process(wrong), "unsupported")
            self.assertEqual(process(rule), "processed")
            game.step({"type": "abandon"})

        result = observed_processing(design, table, game.events)
        self.assertEqual(result["required_opportunities"], 4)
        self.assertEqual(result["distinct_rules_disclosed"], 2)
        self.assertEqual(result["first_correct"], 1)
        self.assertEqual(result["first_correct_after_prior_rule_disclosure"], 1)
        failed, corrected, repeated = result["attempts"]
        self.assertIsNone(failed["rule_id"])
        self.assertEqual(result["disclosures"][0]["rule_ids"], [wrong["rule_id"]])
        self.assertIsNone(corrected["same_rule_disclosed_in_earlier_task_event_id"])
        self.assertEqual(
            repeated["same_rule_disclosed_in_earlier_task_event_id"],
            corrected["event_id"],
        )
        self.assertEqual(
            result["opportunities"][2]["prior_disclosure_events"],
            {rule["rule_id"]: corrected["event_id"]},
        )

    def test_wrong_but_supported_intermediate_discloses_only_actual_rule(self):
        design = load_design(station_design("scandinavia-lunatic"))
        table = processing_table(design)
        game = StationGame(map_world(design), design)
        stage = design["tasks"]["T1"]["stages"][0]
        wrong = next(
            r
            for r in table["rules"]
            if r["material"] == stage["required_kind"]
            and r["operation"] == "catalogue"
            and r["output_spec"] != stage["goal"]
        )
        game.start_task("T1")
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, table["operators"][wrong["operator"]][0])
        self.assertEqual(
            game.step({"type": "process"})["feedback"]["result"], "processed"
        )
        game.step({"type": "abandon"})

        result = observed_processing(design, table, game.events)
        (attempt,) = result["attempts"]
        (disclosure,) = result["disclosures"]
        self.assertEqual(disclosure["rule_ids"], [wrong["rule_id"]])
        self.assertTrue(attempt["first_attempt"])
        self.assertFalse(attempt["goal_compatible"])
        self.assertFalse(result["opportunities"][0]["first_correct"])
        self.assertIsNone(result["opportunities"][1]["first_attempt_event_id"])


if __name__ == "__main__":
    unittest.main()
