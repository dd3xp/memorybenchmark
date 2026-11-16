"""Native-game contracts for the candidate, not model calibration results."""

from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest

from memorybenchmark.prototypes.station_capability import StationGame, map_world
from memorybenchmark.prototypes.station_interfaces import load, world, item, analyze
from memorybenchmark.prototypes.station_knowledge import (
    evidence_support,
    DeliveredSupport,
)
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.composition_lab import plans
from scripts.build_hard_calibration import build, validate


class StationInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authored = build()
        cls.design = load(deepcopy(cls.authored))

    def game(self, task):
        game = StationGame(map_world(self.design), self.design)
        session = StationSession(game, task, feedback_mode="compact")
        return game, session

    def station(self, type_id):
        return self.design["public"]["station_types"][type_id]["stations"][0]

    def test_all_twelve_real_games_complete_and_prior_facts_are_delivered(self):
        proof = validate(self.authored)
        self.assertEqual((proof["successes"], proof["required_operations"]), (12, 32))
        self.assertTrue(proof["actual_prior_feedback_for_every_combined_operation"])

    def test_public_initial_state_never_includes_private_interface_table(self):
        game, session = self.game("T5")
        payload = json.dumps(session.initial, ensure_ascii=False)
        self.assertNotIn("private_interfaces", payload)
        self.assertNotIn("cataloguers", payload)
        self.assertIn("交付目标", session.initial["text"])
        self.assertEqual(game.state.stage, 0)

    def test_wrong_successful_catalogue_needs_recollection_before_correct_chain(self):
        game, session = self.game("T5")
        stage = game.task["stages"][0]
        good = plans(world(self.design), item(stage))[0]
        wrong = next(
            s
            for m, s in world(self.design).cataloguers
            if m == stage["required_kind"] and s != good[0]
        )
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, self.station(wrong))
        first = game.step({"type": "process"})
        self.assertEqual(first["feedback"]["result"], "processed")
        self.assertEqual(game.state.stage, 0)
        self.assertFalse(game.state.processed)
        walk(game, self.station(good[1]))
        failed = game.step({"type": "process"})
        self.assertEqual(failed["feedback"]["result"], "unsupported")
        self.assertNotIn("capability", failed["feedback"])
        retained = game.state.material_state
        self.assertIsNotNone(retained)
        walk(game, stage["target"])
        game.step({"type": "survey"})
        self.assertIsNone(game.state.material_state)
        for station in good:
            walk(game, self.station(station))
            game.step({"type": "process"})
        self.assertEqual(game.state.stage, 1)
        self.assertFalse(game.state.raw)
        self.assertIsNone(game.state.material_state)
        result = analyze(self.design, game.events, game.task_run_id)
        self.assertEqual(result["recollections"], 1)
        self.assertFalse(result["stage_outcomes"][0]["whole_stage_first_correct"])
        self.assertEqual(result["necessary_operation_denominator"], 3)

    def test_feedback_only_evidence_preserves_scope_and_never_invents_full_support(
        self,
    ):
        game, session = self.game("T1")
        stage = game.task["stages"][0]
        plan = plans(world(self.design), item(stage))[0]
        walk(game, stage["target"])
        game.step({"type": "survey"})
        walk(game, self.station(plan[0]))
        game.step({"type": "process"})
        evidence = evidence_support(self.design, game.events)
        self.assertIsInstance(evidence, DeliveredSupport)
        self.assertEqual(len(evidence.facts), 1)
        self.assertEqual(evidence.facts[0][0][1], stage["required_kind"])

    def test_no_inspection_and_replicas_have_identical_processing(self):
        game, session = self.game("T1")
        stage = game.task["stages"][0]
        type_id = plans(world(self.design), item(stage))[0][0]
        outcomes = []
        for station in self.design["public"]["station_types"][type_id]["stations"]:
            other = StationGame(map_world(self.design), self.design)
            other.start_task("T1")
            walk(other, stage["target"])
            other.step({"type": "survey"})
            walk(other, station)
            self.assertNotIn(
                {"type": "inspect"}, other.observation()["available_actions"]
            )
            feedback = other.step({"type": "process"})["feedback"]
            outcomes.append((feedback["result"], feedback["output_format"]))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_unreachable_goal_and_duplicate_rule_are_rejected(self):
        bad = deepcopy(self.authored)
        bad["tasks"]["T1"]["stages"][0]["goal"] = "unavailable"
        bad["tasks"]["T1"]["goal"] = "unavailable"
        with self.assertRaises(ValueError):
            load(bad)
        bad = deepcopy(self.authored)
        bad["private_interfaces"]["cataloguers"].append(
            deepcopy(bad["private_interfaces"]["cataloguers"][0])
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load(bad)
