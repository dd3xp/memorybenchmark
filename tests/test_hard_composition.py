"""Behavioral checks for typed operations, independent stages and planned reuse."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_composition import validate_allocation
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import StationSession

DATA = Path(__file__).resolve().parents[1] / "memorybenchmark/data"


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design(DATA / "orcia_hard36.json")

    def station(self, kind, requirement):
        world = self.design["private_worlds"][map_world(self.design)]
        return next(
            s for s, capability in world.items() if kind in capability[requirement]
        )

    def test_all_three_maps_keep_geometry_and_balanced_experiences(self):
        for name in ("orcia", "hampi", "angkor"):
            with self.subTest(map=name):
                old = load_design(DATA / (name + "_hard48.json"))
                new = load_design(DATA / (name + "_hard36.json"))
                self.assertEqual(old["public"]["locations"], new["public"]["locations"])
                self.assertEqual(old["public"]["edges"], new["public"]["edges"])
                self.assertEqual(
                    old["private_station_capabilities"],
                    new["private_station_capabilities"],
                )
                allocation = validate_allocation(new)
                self.assertEqual(allocation["necessary_operations"], 96)
                self.assertEqual(allocation["tasks"], 36)

    def test_combination_requires_both_operations_and_does_not_advance_early(self):
        game = StationGame(map_world(self.design), self.design)
        game.start_task("T13")
        stage = game.task["stages"][0]
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, self.station(stage["required_kind"], "catalogue"))
        first = game.step({"type": "process"})
        self.assertEqual(game.state.stage, 0)
        self.assertFalse(game.state.processed)
        self.assertEqual(game.state.material_state, "catalogued")
        self.assertEqual(first["feedback"]["requirement"], "catalogue")
        walk(game, self.station(stage["required_kind"], "verify"))
        second = game.step({"type": "process"})
        self.assertEqual(second["feedback"]["next_stage"], 2)
        self.assertEqual(game.state.stage, 1)
        self.assertFalse(game.state.raw)
        self.assertIsNone(game.state.material_state)

    def test_prepared_input_needs_only_second_operation(self):
        design = deepcopy(self.design)
        stage = design["tasks"]["T1"]["stages"][1]
        task = design["tasks"]["T1"]
        task["stages"] = [stage]
        task.update(stage)
        game = StationGame(map_world(design), design)
        game.start_task("T1")
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, self.station(stage["required_kind"], "verify"))
        feedback = game.step({"type": "process"})["feedback"]
        self.assertTrue(game.state.processed)
        self.assertEqual(feedback["operation_completed"], "verify")

    def test_first_operation_only_is_legitimate_delivery_goal(self):
        design = deepcopy(self.design)
        stage = design["tasks"]["T1"]["stages"][0]
        task = design["tasks"]["T1"]
        task["stages"] = [stage]
        task.update(stage)
        game = StationGame(map_world(design), design)
        game.start_task("T1")
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, self.station(stage["required_kind"], "catalogue"))
        game.step({"type": "process"})
        walk(game, task["submit_at"])
        game.step({"type": "submit"})
        self.assertTrue(game.state.success)

    def test_both_prerequisites_must_appear_in_earlier_tasks(self):
        design = deepcopy(self.design)
        design["tasks"]["T1"]["stages"][0] = deepcopy(
            design["tasks"]["T13"]["stages"][0]
        )
        with self.assertRaises(ValueError):
            validate_allocation(design)

    def test_public_text_explains_input_and_goal_without_revealing_station(self):
        game = StationGame(map_world(self.design), self.design)
        session = StationSession(game, "T13", feedback_mode="compact")
        self.assertIn("原始资料", session.initial["text"])
        self.assertIn("已核验资料", session.initial["text"])
        for operation in ("catalogue", "verify"):
            self.assertIn(
                self.design["public"]["requirements"][operation],
                session.initial["text"],
            )
        self.assertNotIn("private_station_capabilities", session.initial["text"])


if __name__ == "__main__":
    unittest.main()
