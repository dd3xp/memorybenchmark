import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from hashlib import sha256

from memorybenchmark.experiments.archive import finish_retention
from memorybenchmark.request_recovery import RequestFailure
from memorybenchmark.transports.subscription import (
    classification,
    CONCURRENCY_PREFIX,
    QUOTA_MESSAGE,
)
from tests.test_experiment_service import ExperimentServiceTests


class RuntimeContracts(unittest.TestCase):
    def test_plain_authentication_failure_is_never_generalized_into_retry(self):
        self.assertIsNone(
            classification(
                RequestFailure(
                    "gateway_http_401", http_status=401, body='{"error":"invalid key"}'
                )
            )
        )
        body = {
            "type": "error",
            "error": {
                "type": "api_error",
                "message": CONCURRENCY_PREFIX
                + json.dumps({"error": "Too many concurrent requests"}),
            },
        }
        self.assertEqual(
            classification(
                RequestFailure(
                    "gateway_http_401", http_status=401, body=json.dumps(body)
                )
            ),
            "wrapped-auth-service-concurrency-1",
        )
        body["error"]["message"] = "authentication failed"
        self.assertIsNone(
            classification(
                RequestFailure(
                    "gateway_http_401", http_status=401, body=json.dumps(body)
                )
            )
        )

    def test_subscription_reset_wait_requires_exact_structured_envelope(self):
        event = {
            "type": "error",
            "error": {
                "code": "subscription_sharing_usage_limit_exceeded",
                "type": "invalid_request_error",
                "param": None,
                "message": QUOTA_MESSAGE,
            },
        }
        self.assertEqual(
            classification(
                RequestFailure(
                    "model_response_failed", upstream_error=json.dumps(event)
                )
            ),
            "subscription-sharing-quota-wait-1",
        )
        event["error"]["code"] = "invalid_api_key"
        self.assertIsNone(
            classification(
                RequestFailure(
                    "model_response_failed", upstream_error=json.dumps(event)
                )
            )
        )

    def test_verified_retention_resumes_without_running_final_audit_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "runtime-hermes/.runs/pilot-test"
            path = run / "sessions/01-T1-retain/model/001-request.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"preserved raw request")
            member = "run/" + path.relative_to(run).as_posix()
            manifest = {
                member: {
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                }
            }
            (root / "status.json").write_text(json.dumps({"run": str(run)}))
            with zipfile.ZipFile(root / "evidence.zip", "w") as archive:
                archive.write(path, member)
                archive.writestr(
                    "provenance/archive-content-manifest.json", json.dumps(manifest)
                )
            finish_retention(root)
            finish_retention(root)
            self.assertFalse(path.exists())
            self.assertEqual(
                json.loads((root / "retention.json").read_text())["phase"], "complete"
            )


class DispatchRecovery(ExperimentServiceTests):
    def test_retry_dispatches_only_missing_counterpart(self):
        calls = []

        def dispatch(job, config):
            if len(calls) == 1 and not getattr(self, "failed_once", False):
                self.failed_once = True
                raise RuntimeError("scheduler temporary error")
            calls.append(job["condition"])

        self.scheduler.dispatch = dispatch

        def freeze(project, destination, design):
            self.assertEqual(destination.name, "runtime-hermes")
            destination.mkdir(parents=True)
            return "same"

        with patch("memorybenchmark.experiments.service.freeze", side_effect=freeze):
            with self.assertRaises(RuntimeError):
                self.service.create(self.selection)
            self.service.create(self.selection)
        self.assertEqual(calls, ["retain", "clear"])


if __name__ == "__main__":
    unittest.main()
