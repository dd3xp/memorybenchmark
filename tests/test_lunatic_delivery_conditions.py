from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from memorybenchmark.prototypes.composition_lab import plans
from memorybenchmark.prototypes.station_capability import StationGame, map_world
from memorybenchmark.prototypes.station_interfaces import analyze, item, load, world
from memorybenchmark.prototypes.station_pilot import replay_checkpoint
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import render_text
from scripts.build_lunatic_delivery_conditions import assess, build


class DeliveryConditionsTests(unittest.TestCase):
    def setUp(self):
        self.authored = build()
        self.design = load(deepcopy(self.authored))

    def process(self, game, station_type):
        station = self.design["public"]["station_types"][station_type]["stations"][0]
        walk(game, station)
        return game.step({"type": "process"})

    def survey(self, game, stage):
        walk(game, stage["target"])
        game.step({"type": "survey"})

    def test_all_candidate_combinations_are_supported_by_earlier_game_feedback(self):
        review = assess(self.authored)
        self.assertEqual(review["successes"], 20)
        self.assertEqual(review["matched_condition_pairs"], 8)
        self.assertGreater(review["valid_standard_wrong_condition_type_routes"], 0)
        self.assertLessEqual(review["maximum_reference_actions"], 352)

    def test_same_standard_wrong_condition_requires_recollection_and_replays(self):
        good, next_stage = self.design["tasks"]["T13"]["stages"]
        alternate = self.design["tasks"]["T15"]["stages"][0]
        self.assertEqual(good["required_kind"], alternate["required_kind"])
        self.assertEqual(good["target"], alternate["target"])
        self.assertEqual(good["goal"], alternate["goal"])

        game = StationGame(map_world(self.design), self.design)
        initial = game.start_task("T13")
        self.assertIn(good["delivery_condition"], render_text(initial, compact=True))
        self.assertNotIn("format_conditions", json.dumps(initial))
        self.survey(game, good)
        engine = world(self.design)
        cataloguer, verifier = plans(engine, item(alternate))[0]
        catalogued = self.process(game, cataloguer)
        self.assertEqual(
            catalogued["feedback"]["delivery_condition"],
            alternate["delivery_condition"],
        )
        denied = self.process(game, verifier)
        self.assertEqual(denied["feedback"]["output_format"], good["goal"])
        self.assertEqual(denied["feedback"]["result"], "processed")
        self.assertTrue(denied["feedback"]["delivery_condition_failed"])
        self.assertIn("交付条件不符", render_text(denied, compact=True))
        self.assertEqual(game.state.stage, 0)

        self.survey(game, good)
        for station in plans(engine, item(good))[0]:
            self.process(game, station)
        self.assertEqual(game.state.stage, 1)
        self.assertFalse(game.state.raw)
        self.assertIsNone(game.state.material_state)
        self.survey(game, next_stage)
        for station in plans(engine, item(next_stage))[0]:
            self.process(game, station)
        walk(game, game.task["submit_at"])
        game.step({"type": "submit"})
        self.assertTrue(game.state.success)

        result = analyze(self.design, game.events, game.task_run_id)
        self.assertFalse(result["stage_outcomes"][0]["whole_stage_first_correct"])
        self.assertTrue(result["stage_outcomes"][1]["whole_stage_first_correct"])
        self.assertEqual(result["first_operation_correct"], 2)
        self.assertEqual(result["recollections"], 1)

        with TemporaryDirectory() as directory:
            session = Path(directory)
            (session / "summary.json").write_text(
                '{"task_id": "T13"}', encoding="utf-8"
            )
            (session / "events.jsonl").write_text(
                "\n".join(map(json.dumps, game.events)) + "\n", encoding="utf-8"
            )
            replayed = replay_checkpoint(self.design, map_world(self.design), [session])
        self.assertEqual(replayed.events, game.events)

    def test_combined_goal_cannot_omit_its_condition(self):
        task = self.authored["tasks"]["T13"]
        del task["delivery_condition"], task["stages"][0]["delivery_condition"]
        with self.assertRaisesRegex(ValueError, "needs a public delivery condition"):
            load(self.authored)
