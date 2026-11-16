"""Archive integrity and scientific boundaries fail closed without game replay."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from memorybenchmark.experiments.verification import inventory, verify_download
from memorybenchmark.prototypes.station_interfaces import load
from scripts.build_hard_calibration import build


def body(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def fixture(folder, *, changed_context=False, crossed_memory=False, wrong_effort=False):
    registry = body({"models": {"gpt-5.6-luna": {"hermes_context_tokens": 272000}}})
    design = body(build())
    files = {
        "config/model-gateways.json": registry,
        "memorybenchmark/data/calibration/example.json": design,
    }
    source_manifest = {
        name: {"bytes": len(value), "sha256": sha256(value).hexdigest()}
        for name, value in files.items()
    }
    job = {
        "model": "gpt-5.6-luna",
        "agent": "hermes",
        "context_tokens": 272000,
        "tasks_per_condition": 12,
        "condition": "clear",
        "pair_id": "pair",
        "source_digest": sha256(
            json.dumps(source_manifest, sort_keys=True).encode()
        ).hexdigest(),
        "registry_sha256": sha256(registry).hexdigest(),
        "design_file": "calibration/example.json",
    }
    packaged = BytesIO()
    with zipfile.ZipFile(packaged, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, value in files.items():
            bundle.writestr(name, value)
        bundle.writestr("source-manifest.json", body(source_manifest))
    baseline_body = b"native baseline"
    baseline = {
        "memory.md": {
            "size": len(baseline_body),
            "sha256": sha256(baseline_body).hexdigest(),
        }
    }
    pilot = {
        "map_configuration_sha256": sha256(design).hexdigest(),
        "baseline_memory": baseline,
        "memory_condition": "clear",
        "experiment_id": "experiment",
        "sessions": [],
    }
    members = {
        "run/provenance/executor-source.zip": packaged.getvalue(),
        "provenance/source-manifest.json": body(source_manifest),
        "provenance/job.json": body(job),
        "run/design.json": body(load(json.loads(design))),
        "run/baseline/memory.md": baseline_body,
    }
    rows = []
    for i in range(12):
        name = f"{i+1:02d}-T{i+1}-clear"
        pilot["sessions"].append({"name": name})
        rows.append({"name": name, "llm_calls": 1})
        prefix = "run/sessions/" + name + "/"
        initial = {
            "native_context_configuration": {
                "model_context_length": 64000 if changed_context else 272000,
                "registry_sha256": job["registry_sha256"],
                "model": job["model"],
            }
        }
        before = {} if crossed_memory and i else baseline
        summary = {
            "input_memory": before,
            "output_memory": baseline,
            "initial_session": initial,
            "infrastructure_ok": True,
            "action_policy": "single",
            "llm_calls": 1,
            "session_id": str(i),
        }
        members[prefix + "summary.json"] = body(summary)
        members[prefix + "memory-before.json"] = body(before)
        members[prefix + "memory-after/memory.md"] = baseline_body
        members[prefix + "transport-attempts.jsonl"] = b""
        members[prefix + "model/001-request.json"] = body(
            {
                "model": job["model"],
                "reasoning": {"effort": "high"},
                "tools": [{"type": "function"}],
                "input": [{"role": "user", "content": "PRIVATE_PROMPT"}],
            }
        )
        members[prefix + "model/001-response.json"] = body(
            {
                "lines": [
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "model": job["model"],
                                "reasoning": {
                                    "effort": "medium" if wrong_effort else "high"
                                },
                                "usage": {"input_tokens": 5, "output_tokens": 1},
                            },
                        }
                    )
                ]
            }
        )
    members["run/pilot.json"] = body(pilot)
    audit = {
        "status": "completed_and_audited",
        "condition": "clear",
        "experiment_id": "experiment",
        "rows": rows,
        "replay": {
            "sessions": 12,
            **dict.fromkeys(
                (
                    "pilot_completed",
                    "memory_chains_verified",
                    "fresh_sessions_and_isolation_verified",
                    "native_archive_verified",
                ),
                True,
            ),
        },
    }
    members["provenance/audit-result.json"] = body(audit)
    costs = {"failure_events": 0, "active_pending_rpcs": 0}
    members["provenance/transport-costs.json"] = body(costs)
    manifest = {
        name: {"bytes": len(value), "sha256": sha256(value).hexdigest()}
        for name, value in members.items()
    }
    archive = folder / "evidence.zip.download"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, value in members.items():
            bundle.writestr(name, value)
        bundle.writestr("provenance/archive-content-manifest.json", body(manifest))
    result = {
        **audit,
        "transport_costs": costs,
        "archive": {
            "contents_verified": True,
            "bytes": archive.stat().st_size,
            "sha256": sha256(archive.read_bytes()).hexdigest(),
        },
    }
    (folder / "result.json").write_bytes(body(result))
    (folder / "driver-exit.json").write_bytes(body({"exit_code": 0}))
    return result


class CalibrationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_clear_baselines_context_models_high_and_missing_reasoning_are_checked(
        self,
    ):
        fixture(self.root)
        result = verify_download(self.root)
        self.assertTrue(result["passed"])
        self.assertEqual(result["model_evidence"]["primary_high_pairs"], 12)
        self.assertEqual(
            result["model_evidence"]["responses_without_reported_reasoning"], 12
        )
        self.assertFalse(result["game_replayed_locally"])
        self.assertNotIn("PRIVATE_PROMPT", json.dumps(result))
        (self.root / "evidence.zip.download").unlink()
        self.assertEqual(
            verify_download(self.root), result
        )  # no repeated verification after passed

    def test_wrong_actual_context_never_gets_a_passed_receipt(self):
        fixture(self.root, changed_context=True)
        with self.assertRaisesRegex(ValueError, "context differs"):
            verify_download(self.root)
        self.assertFalse((self.root / "local-verification.json").exists())

    def test_clear_cannot_adopt_a_different_input_memory(self):
        fixture(self.root, crossed_memory=True)
        with self.assertRaisesRegex(ValueError, "condition boundary"):
            verify_download(self.root)

    def test_request_high_does_not_substitute_for_provider_high(self):
        fixture(self.root, wrong_effort=True)
        with self.assertRaisesRegex(ValueError, "acknowledgement"):
            verify_download(self.root)

    def test_outer_hash_is_checked_before_reading_members(self):
        fixture(self.root)
        path = self.root / "evidence.zip.download"
        with path.open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "outer size/SHA"):
            verify_download(self.root)

    def test_self_consistent_bundle_must_match_independently_frozen_source(self):
        fixture(self.root)
        with self.assertRaisesRegex(ValueError, "independently frozen"):
            verify_download(self.root, expected_source_digest="another-round")
        self.assertFalse((self.root / "local-verification.json").exists())

    def test_inner_hash_and_unsafe_or_duplicate_inventory_are_rejected(self):
        for name in ("safe", "../escaped", "C:/escaped"):
            with self.subTest(name=name):
                archive = BytesIO()
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(name, b"corrupted")
                with zipfile.ZipFile(archive) as bundle:
                    with self.assertRaises(ValueError):
                        inventory(bundle, {name: {"bytes": 1, "sha256": "wrong"}})
