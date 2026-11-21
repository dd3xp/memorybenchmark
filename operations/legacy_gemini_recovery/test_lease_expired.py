"""Exercise the explicit lease-expiry transaction without a model or scheduler."""

from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import recover_lease_expired as recovery


class LeaseExpiryTransaction(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private = Path(temporary.name)
        self.root = self.private / (
            "easy20-gemini-gemini-3.1-flash-lite-dingo-normal-retain-20261111"
        )
        self.run = self.root / (
            "runtime-hermes/.runs/"
            "pilot-hermes-retain-dingo-normal-gemini-3.1-flash-lite-20261111"
        )
        self.folder = self.run / "sessions/16-T16-retain"
        self.guard = (
            self.root / "request-recovery-state/leases" / ("a" * 32) / "guard-exit.json"
        )
        self.pause = self.root / recovery.PAUSE
        recovery.write(
            self.private / "gemini-easy-normal-hermes-20261111/prepared.json",
            {
                "runs": [
                    {
                        "root": str(self.root),
                        "run": str(self.run),
                        "experiment_id": "owned-run",
                        "task_name": "scheduler-owned-by-run",
                    }
                ]
            },
        )
        for path, value in (
            (
                self.root / "run-plan.json",
                {
                    "run_directory_name": self.run.name,
                    "model_alias": recovery.MODEL,
                    "map_id": "dingo-normal",
                    "condition": "retain",
                    "context_tokens_configured": 250000,
                    "experiment_id": "owned-run",
                    "source_zip_sha256": "b" * 64,
                },
            ),
            (self.root / "driver-started.json", {"created_filetime": 10, "pid": 41}),
            (self.root / "driver-exit.json", {"exit_code": 1}),
            (self.pause, {"type": "RuntimeError", "reason": "Native failure"}),
            (self.guard, {"reason": "host_lease_expired", "exit_code": -9}),
            (
                self.run / "pilot.json",
                {
                    "experiment_id": "owned-run",
                    "memory_condition": "retain",
                    "model_alias": recovery.MODEL,
                    "status": "interrupted",
                    "tasks": [f"T{i}" for i in range(1, 25)],
                    "sessions": [
                        {"name": f"{i:02d}-T{i}-retain"} for i in range(1, 16)
                    ],
                    "operator_whole_task_retries": 1,
                    "automatic_reboot_boundary_retries": 2,
                },
            ),
        ):
            recovery.write(path, value)
        self.folder.mkdir(parents=True)
        self.summary_path = self.folder / "summary.json"
        self.deliveries = self.folder / "game-deliveries.jsonl"
        self.state = {"done": False, "success": False, "steps": 17, "distance": 24}
        self.set_deliveries()
        (self.folder / "model").mkdir()
        (self.folder / "model/raw.txt").write_bytes(b"original response evidence")
        self.checkpoint = patch.object(recovery, "validate_inputs").start()
        self.addCleanup(patch.stopall)

    def set_deliveries(self, *extra_responses):
        responses = ({"observation": self.state}, *extra_responses)
        body = b"".join(
            json.dumps({"response": response}).encode() + b"\n"
            for response in responses
        )
        self.deliveries.write_bytes(body)
        recovery.write(
            self.summary_path,
            {
                "task_id": "T16",
                "condition": "retain",
                "infrastructure_ok": False,
                "infrastructure_error": "OSError",
                "done": False,
                "success": None,
                "worker_returncode": 137,
                "host_io_error": {"type": "OSError", "errno": 22, "winerror": None},
                "request_recovery": {"lease_id": "a" * 32},
                "game_deliveries_sha256": sha256(body).hexdigest(),
                "game_actions": 17,
                "distance": 24,
            },
        )
        self.summary_sha256 = sha256(self.summary_path.read_bytes()).hexdigest()

    def stage(self, identity=None, summary_sha256=None):
        return recovery.stage(
            self.root,
            summary_sha256 or self.summary_sha256,
            10,
            private=self.private,
            process_identity=lambda _: identity,
        )

    def test_preserves_failed_session_and_pause_and_counts_operator_once(self):
        before = recovery.read(self.run / "pilot.json")
        pause = self.pause.read_bytes()
        info = self.stage()
        pilot = recovery.read(self.run / "pilot.json")
        self.assertEqual(pilot["sessions"], before["sessions"])
        self.assertEqual(pilot["operator_whole_task_retries"], 2)
        self.assertEqual(pilot["automatic_reboot_boundary_retries"], 2)
        self.assertEqual(len(pilot["attempt_history"]), 1)
        original = Path(info["preserved_at"])
        self.assertEqual(
            (original / "model/raw.txt").read_bytes(), b"original response evidence"
        )
        self.assertEqual(
            (Path(info["receipt"]).parent / "paused-cleared.json").read_bytes(), pause
        )
        self.assertFalse(self.folder.exists())
        self.assertFalse(self.pause.exists())
        self.assertEqual(self.stage(), info)
        self.assertEqual(recovery.read(self.run / "pilot.json"), pilot)

    def test_crash_after_move_keeps_pause_and_same_transaction_resumes(self):
        write = recovery.write

        def fail_on_pilot(path, value):
            if path.name == "pilot.json":
                raise OSError("simulated write failure")
            return write(path, value)

        with patch.object(recovery, "write", side_effect=fail_on_pilot):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.stage()
        self.assertTrue(self.pause.exists())
        self.assertFalse(self.folder.exists())
        self.assertTrue(self.stage()["prepared"])

    def test_guard_exit_must_prove_lease_expiry(self):
        recovery.write(self.guard, {"reason": "worker_exited", "exit_code": -9})
        with self.assertRaisesRegex(ValueError, "lease expiry"):
            self.stage()
        self.assertTrue(self.folder.is_dir())
        self.checkpoint.assert_not_called()

    def test_terminal_game_failure_cannot_be_repeated(self):
        self.set_deliveries(
            {"observation": {**self.state, "done": True}},
            {"observation": self.state},
            {"error": "invalid_action", "message": "Task is over"},
        )
        with self.assertRaisesRegex(ValueError, "terminal game outcome"):
            self.stage()
        self.assertTrue(self.pause.is_file())

    def test_last_error_response_does_not_hide_the_latest_game_state(self):
        self.set_deliveries(
            {"error": "stale_revision", "message": "Read current state first"}
        )
        self.assertTrue(self.stage()["prepared"])

    def test_sha_covers_errors_alongside_game_observations(self):
        with self.deliveries.open("ab") as stream:
            stream.write(b'{"response":{"error":"invalid_action"}}\n')
        with self.assertRaisesRegex(ValueError, "deliveries differ"):
            self.stage()
        self.assertTrue(self.folder.is_dir())

    def test_original_driver_must_be_dead(self):
        with self.assertRaisesRegex(ValueError, "driver has exited"):
            self.stage(identity=10)
        self.assertTrue(self.folder.is_dir())

    def test_attested_summary_must_match(self):
        with self.assertRaisesRegex(ValueError, "inspected evidence"):
            self.stage(summary_sha256="c" * 64)
        self.assertTrue(self.folder.is_dir())


if __name__ == "__main__":
    unittest.main()
