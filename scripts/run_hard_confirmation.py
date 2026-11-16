"""Start the explicitly authorized full Hard candidate through the managed service."""

import argparse
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
from scripts.run_hard_calibration import preflight_job


PROJECT = Path(__file__).resolve().parents[1]
POLICY = "config/authorized-hard-binding36-retain.json"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate(review, policy, project):
    """Refuse extra conditions, changed science or accidentally reused pilot worlds."""
    required = {
        "agent": "hermes",
        "model": "gpt-5.6-luna",
        "conditions": ["retain"],
        "tasks_per_condition": 36,
        "total_tasks": 36,
        "context_tokens": 272000,
        "movement_mode": "step",
        "main_model_calls": 400,
        "final_model_calls": 6,
        "game_steps": 352,
        "effective_wall_seconds": 604800,
        "infrastructure_wait_seconds": 604800,
        "reasoning_effort": "high",
        "design_id": policy["design_id"],
        "registry_sha256": policy["registry_sha256"],
    }
    if any(review.get(key) != value for key, value in required.items()):
        raise ValueError(
            "Full confirmation does not match the explicit retain-only contract"
        )
    if (
        policy["conditions"] != ["retain"]
        or policy["maximum_total_tasks"] != 36
        or policy["maximum_groups"] != 1
        or policy["world_seed"] != 61501
        or policy["launch_clear"]
        or policy["import_calibration_memory"]
    ):
        raise ValueError("This authorization permits one fresh retained world only")
    design = Path(project) / "memorybenchmark/data" / policy["design_file"]
    if sha256(design.read_bytes()).hexdigest() != policy["design_sha256"]:
        raise ValueError("Reviewed full36 design changed before preparation")


def execute(runtime_config):
    policy = read(PROJECT / POLICY)
    config = replace(RuntimeConfig.load(runtime_config), project=PROJECT)
    config.private_root.mkdir(parents=True, exist_ok=True)
    service = ExperimentService(
        config,
        WindowsScheduler(),
        conditions=("retain",),
        maps={
            policy["map"]: (
                "奥尔恰Hard组合完整确认",
                "Hard confirmation",
                policy["design_file"],
            )
        },
    )
    request = {
        key: policy[key] for key in ("model", "map", "movement_mode", "request_id")
    }
    validate(service.preview(request), policy, PROJECT)
    with exclusive(config.private_root / "hard-binding36-confirmation.owner.lock"):
        prepared = service.prepare(request)
        group = service.repository.read(prepared["id"])
        if group["phase"] == "dispatched":
            print(json.dumps({"id": group["id"], "phase": "already_dispatched"}))
            return
        if [job["condition"] for job in group["jobs"]] != ["retain"]:
            raise ValueError("Unexpected counterpart; nothing dispatched")
        job = group["jobs"][0]
        root = Path(job["root"])
        if (root.parent / "clear").exists():
            raise ValueError("Unexpected clear root; do not launch or erase it")
        command = [
            str(config.python),
            "-X",
            "utf8",
            "-m",
            "scripts.run_hard_confirmation",
            "--preflight-job",
            str(root / "job.json"),
        ]
        result = subprocess.run(
            command,
            cwd=root / "runtime-hermes",
            capture_output=True,
            timeout=policy["native_preparation_timeout_seconds"],
        )
        (root / "preflight.stdout.log").write_bytes(result.stdout)
        (root / "preflight.stderr.log").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(
                "Owned zero-model preflight failed; inspect its saved error before dispatch"
            )
        receipt = read(root / "preflight.json")
        baseline_sha = sha256(
            json.dumps(receipt["baseline"], sort_keys=True).encode()
        ).hexdigest()
        if (
            not receipt["passed"]
            or receipt["model_calls"] != 0
            or baseline_sha != policy["baseline_manifest_sha256"]
        ):
            raise ValueError(
                "Full confirmation must start from the pristine native baseline"
            )
        atomic_json(
            root / "confirmation-authorization.json",
            {
                "authorization": policy,
                "baseline_sha256": baseline_sha,
                "source_digest": job["source_digest"],
                "prior_learning_imported": False,
            },
        )
        dispatched = service.create(request)
        atomic_json(root.parent / "dispatch.json", dispatched)
        print(json.dumps(dispatched, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--preflight-job", type=Path)
    args = parser.parse_args()
    if args.preflight_job:
        preflight_job(args.preflight_job)
    elif args.runtime_config:
        execute(args.runtime_config)
    else:
        parser.error(
            "Select an authorized server runtime or an owned zero-model preflight"
        )


if __name__ == "__main__":
    main()
