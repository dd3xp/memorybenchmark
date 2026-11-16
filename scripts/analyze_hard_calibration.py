"""Read a sealed managed result once; never run another game audit or model."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import zipfile

from memorybenchmark.experiments.calibration import summarize
from memorybenchmark.experiments.verification import authorized_task_count
from memorybenchmark.watch import atomic_json


def analyze(root):
    root = Path(root)
    result_path = root / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    exited = json.loads((root / "driver-exit.json").read_text(encoding="utf-8-sig"))
    if (
        not result.get("archive", {}).get("contents_verified")
        or exited.get("exit_code") != 0
    ):
        raise ValueError(
            "Wait for the original driver to finish its own audit and archive"
        )
    output = root / "calibration-metrics.json"
    checksum = sha256(result_path.read_bytes()).hexdigest()
    if output.exists():
        previous = json.loads(output.read_text(encoding="utf-8"))
        if previous["source_result_sha256"] != checksum:
            raise ValueError("The sealed source result changed")
        return previous
    value = summarize(result)
    with zipfile.ZipFile(root / result["archive"]["name"]) as archive:
        names = set(archive.namelist())
        job = json.loads(archive.read("provenance/job.json"))
        expected_tasks = authorized_task_count(job, job["source_digest"])
        if (
            job["condition"],
            job["model"],
            job["context_tokens"],
            job["movement_mode"],
            job["tasks_per_condition"],
        ) != (result["condition"], "gpt-5.6-luna", 272000, "step", expected_tasks):
            raise ValueError("Sealed result does not match the authorized calibration")
        for row in result["rows"]:
            summary = json.loads(
                archive.read(f"run/sessions/{row['name']}/summary.json")
            )
            actual = summary["initial_session"]["native_context_configuration"]
            if (
                actual["model_context_length"] != 272000
                or actual["registry_sha256"] != job["registry_sha256"]
                or actual["model"] != job["model"]
            ):
                raise ValueError("Actual native context does not match this job")
    expected = [
        f"run/sessions/{row['name']}/transport-attempts.jsonl"
        for row in result["rows"]
        if row["model_usage"]["calls"]
    ]
    if not all(name in names for name in expected):
        value["infrastructure_costs"] = {
            "status": "unknown; canonical transport ledger missing"
        }
    value.update(
        source_result_sha256=checksum,
        server_sealed_audit_passed=True,
        local_archive_verification="pending",
        transport_ledger_inventory_present=all(name in names for name in expected),
        actual_context=272000,
        registry_sha256=job["registry_sha256"],
        design_id=job["design_id"],
        source_digest=job["source_digest"],
    )
    atomic_json(output, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    value = analyze(args.root)
    print(
        json.dumps(
            {
                k: value[k]
                for k in (
                    "condition",
                    "tasks",
                    "after_first_planned_goal_encounter",
                    "combined_with_both_prior_actual_facts",
                    "distance",
                    "model_calls",
                )
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
