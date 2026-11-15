import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.experiments.costs import transport_costs


class TransportCostsTests(unittest.TestCase):
    def test_two_physical_failures_one_rpc_are_both_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions/01-T1-retain/transport-attempts.jsonl"
            path.parent.mkdir(parents=True)
            rows = [
                {
                    "kind": "request_failed",
                    "call": 1,
                    "request_sha256": "same",
                    "reason": "gateway_http_429",
                },
                {
                    "kind": "request_failed",
                    "call": 1,
                    "request_sha256": "same",
                    "reason": "gateway_http_429",
                },
                {"kind": "request_completed", "call": 1, "request_sha256": "same"},
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            result = transport_costs(directory)
            self.assertEqual(result["failure_events"], 2)
            self.assertEqual(result["affected_rpcs"], 1)
            self.assertEqual(result["recovered_affected_rpcs"], 1)
            self.assertEqual(result["active_pending_rpcs"], 0)
            self.assertEqual(result["failure_events_without_reported_usage"], 2)

    def test_abandoned_attempt_is_history_and_its_reported_cost_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = (
                Path(directory)
                / "failed-attempts/01-T1-retain-host-reboot/transport-attempts.jsonl"
            )
            path.parent.mkdir(parents=True)
            rows = [
                {
                    "kind": "request_completed",
                    "call": 1,
                    "request_sha256": "a",
                    "reported_usage": {
                        "input_tokens": 120,
                        "output_tokens": 10,
                        "output_tokens_details": {"reasoning_tokens": 4},
                    },
                },
                {
                    "kind": "request_failed",
                    "call": 2,
                    "request_sha256": "b",
                    "reason": "gateway_http_429",
                },
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            result = transport_costs(directory)
            self.assertEqual(result["historical_unrecovered_rpcs"], 1)
            self.assertEqual(result["active_pending_rpcs"], 0)
            self.assertEqual(
                result["abandoned_attempt_reported_tokens"],
                {"input_tokens": 120, "output_tokens": 10, "reasoning_tokens": 4},
            )


if __name__ == "__main__":
    unittest.main()
