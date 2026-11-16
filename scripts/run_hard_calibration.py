"""Prepare, zero-model probe and dispatch one explicitly bounded native pair.

Run from an isolated installed source copy on Squishy. No existing project's
catalog, frozen executor, experiment root or task is modified by this entry.
"""

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from memorybenchmark.experiments.config import RuntimeConfig
from memorybenchmark.experiments.repository import exclusive
from memorybenchmark.experiments.scheduler import WindowsScheduler
from memorybenchmark.experiments.service import ExperimentService
from memorybenchmark.watch import atomic_json
from memorybenchmark.experiments.calibration import choose_followup
from scripts.analyze_hard_calibration import analyze


PROJECT = Path(__file__).resolve().parents[1]
MAP = "orcia-hard-interface-calibration"
DESIGN = "calibration/orcia_interface12.json"
FOLLOWUP_DESIGNS = {
    "binding": "calibration/orcia_binding12.json",
    "interface-confirmation": "calibration/orcia_interface_confirmation12.json",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def preflight_job(path):
    from memorybenchmark.experiments.freezer import verify
    from memorybenchmark.ga_runtime import WSLJail, memory_manifest
    from memorybenchmark.prototypes.station_independent import initialize, ownership
    from memorybenchmark.prototypes.station_pilot import StationNativeSessions

    job = read(path)
    root = Path(path).resolve().parent
    if Path(job["root"]).resolve() != root or job["schema"] != "benchmark-job-1":
        raise ValueError("Preflight job does not own its directory")
    runtime = root / "runtime-hermes"
    if PROJECT.resolve() != runtime.resolve():
        raise ValueError("Preflight must execute inside this job's frozen source")
    verify(runtime, job["source_digest"])
    run = (
        runtime
        / ".runs"
        / f"pilot-hermes-{job['condition']}-{job['map']}-{job['pair_id'][:12]}"
    )
    with ownership(run):
        if not (run / "pilot.json").exists():
            initialize(
                run,
                Path(job["native_archive"]),
                agent="hermes",
                condition=job["condition"],
                design_path=runtime / "memorybenchmark/data" / job["design_file"],
                model_alias=job["model"],
                reasoning_effort="high",
                movement_mode="step",
                transport_retries=0,
                transport_failure_limit=0,
                wall_seconds=604800,
            )
        pilot = read(run / "pilot.json")
        if pilot["sessions"] or pilot["status"] != "ready":
            raise ValueError(
                "Preflight cannot inspect or relaunch a running scientific session"
            )
        native = StationNativeSessions(
            run / "source/hermes-agent",
            run / "support",
            WSLJail(job["distro"], job["native_runtime"], job["runtime_dependencies"]),
            agent="hermes",
            feedback_mode="compact",
            game_access="native",
            action_policy="single",
            movement_mode="step",
            model_alias=job["model"],
            reasoning_effort="high",
            max_turns=400,
            final_turns=6,
            wall_seconds=604800,
        )
        if (run / "probe/summary.json").exists():
            probe = read(run / "probe/summary.json")
        else:
            probe = native.probe(run / "baseline", run / "probe")
        if (
            not probe["infrastructure_ok"]
            or probe["llm_calls"] != 0
            or probe.get("model_requests", 0) != 0
        ):
            raise ValueError("Zero-model native probe did not pass")
        support = {}
        for source in (run / "support").glob("*.py"):
            frozen = runtime / "memorybenchmark" / source.name
            if frozen.exists():
                if frozen.read_bytes() != source.read_bytes():
                    raise ValueError(
                        "Executed support preparation changed source bytes"
                    )
                support[source.name] = sha256(source.read_bytes()).hexdigest()
        receipt = {
            "passed": True,
            "model_calls": 0,
            "run": str(run),
            "baseline": memory_manifest(run / "baseline"),
            "actual_native_probe": True,
            "support_sha256": support,
            "source_digest": job["source_digest"],
        }
        atomic_json(root / "preflight.json", receipt)
    print(json.dumps({"condition": job["condition"], "passed": True, "model_calls": 0}))


def execute(runtime_config, round_number):
    policy = read(PROJECT / "config/authorized-hard-calibration.json")
    if not 1 <= round_number <= policy["maximum_rounds"]:
        raise ValueError("Requested calibration exceeds the two-round authorization")
    original = RuntimeConfig.load(runtime_config)
    private_root = original.private_root / "hard-calibration-native"
    private_root.mkdir(exist_ok=True)
    config = replace(original, project=PROJECT, private_root=private_root)
    design_file = DESIGN
    decision = None
    if round_number == 2:
        previous_id = ExperimentService(config, WindowsScheduler()).repository.pair_id(
            "hard-interface-calibration-round-1-v1"
        )
        previous = read(config.experiments / previous_id / "pair.json")
        owned = [j for j in previous["jobs"] if j["condition"] == "retain"]
        if (
            len(owned) != 1
            or Path(owned[0]["root"]).resolve()
            != (config.experiments / previous_id / "retain").resolve()
        ):
            raise ValueError(
                "Previous retained result does not own this calibration slot"
            )
        metrics = analyze(Path(owned[0]["root"]))
        if metrics["design_id"] != "hard-interface-calibration-v1-61301-12":
            raise ValueError(
                "Previous retained pilot used a different calibration design"
            )
        decision = {
            **choose_followup(metrics),
            "source_result_sha256": metrics["source_result_sha256"],
            "prior_pair": previous_id,
            "retained_metrics": metrics,
            "previous_clear_keeps_running_independently": True,
        }
        design_file = FOLLOWUP_DESIGNS[decision["variant"]]
    service = ExperimentService(
        config,
        WindowsScheduler(),
        maps={MAP: ("奥尔恰Hard候选校准", "Hard calibration", design_file)},
    )
    request = {
        "model": policy["model"],
        "map": MAP,
        "movement_mode": "step",
        "request_id": f"hard-interface-calibration-round-{round_number}-v1",
    }
    with exclusive(private_root / "authorization.lock"):
        if decision is not None:
            path = private_root / "round-2-decision.json"
            if path.exists() and read(path) != decision:
                raise ValueError(
                    "A followup decision already exists; preserve its original source"
                )
            if not path.exists():
                atomic_json(path, decision)
        review = service.preview(request)
        if (
            review["tasks_per_condition"],
            review["total_tasks"],
            review["context_tokens"],
            review["main_model_calls"],
            review["game_steps"],
        ) != (12, 24, 272000, 400, 352):
            raise ValueError(
                "Candidate does not match the authorized calibration contract"
            )
        prepared = service.prepare(request)
        pair = service.repository.read(prepared["id"])
        if pair["phase"] == "dispatched":
            print(json.dumps({"id": pair["id"], "phase": "already_dispatched"}))
            return
        receipts = []
        for job in pair["jobs"]:
            root = Path(job["root"])
            command = [
                str(config.python),
                "-X",
                "utf8",
                "-m",
                "scripts.run_hard_calibration",
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
                    "Native preflight failed; inspect its saved stderr before any dispatch"
                )
            receipts.append(read(root / "preflight.json"))
        if receipts[0]["baseline"] != receipts[1]["baseline"]:
            raise ValueError("Paired original baselines differ")
        atomic_json(
            private_root / f"round-{round_number}-preflight.json",
            {
                "passed": True,
                "model_calls": 0,
                "pair_id": pair["id"],
                "receipts": receipts,
            },
        )
        result = service.create(request)
        atomic_json(private_root / f"round-{round_number}-dispatch.json", result)
        print(json.dumps(result, ensure_ascii=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--preflight-job", type=Path)
    args = parser.parse_args()
    if args.preflight_job:
        preflight_job(args.preflight_job)
    elif args.runtime_config:
        execute(args.runtime_config, args.round)
    else:
        parser.error("Select a server runtime configuration or a zero-model owned job")


if __name__ == "__main__":
    main()
