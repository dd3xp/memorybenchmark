import unittest
from dataclasses import replace

from memorybenchmark.prototypes.composition_lab import plans
from memorybenchmark.prototypes.station_capability import StationGame, map_world
from memorybenchmark.prototypes.station_interfaces import item, load, world
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import render_text
from scripts.build_lunatic_seal_comparison import SEALS, assess, build


class SealComparisonTests(unittest.TestCase):
    def test_real_reference_composes_previously_delivered_seals(self):
        proof = assess(build())
        self.assertEqual(proof["successes"], 20)
        self.assertEqual(proof["required_operations"], 56)
        self.assertEqual(proof["matched_relation_pairs"], 8)
        self.assertEqual(proof["commissions_with_same_relation_in_both_stages"], 4)
        self.assertEqual(proof["valid_standard_wrong_relation_routes"], 32)
        self.assertTrue(proof["actual_prior_feedback_for_every_combined_operation"])

    def test_changing_either_observed_seal_changes_compatible_stations(self):
        design = build()
        engine = world(design)
        stage = item(design["tasks"]["T13"]["stages"][0])
        opposite = dict(zip(SEALS, reversed(SEALS), strict=True))
        flipped_catalogue = replace(
            engine,
            catalogue_seals={k: opposite[v] for k, v in engine.catalogue_seals.items()},
        )
        flipped_verifier = replace(
            engine,
            verifier_seals={
                material: {k: opposite[v] for k, v in by_type.items()}
                for material, by_type in engine.verifier_seals.items()
            },
        )
        expected = set(plans(engine, stage))
        for variant in (flipped_catalogue, flipped_verifier):
            candidate = set(plans(variant, stage))
            self.assertTrue(candidate)
            self.assertFalse(expected & candidate)
        self.assertEqual(
            plans(flipped_catalogue, stage), plans(flipped_verifier, stage)
        )

    def test_wrong_relation_is_visible_and_does_not_complete_stage(self):
        design = load(build())
        game = StationGame(map_world(design), design)
        task = design["tasks"]["T13"]
        first = task["stages"][0]
        alternate = next(
            stage
            for other in design["tasks"].values()
            for stage in other["stages"]
            if stage["required_kind"] == first["required_kind"]
            and stage["target"] == first["target"]
            and stage["goal"] == first["goal"]
            and stage.get("delivery_condition") is not None
            and stage["delivery_condition"] != first["delivery_condition"]
        )
        engine = world(design)
        game.start_task("T13")

        def survey():
            walk(game, first["target"])
            game.step({"type": "survey"})

        def process(station_type):
            walk(game, design["public"]["station_types"][station_type]["stations"][0])
            return game.step({"type": "process"})

        survey()
        catalogue, verifier = plans(engine, item(alternate))[0]
        issued = process(catalogue)
        self.assertIn("编目封签", render_text(issued, compact=True))
        self.assertNotIn("delivery_condition", issued["feedback"])
        rejected = process(verifier)
        self.assertEqual(rejected["feedback"]["output_format"], first["goal"])
        self.assertEqual(
            rejected["feedback"]["delivery_condition"], alternate["delivery_condition"]
        )
        self.assertIn("核验封签", render_text(rejected, compact=True))
        self.assertIn("交付条件不符", render_text(rejected, compact=True))
        self.assertEqual(game.state.stage, 0)

        survey()
        for station_type in plans(engine, item(first))[0]:
            process(station_type)
        self.assertEqual(game.state.stage, 1)
        self.assertIsNone(game.state.material_state)
        self.assertFalse(game.state.raw)
