"""Verify a downloaded managed archive without replaying games or using a model."""

from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import zipfile

from ..agent_sessions import native_model_request_kind, observed_reasoning_effort
from ..prototypes.station_interfaces import load as load_interfaces
from .archive import file_digest


def require(value, message):
    if not value:
        raise ValueError(message)


FULL_RETAINED_CONFIRMATIONS = {
    "hard-binding36-retain-61501-v1": {
        "model": "gpt-5.6-luna",
        "world_seed": 61501,
        "design_id": "hard-binding-calibration-v2-61501-36",
        "design_file": "candidates/orcia_binding36.json",
    },
    "hard-target60-retain-61601-v1": {
        "model": "gpt-5.6-luna",
        "world_seed": 61601,
        "design_id": "hard-binding-calibration-v3-61601-36",
        "design_file": "candidates/orcia_binding36_target60.json",
    },
    "hard-target60-retain-61601-gpt6-luna-v1": {
        "model": "gpt-6-luna",
        "world_seed": 61601,
        "design_id": "hard-binding-calibration-v3-61601-36",
        "design_file": "candidates/orcia_binding36_target60.json",
    },
}

LUNATIC_RETAINED_PILOT = {
    "lunatic-scandinavia-goal-switch-retain18-v1": {
        "model": "gpt-5.6-luna",
        "map": "scandinavia-lunatic",
        "design_id": "lunatic-01-v4.1-goal-switch-pilot18",
        "design_file": "calibration/scandinavia_lunatic_goal_switch18.json",
    },
}


def authorized_task_count(job, expected_source_digest):
    """Additional task counts require a named retained run and a frozen source."""
    count = job["tasks_per_condition"]
    if count == 12:
        require(job["model"] == "gpt-5.6-luna", "Unknown Hard calibration model")
        return 12
    candidates = {36: FULL_RETAINED_CONFIRMATIONS, 18: LUNATIC_RETAINED_PILOT}
    require(
        expected_source_digest is not None
        and any(
            job["pair_id"] == sha256(request.encode()).hexdigest()[:32]
            and all(
                job.get(key) == value
                for key, value in spec.items()
                if key != "world_seed"
            )
            for request, spec in candidates.get(count, {}).items()
        )
        and job["condition"] == "retain"
        and job.get("conditions") == ["retain"]
        and job["movement_mode"] == "step",
        "Verification needs the authorized retained job and independent frozen source",
    )
    return count


def read(bundle, name):
    return json.loads(bundle.read(name))


def inventory(bundle, manifest):
    names = bundle.namelist()
    require(len(names) == len(set(names)), "Duplicate archive members")
    for name in names:
        path = PurePosixPath(name)
        require(
            not path.is_absolute()
            and ".." not in path.parts
            and "\\" not in name
            and ":" not in name
            and not name.endswith("/"),
            "Unsafe archive member",
        )
    require(
        set(names) == set(manifest) | {"provenance/archive-content-manifest.json"},
        "Archive inventory differs from its manifest",
    )
    size = 0
    for name, expected in manifest.items():
        digest, length = sha256(), 0
        with bundle.open(name) as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b""):
                digest.update(block)
                length += len(block)
        require(
            length == expected["bytes"] and digest.hexdigest() == expected["sha256"],
            "Archive member integrity differs: " + name,
        )
        size += length
    return size


def memory_inventory(manifest, prefix):
    return {
        name[len(prefix) :]: {"size": value["bytes"], "sha256": value["sha256"]}
        for name, value in manifest.items()
        if name.startswith(prefix)
    }


def source_identity(bundle, job):
    manifest = read(bundle, "provenance/source-manifest.json")
    digest = sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    require(digest == job["source_digest"], "Frozen executor identity differs")
    with zipfile.ZipFile(
        BytesIO(bundle.read("run/provenance/executor-source.zip"))
    ) as source:
        require(
            read(source, "source-manifest.json") == manifest, "Source manifests differ"
        )
        require(
            set(source.namelist()) == set(manifest) | {"source-manifest.json"},
            "Source package inventory differs",
        )
        for name, expected in manifest.items():
            body = source.read(name)
            require(
                len(body) == expected["bytes"]
                and sha256(body).hexdigest() == expected["sha256"],
                "Frozen source member changed",
            )
        original_design = source.read("memorybenchmark/data/" + job["design_file"])
        pilot = read(bundle, "run/pilot.json")
        require(
            sha256(original_design).hexdigest() == pilot["map_configuration_sha256"]
            and read(bundle, "run/design.json")
            == load_interfaces(json.loads(original_design)),
            "Executed design differs from the frozen candidate",
        )
        registry = source.read("config/model-gateways.json")
        require(
            sha256(registry).hexdigest() == job["registry_sha256"],
            "Context registry differs",
        )
    return manifest


def completed_response(value):
    completed = []
    for line in value.get("lines", []):
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            event = json.loads(line[5:])
            if event.get("type") == "response.completed":
                completed.append(event["response"])
    require(len(completed) == 1, "A canonical request lacks one completed response")
    return completed[0]


