"""Prepare and dispatch one reviewed Lunatic pilot."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from memorybenchmark.experiments.config import RuntimeConfig
from memorybenchmark.experiments.repository import exclusive
from memorybenchmark.experiments.scheduler import WindowsScheduler
from memorybenchmark.experiments.service import ExperimentService
from memorybenchmark.watch import atomic_json
from scripts.run_hard_calibration import read


PROJECT = Path(__file__).resolve().parents[1]
PAIRED_POLICY = "config/authorized-lunatic-recall-pilot.json"
GOAL_SWITCH_POLICY = "config/authorized-lunatic-goal-switch-retain.json"
EXPANDED_GOAL_SWITCH_POLICY = (
    "config/authorized-lunatic-goal-switch-expanded-retain.json"
)
FULL_GOAL_SWITCH_POLICY = "config/authorized-lunatic-goal-switch-full-retain.json"
CONDITIONS = {
    PAIRED_POLICY: ("retain", "clear"),
    GOAL_SWITCH_POLICY: ("retain",),
    EXPANDED_GOAL_SWITCH_POLICY: ("retain",),
    FULL_GOAL_SWITCH_POLICY: ("retain",),
}


def probe(job, config, expected_baseline):
    root = Path(job["root"])
    if not (root / "preflight.json").exists():
        result = subprocess.run(
            [
                str(config.python),
                "-X",
                "utf8",
                "-m",
                "scripts.run_hard_calibration",
                "--preflight-job",
                str(root / "job.json"),
            ],
            cwd=root / "runtime-hermes",
            capture_output=True,
            timeout=3600,
        )
        (root / "preflight.stdout.log").write_bytes(result.stdout)
        (root / "preflight.stderr.log").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("Inspect the owned Lunatic preflight error")
    receipt = read(root / "preflight.json")
    baseline = sha256(
        json.dumps(receipt["baseline"], sort_keys=True).encode()
    ).hexdigest()
    if (
        receipt["passed"] is not True
        or receipt["model_calls"] != 0
        or receipt["source_digest"] != job["source_digest"]
        or baseline != expected_baseline
    ):
        raise ValueError("Lunatic preflight did not match its frozen job and baseline")
    return baseline


def execute(runtime_path, authorization=PAIRED_POLICY):
    if authorization not in CONDITIONS:
        raise ValueError("Select an explicitly authorized Lunatic pilot")
    conditions = CONDITIONS[authorization]
    policy = read(PROJECT / authorization)
    config = replace(RuntimeConfig.load(runtime_path), project=PROJECT)
    request = {**policy["selection"], "request_id": policy["request_id"]}
    service = ExperimentService(
        config,
        WindowsScheduler(),
        conditions=conditions,
        maps={request["map"]: ("斯堪的纳维亚", "Lunatic pilot", policy["design_file"])},
    )
    review = service.preview(request)
    design = service.design_path(request["map"])
    if any(review.get(key) != value for key, value in policy["review"].items()):
        raise ValueError("The pilot preview differs from the authorized scope")
    if sha256(design.read_bytes()).hexdigest() != policy["design_sha256"]:
        raise ValueError("The reviewed pilot design has changed")
    with exclusive(config.private_root / (policy["request_id"] + ".owner.lock")):
        prepared = service.prepare(request)
        pair = service.repository.read(prepared["id"])
        jobs = pair["jobs"]
        group_root = service.repository.pair_directory(pair["id"])
        if tuple(job["condition"] for job in jobs) != conditions or (
            conditions == ("retain",) and (group_root / "clear").exists()
        ):
            raise ValueError("Prepared conditions differ from the authorization")
        if pair["phase"] == "dispatched":
            return prepared
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            probes = [
                pool.submit(probe, job, config, policy["baseline_manifest_sha256"])
                for job in jobs
            ]
            baselines = {
                job["condition"]: check.result() for job, check in zip(jobs, probes)
            }
        atomic_json(
            group_root / "preflight.json",
            {"passed": True, "model_calls": 0, "baseline_sha256": baselines},
        )
        return service.create(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--authorization", choices=CONDITIONS, default=PAIRED_POLICY)
    args = parser.parse_args()
    print(
        json.dumps(execute(args.runtime_config, args.authorization), ensure_ascii=True)
    )


if __name__ == "__main__":
    main()
