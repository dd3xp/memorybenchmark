"""Prepare and dispatch the initial twelve-task Lunatic pair."""

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
POLICY = PROJECT / "config/authorized-lunatic-recall-pilot.json"


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


def execute(runtime_path):
    policy = read(POLICY)
    config = replace(RuntimeConfig.load(runtime_path), project=PROJECT)
    request = {**policy["selection"], "request_id": policy["request_id"]}
    service = ExperimentService(
        config,
        WindowsScheduler(),
        maps={request["map"]: ("斯堪的纳维亚", "Lunatic pilot", policy["design_file"])},
    )
    review = service.preview(request)
    design = service.design_path(request["map"])
    if any(review.get(key) != value for key, value in policy["review"].items()):
        raise ValueError("The pilot preview differs from the paired scope")
    if sha256(design.read_bytes()).hexdigest() != policy["design_sha256"]:
        raise ValueError("The reviewed pilot design has changed")
    with exclusive(config.private_root / (policy["request_id"] + ".owner.lock")):
        prepared = service.prepare(request)
        pair = service.repository.read(prepared["id"])
        if pair["phase"] == "dispatched":
            return prepared
        jobs = pair["jobs"]
        if [job["condition"] for job in jobs] != ["retain", "clear"]:
            raise ValueError("Prepare and verify both independent conditions")
        with ThreadPoolExecutor(max_workers=2) as pool:
            probes = [
                pool.submit(probe, job, config, policy["baseline_manifest_sha256"])
                for job in jobs
            ]
            baselines = {
                job["condition"]: check.result() for job, check in zip(jobs, probes)
            }
        atomic_json(
            service.repository.pair_directory(pair["id"]) / "preflight.json",
            {"passed": True, "model_calls": 0, "baseline_sha256": baselines},
        )
        return service.create(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.runtime_config), ensure_ascii=True))


if __name__ == "__main__":
    main()