def session_evidence(bundle, manifest, row, job, before):
    prefix = "run/sessions/" + row["name"] + "/"
    summary = read(bundle, prefix + "summary.json")
    require(
        summary["input_memory"]
        == before
        == read(bundle, prefix + "memory-before.json"),
        "Memory input crossed the condition boundary",
    )
    after = memory_inventory(manifest, prefix + "memory-after/")
    require(after == summary["output_memory"], "Memory checkpoint differs")
    initial = summary["initial_session"]
    context = initial["native_context_configuration"]
    require(
        context["model_context_length"] == job["context_tokens"]
        and context["registry_sha256"] == job["registry_sha256"]
        and context["model"] == job["model"],
        "Executed native context differs",
    )
    require(
        summary["infrastructure_ok"] and summary["action_policy"] == "single",
        "Canonical session infrastructure or movement policy differs",
    )
    requests = {
        name
        for name in manifest
        if name.startswith(prefix + "model/") and name.endswith("-request.json")
    }
    responses = {
        name
        for name in manifest
        if name.startswith(prefix + "model/") and name.endswith("-response.json")
    }
    require(
        {name.replace("-request.json", "-response.json") for name in requests}
        == responses,
        "Canonical model request/response inventory differs",
    )
    require(
        len(requests) == summary["llm_calls"] == row["llm_calls"],
        "Model call counts differ",
    )
    counts = Counter()
    for name in sorted(requests):
        request = read(bundle, name)
        response = completed_response(
            read(bundle, name.replace("-request.json", "-response.json"))
        )
        require(
            request["model"] == response["model"] == job["model"],
            "Actual model identity differs",
        )
        kind = native_model_request_kind(request, "hermes-session-1")
        counts["responses"] += 1
        if kind == "agent":
            require(
                observed_reasoning_effort(request)
                == observed_reasoning_effort(response)
                == "high",
                "A primary response lacks its native high request/acknowledgement",
            )
            counts["primary_high_pairs"] += 1
        usage = response.get("usage") or {}
        counts["responses_without_reported_input_output"] += not all(
            type(usage.get(k)) is int for k in ("input_tokens", "output_tokens")
        )
        counts["responses_without_reported_reasoning"] += (
            type((usage.get("output_tokens_details") or {}).get("reasoning_tokens"))
            is not int
        )
    require(counts["primary_high_pairs"] > 0, "No real primary model response")
    require(
        prefix + "transport-attempts.jsonl" in manifest,
        "Canonical transport ledger missing",
    )
    return summary["session_id"], after, counts


def verify_download(folder, *, expected_source_digest=None):
    """A passed receipt is reused; raw scientific outcomes never get replayed here."""
    folder = Path(folder)
    receipt = folder / "local-verification.json"
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        require(previous.get("passed") is True, "Existing verification needs diagnosis")
        require(
            expected_source_digest is None
            or previous["source_digest"] == expected_source_digest,
            "Passed archive belongs to another frozen source",
        )
        return previous
    result = json.loads((folder / "result.json").read_text(encoding="utf-8-sig"))
    exited = json.loads((folder / "driver-exit.json").read_text(encoding="utf-8-sig"))
    archive = folder / "evidence.zip.download"
    expected = result["archive"]
    require(
        exited["exit_code"] == 0
        and expected["contents_verified"]
        and result["status"] == "completed_and_audited",
        "Original driver has not sealed this result",
    )
    require(
        archive.stat().st_size == expected["bytes"]
        and file_digest(archive) == expected["sha256"],
        "Downloaded archive outer size/SHA differs",
    )
    with zipfile.ZipFile(archive) as bundle:
        manifest = read(bundle, "provenance/archive-content-manifest.json")
        expanded = inventory(bundle, manifest)
        job = read(bundle, "provenance/job.json")
        require(
            expected_source_digest is None
            or job["source_digest"] == expected_source_digest,
            "Archive differs from the independently frozen source identity",
        )
        require(
            job["agent"] == "hermes" and job["context_tokens"] == 272000,
            "Archive is not an authorized native calibration",
        )
        expected_tasks = authorized_task_count(job, expected_source_digest)
        source = source_identity(bundle, job)
        audit = read(bundle, "provenance/audit-result.json")
        require(
            {k: result[k] for k in audit} == audit,
            "Published result differs from its original audit",
        )
        replay = audit["replay"]
        require(
            all(
                replay[k] is True
                for k in (
                    "pilot_completed",
                    "memory_chains_verified",
                    "fresh_sessions_and_isolation_verified",
                    "native_archive_verified",
                )
            ),
            "Original strict audit did not pass",
        )
        pilot = read(bundle, "run/pilot.json")
        require(
            pilot["memory_condition"] == job["condition"] == result["condition"]
            and pilot["experiment_id"] == result["experiment_id"]
            and len(result["rows"])
            == len(pilot["sessions"])
            == replay["sessions"]
            == expected_tasks,
            "Condition/session identity differs",
        )
        baseline = memory_inventory(manifest, "run/baseline/")
        require(baseline == pilot["baseline_memory"], "Original baseline differs")
        before, identities, totals = baseline, [], Counter()
        for row in result["rows"]:
            identity, after, counts = session_evidence(
                bundle, manifest, row, job, before
            )
            identities.append(identity)
            totals.update(counts)
            before = baseline if job["condition"] == "clear" else after
        require(len(set(identities)) == expected_tasks, "Sessions were reused")
        costs = read(bundle, "provenance/transport-costs.json")
        require(
            costs == result["transport_costs"], "Infrastructure cost record differs"
        )
    value = {
        "passed": True,
        "archive_bytes": expected["bytes"],
        "archive_sha256": expected["sha256"],
        "manifest_members": len(manifest),
        "expanded_bytes": expanded,
        "condition": job["condition"],
        "pair_id": job["pair_id"],
        "source_digest": job["source_digest"],
        "source_files": len(source),
        "actual_context": 272000,
        "registry_sha256": job["registry_sha256"],
        "model_evidence": dict(totals),
        "memory_boundary_verified": True,
        "original_strict_audit_verified": True,
        "game_replayed_locally": False,
        "reasoning_is_output_subset": True,
        "unreported_usage_is_unknown": True,
    }
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=True, indent=2)
    return value
