"""Contracts for removing regional constraints and reusing specific outcomes."""

import json
from pathlib import Path
import unittest

from memorybenchmark.map_catalog import station_design
from memorybenchmark.prototypes.composition_lab import plans
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_interfaces import item, world
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import StationSession
from scripts.build_hard_calibration import validate
from scripts.build_lunatic_recall import DATA, pilot


class LunaticRecallTests(unittest.TestCase):
    def test_all_candidate_maps_keep_geography_and_drop_processing_zones(self):
        for theme in ("scandinavia", "mongolia", "andes"):
            with self.subTest(theme=theme):
                path = station_design(f"{theme}-lunatic")
                current = load_design(path)
                previous = load_design(DATA / f"{theme}_lunatic64.json")
                public = current["public"]
                old = previous["public"]
                for key in ("edges", "ferry_edges", "view_box", "kinds"):
                    self.assertEqual(public[key], old[key])
                self.assertEqual(public["locations"].keys(), old["locations"].keys())
                self.assertNotIn("processing_regions", public)
                for key, place in public["locations"].items():
                    self.assertNotIn("region_category", place)
                    self.assertEqual(
                        (place["x"], place["y"]),
                        (old["locations"][key]["x"], old["locations"][key]["y"]),
                    )
                for task in current["tasks"].values():
                    self.assertNotIn("required_region", task)
                    self.assertNotIn("required_region", task["stages"][0])
                    self.assertNotIn("required_region", task["stages"][1])
                self.assertEqual(len(current["tasks"]), 64)

    def test_same_goal_wrong_material_path_succeeds_locally_but_cannot_advance(self):
        design = load_design(station_design("scandinavia-lunatic"))
        game = StationGame(map_world(design), design)
        session = StationSession(game, "T33", feedback_mode="compact")
        visible = json.dumps(session.initial, ensure_ascii=False)
        self.assertIn("交付目标", visible)
        self.assertNotIn("private_interfaces", visible)
        first, second = game.task["stages"]
        self.assertEqual(first["goal"], second["goal"])

        def process_path(path):
            walk(game, first["target"])
            game.step({"type": "survey"})
            for station_type in path:
                walk(
                    game, design["public"]["station_types"][station_type]["stations"][0]
                )
                feedback = game.step({"type": "process"})["feedback"]
                self.assertEqual(feedback["result"], "processed")
                self.assertNotIn("capability", feedback)
            return feedback

        engine = world(design)
        wrong = process_path(plans(engine, item(second))[0])
        self.assertNotEqual(wrong["output_format"], first["goal"])
        self.assertEqual(game.state.stage, 0)
        right = process_path(plans(engine, item(first))[0])
        self.assertEqual(right["output_format"], first["goal"])
        self.assertEqual(game.state.stage, 1)
        self.assertFalse(game.state.raw)
        self.assertIsNone(game.state.material_state)

    def test_published_pilot_preserves_identical_full_map_rules_and_real_prerequisites(
        self,
    ):
        full = json.loads(station_design("scandinavia-lunatic").read_bytes())
        selected = pilot(full)
        deployed = DATA / "calibration/scandinavia_lunatic_recall12.json"
        self.assertEqual(selected, json.loads(deployed.read_bytes()))
        self.assertEqual(selected["private_interfaces"], full["private_interfaces"])
        self.assertEqual(selected["evaluation"]["allocation"]["combined_stages"], 8)
        self.assertGreater(
            selected["evaluation"]["allocation"]["shortest_prior_experience_gap_tasks"],
            1,
        )

    def test_goal_switch_adds_both_standards_as_ordinary_then_combined_experience(self):
        full = json.loads(station_design("scandinavia-lunatic").read_bytes())
        previous = pilot(full)
        candidate = pilot(full, goal_switch=True)
        deployed = DATA / "calibration/scandinavia_lunatic_goal_switch18.json"
        self.assertEqual(candidate, json.loads(deployed.read_bytes()))
        self.assertEqual(
            candidate["private_interfaces"], previous["private_interfaces"]
        )
        self.assertEqual(
            candidate["public"],
            {**previous["public"], "version": candidate["design_id"]},
        )
        source_tasks = candidate["provenance"]["pilot_from_tasks"]
        self.assertEqual(
            [
                task_id
                for task_id in source_tasks
                if task_id in previous["provenance"]["pilot_from_tasks"]
            ],
            previous["provenance"]["pilot_from_tasks"],
        )
        proof = validate(candidate)
        self.assertEqual(proof["successes"], len(candidate["tasks"]))
        self.assertTrue(proof["actual_prior_feedback_for_every_combined_operation"])
        self.assertLess(proof["maximum_reference_actions"], 352)


if __name__ == "__main__":
    unittest.main()
