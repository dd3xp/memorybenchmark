"""Paired reports preserve failures and reject incomplete or mismatched evidence."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.report_hard_calibration import build, condition


class CalibrationReportTests(unittest.TestCase):
    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.folders = []
        self.normal = {
            "actual_context_tokens_all_sessions": 272000,
            "rows": [
                {
                    "map": "nessie-normal",
                    "condition": "retain",
                    "movement_mode": "route",
                    "after_first_encounter": {"correct": 36, "denominator": 36},
                }
            ],
        }
        for pair in ("a" * 32, "b" * 32):
            for mode in ("retain", "clear"):
                folder = Path(self.workspace.name) / pair / mode
                folder.mkdir(parents=True)
                self.folders.append(folder)
                result = {"rows": [{"task_id": "T1", "success": mode == "retain"}]}
                self.write(folder, "result.json", result)
                self.write(
                    folder,
                    "job.json",
                    {
                        "pair_id": pair,
                        "condition": mode,
                        "source_digest": pair,
                        "model": "gpt-5.6-luna",
                        "context_tokens": 272000,
                        "movement_mode": "step",
                        "tasks_per_condition": 12,
                        "design_id": "fixture",
                    },
                )
                self.write(
                    folder,
                    "local-verification.json",
                    {
                        "passed": True,
                        "pair_id": pair,
                        "condition": mode,
                        "source_digest": pair,
                        "actual_context": 272000,
                    },
                )
                self.write(
                    folder,
                    "calibration-metrics.json",
                    {
                        "condition": mode,
                        "source_digest": pair,
                        "design_id": "fixture",
                        "local_archive_verification": "pending",
                        "source_result_sha256": sha256(
                            (folder / "result.json").read_bytes()
                        ).hexdigest(),
                        "tasks": {
                            "correct": 12 if mode == "retain" else 9,
                            "denominator": 12,
                        },
                        "after_first_planned_goal_encounter": {
                            "rate": 0.875 if mode == "retain" else 0.25
                        },
                        "infrastructure_costs": {"unknown_usage": None},
                    },
                )

    @staticmethod
    def write(folder, name, value):
        (folder / name).write_text(json.dumps(value), encoding="utf-8")

    def test_reports_both_conditions_preserving_failures_and_unknown_usage(self):
        report = build(self.folders, self.normal)
        self.assertEqual(report["completed_tasks"], 48)
        self.assertEqual(report["successful_tasks"], 42)
        for row in report["rounds"]:
            self.assertEqual(
                row["normal_minus_retained_repeat_percentage_points"], 12.5
            )
            self.assertEqual(row["conditions"]["clear"]["game_failure_tasks"], ["T1"])
            self.assertIsNone(
                row["conditions"]["clear"]["metrics"]["infrastructure_costs"][
                    "unknown_usage"
                ]
            )
            self.assertNotIn(
                "local_archive_verification", row["conditions"]["retain"]["metrics"]
            )

    def test_missing_clear_cannot_be_reported_as_a_finished_pair(self):
        with self.assertRaisesRegex(ValueError, "retain and clear"):
            build(self.folders[:-1], self.normal)

    def test_a_changed_source_result_invalidates_the_metrics(self):
        self.write(self.folders[0], "result.json", {"rows": []})
        with self.assertRaisesRegex(ValueError, "must agree"):
            condition(self.folders[0])

    def test_invalid_64k_reference_is_rejected(self):
        self.normal["actual_context_tokens_all_sessions"] = 64000
        with self.assertRaisesRegex(ValueError, "invalid historical context"):
            build(self.folders, self.normal)


if __name__ == "__main__":
    unittest.main()
