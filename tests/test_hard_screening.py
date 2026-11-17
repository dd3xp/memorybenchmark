"""A full retained development run stops only at predeclared saved boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.experiments.hard_screening import (
    HardScreen,
    DevelopmentScreenStop,
    decision,
)
from memorybenchmark.experiments.verification import authorized_task_count
from memorybenchmark.experiments.repository import PairRepository
from scripts.build_hard_calibration import build, validate
from scripts.run_hard_confirmation import validate as validate_confirmation

PROJECT = Path(__file__).resolve().parents[1]


class HardScreeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.authorization = json.loads(
            (PROJECT / "config/authorized-hard-target60-retain.json").read_text()
        )
        self.policy = self.authorization["development_screen"]
        self.job = {
            **self.authorization,
            "root": str(self.root),
            "condition": "retain",
            "conditions": ["retain"],
            "tasks_per_condition": 36,
            "total_tasks": 36,
            "pair_id": PairRepository.pair_id(self.authorization["request_id"]),
        }

    @staticmethod
    def metrics(n=24, rate=0.6, known=8, missing=0):
        return {
            "after_first_planned_goal_encounter": {
                "correct": round(n * rate),
                "denominator": n,
                "rate": rate,
            },
            "combined_with_both_prior_actual_facts": {
                "correct": round(known * rate),
                "denominator": known,
                "rate": rate,
            },
            "combinations_without_both_prior_actual_facts": missing,
        }

    def test_no_stop_during_first_encounters_or_tiny_known_combo_sample(self):
        self.assertIsNone(decision(self.metrics(n=23, rate=0), self.policy))
        self.assertIsNone(decision(self.metrics(rate=1, known=7), self.policy))

    def test_low_high_and_middle_follow_preregistered_rules(self):
        self.assertEqual(decision(self.metrics(rate=0.2), self.policy), "too_hard")
        self.assertEqual(decision(self.metrics(rate=0.95), self.policy), "too_easy")
        self.assertIsNone(decision(self.metrics(rate=0.6), self.policy))
        self.assertIsNone(decision(self.metrics(rate=0.8), self.policy))
        self.assertEqual(
            decision(self.metrics(n=36, rate=0.8), self.policy), "too_easy"
        )

    def test_missing_prior_feedback_is_a_design_stop_not_a_memory_score(self):
        self.assertEqual(
            decision(self.metrics(missing=1), self.policy),
            "missing_required_prior_feedback",
        )

    def test_real_zero_model_game_stops_at_completed_task24_before_task25(self):
        design = build(
            seed=61601, variant="binding", full=True, curriculum="balanced-three"
        )
        with self.assertRaises(DevelopmentScreenStop):
            validate(design, checkpoint_observer=HardScreen(self.job, self.policy))
        stop = json.loads((self.root / "development-stop.json").read_text())
        self.assertEqual(
            (stop["completed"], stop["planned"], stop["decision"]), (24, 36, "too_easy")
        )
        self.assertEqual(
            stop["metrics"]["after_first_planned_goal_encounter"]["denominator"], 24
        )
        self.assertEqual(
            stop["metrics"]["combined_with_both_prior_actual_facts"]["denominator"], 8
        )
        self.assertTrue(stop["partial_attempt_is_not_a_complete_result"])
        self.assertEqual(stop["model_or_game_replay_calls"], 0)
        self.assertFalse((self.root / "development-observations/25.json").exists())

    def test_resume_preserves_immutable_observation_and_full_run_goes_to_audit(self):
        screen = HardScreen(self.job, self.policy)
        sessions = [{"success": True}] * 24
        report = {"sessions": sessions, "tasks": list(range(36))}
        game = type("Game", (), {"design": {}, "events": []})()
        with patch(
            "memorybenchmark.experiments.hard_screening.prefix_metrics",
            return_value=self.metrics(),
        ):
            screen(report, game)
            first = (self.root / "development-observations/24.json").read_bytes()
            screen(report, game)
            self.assertEqual(
                (self.root / "development-observations/24.json").read_bytes(), first
            )
        report["sessions"] = [{"success": True}] * 36
        with patch(
            "memorybenchmark.experiments.hard_screening.prefix_metrics",
            return_value=self.metrics(n=64, rate=1, known=24),
        ):
            screen(report, game)
        receipt = json.loads((self.root / "development-metrics.json").read_text())
        self.assertEqual(receipt["phase"], "full_tasks_pending_original_audit")
        self.assertFalse(receipt["partial_attempt_is_not_a_complete_result"])
        self.assertFalse((self.root / "development-stop.json").exists())

    def test_only_the_authorized_new_retained_world_is_accepted(self):
        review = {**self.job, "agent": "hermes"}
        validate_confirmation(review, self.authorization, PROJECT)
        self.assertEqual(authorized_task_count(self.job, "independent-source"), 36)
        for changed in (
            {"condition": "clear"},
            {"design_id": "other"},
            {"pair_id": "old-pair"},
        ):
            with self.assertRaises(ValueError):
                authorized_task_count({**self.job, **changed}, "independent-source")
        with self.assertRaises(ValueError):
            HardScreen({**self.job, "context_tokens": 64000}, self.policy)
        malformed = deepcopy(self.policy)
        malformed["minimum_repeat_operations"] = 0
        with self.assertRaises(ValueError):
            HardScreen(self.job, malformed)

    def test_curriculum_gives_every_experience_three_uses_with_both_premises(self):
        design = build(
            seed=61601, variant="binding", full=True, curriculum="balanced-three"
        )
        allocation = design["evaluation"]["allocation"]
        self.assertEqual(
            (
                allocation["materials"],
                allocation["fully_scoped_goal_classes"],
                allocation["uses_each"],
            ),
            (8, 32, 3),
        )
        self.assertEqual(
            (
                allocation["tasks"],
                allocation["stages"],
                allocation["necessary_operations"],
            ),
            (36, 72, 96),
        )
        result = validate(design)
        self.assertEqual(result["successes"], 36)
        self.assertTrue(result["actual_prior_feedback_for_every_combined_operation"])
        self.assertLessEqual(result["maximum_reference_actions"], 352)
        original = json.loads(
            (PROJECT / "memorybenchmark/data/orcia_hard36.json").read_text(
                encoding="utf-8"
            )
        )
        for key in ("locations", "edges", "station_types"):
            self.assertEqual(design["public"][key], original["public"][key])


if __name__ == "__main__":
    unittest.main()
