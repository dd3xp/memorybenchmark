from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from memorybenchmark.prototypes.composition_lab import experience_keys, plans
from memorybenchmark.prototypes.station_capability import StationGame, map_world
from memorybenchmark.prototypes.station_interfaces import analyze, item, load, world
from memorybenchmark.prototypes.station_pilot import replay_checkpoint
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import render_text
from scripts.build_lunatic_verifier_conditions import assess, build


class VerifierConditionsTests(unittest.TestCase):
    def test_all_twenty_commissions_have_prior_feedback_routes(self):
        assessment = assess(build())
        self.assertEqual(assessment["successes"], 20)
        self.assertEqual(assessment["same_format_pairs"], 4)
        self.assertEqual(assessment["split_format_pairs"], 4)
        self.assertEqual(assessment["required_operations"], 56)
        self.assertTrue(assessment["actual_prior_feedback_for_every_combined_operation"])
        self.assertLessEqual(assessment["maximum_reference_actions"], 352)

    def test_same_format_and_standard_still_require_the_right_verifier(self):
        design = load(build())
        first, second = design["tasks"]["T13"]["stages"]
        alternate = design["tasks"]["T15"]["stages"][0]
        engine = world(design)
        good = plans(engine, item(first))[0]
        wrong = plans(engine, item(alternate))[0]
        self.assertEqual(good[0], wrong[0])
        self.assertNotEqual(good[1], wrong[1])
        good_keys = experience_keys(item(first), engine)
        wrong_keys = experience_keys(item(alternate), engine)
        self.assertEqual(good_keys[0], wrong_keys[0])
        self.assertEqual(good_keys[1][:-1], wrong_keys[1][:-1])
        self.assertNotEqual(good_keys[1][-1], wrong_keys[1][-1])

        game = StationGame(map_world(design), design)

        def process(station_type):
            station = design["public"]["station_types"][station_type]["stations"][0]
            walk(game, station)
            return game.step({"type": "process"})

        def survey(stage):
            walk(game, stage["target"])
            game.step({"type": "survey"})

        initial = game.start_task("T13")
        self.assertNotIn("verification_conditions", json.dumps(initial))
        survey(first)
        catalogue = process(good[0])
        self.assertNotIn("delivery_condition", catalogue["feedback"])
        denied = process(wrong[1])
        self.assertEqual(denied["feedback"]["output_format"], first["goal"])
        self.assertEqual(
            denied["feedback"]["delivery_condition"], alternate["delivery_condition"]
        )
        self.assertIn("交付条件不符", render_text(denied, compact=True))
        self.assertEqual(game.state.stage, 0)

        survey(first)
        for station in good:
            process(station)
        self.assertEqual(game.state.stage, 1)
        self.assertFalse(game.state.raw)
        self.assertIsNone(game.state.material_state)
        survey(second)
        for station in plans(engine, item(second))[0]:
            process(station)
        walk(game, game.task["submit_at"])
        game.step({"type": "submit"})
        self.assertTrue(game.state.success)

        report = analyze(design, game.events, game.task_run_id)
        catalogue_op, verifier_op = report["processing_operations"][:2]
        self.assertTrue(catalogue_op["first_processing_correct"])
        self.assertNotIn("scope_condition", catalogue_op)
        self.assertTrue(verifier_op["local_first_success"])
        self.assertFalse(verifier_op["first_processing_correct"])
        self.assertEqual(verifier_op["scope_condition"], first["delivery_condition"])
        self.assertFalse(verifier_op["prior_matching_feedback"])
        self.assertEqual(report["first_operation_correct"], 3)
        self.assertEqual(report["recollections"], 1)

        with TemporaryDirectory() as directory:
            session = Path(directory)
            (session / "summary.json").write_text(
                '{"task_id": "T13"}', encoding="utf-8"
            )
            (session / "events.jsonl").write_text(
                "\n".join(map(json.dumps, game.events)) + "\n", encoding="utf-8"
            )
            replayed = replay_checkpoint(design, map_world(design), [session])
        self.assertEqual(replayed.events, game.events)

    def test_conditioned_standalone_verification_cannot_omit_condition(self):
        design = deepcopy(build())
        task = design["tasks"]["T3"]
        del task["delivery_condition"], task["stages"][0]["delivery_condition"]
        with self.assertRaisesRegex(ValueError, "needs a public delivery condition"):
            load(design)


if __name__ == "__main__":
    unittest.main()
