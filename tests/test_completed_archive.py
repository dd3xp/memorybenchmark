"""An archive repair must never become a route back into incomplete gameplay."""

from copy import deepcopy
import unittest

from operations.resume_completed_archive import validate_completed


class CompletedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.job = {"tasks_per_condition": 2, "condition": "retain"}
        self.pilot = {
            "status": "completed",
            "memory_condition": "retain",
            "tasks": ["T1", "T2"],
            "sessions": [{"infrastructure_ok": True}, {"infrastructure_ok": True}],
        }
        self.paused = {
            "type": "AssertionError",
            "message": "executed support differs from frozen source",
        }

    def test_only_completed_condition_is_eligible(self):
        validate_completed(self.pilot, self.job, self.paused)
        for changes in (
            {"status": "running"},
            {"memory_condition": "clear"},
            {"tasks": ["T1"]},
            {"sessions": [{"infrastructure_ok": True}]},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_completed({**self.pilot, **changes}, self.job, self.paused)

    def test_infrastructure_failures_and_unknown_errors_are_not_retried(self):
        pilot = deepcopy(self.pilot)
        pilot["sessions"][1]["infrastructure_ok"] = False
        with self.assertRaises(ValueError):
            validate_completed(pilot, self.job, self.paused)
        with self.assertRaises(ValueError):
            validate_completed(
                self.pilot, self.job, {"type": "ValueError", "message": "other failure"}
            )
