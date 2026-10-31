"""One complete longitudinal station experiment, with no peer or coordinator.

Run this entry point in separate processes/output directories for retain and
clear. Both conditions advance their own actual game history. Only the choice
of persistent memory between tasks differs. Comparison is an offline operation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from ..agent_adapters import load_adapter
from ..errors import InfrastructureError
from ..ga_runtime import WSLJail, memory_manifest
from ..model_gateway import GatewayModel
from ..watch import atomic_json as save_json
from .station_capability import StationGame, load_design, map_world
from .station_parallel import _archive_failed, _completed_peer, _transport_peer, read, transport_failure
from .station_pilot import PROMPT_PROTOCOL, StationNativeSessions, replay_checkpoint
from .station_session import EASY20_REUSE_DESIGN, FEEDBACK_PROTOCOLS


PROTOCOL = "station-independent-experiment-1"


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def ownership(output):
    """An OS lock belongs to this run alone and is released on process death."""
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output.with_name(output.name + ".owner.lock")
    with lock_path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("This experiment already has an owner") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def initialize(output, archive, *, agent, condition, design_path=EASY20_REUSE_DESIGN,
               tasks=None, seed=20261029, model_alias="gpt-5.6-luna", max_turns=100,
               final_turns=6, wall_seconds=3600, transport_retries=2,
               transport_failure_limit=8):
    if agent not in ("ga", "hermes") or condition not in ("retain", "clear"):
        raise ValueError("Specify a native agent and one memory condition")
    for value, minimum in ((max_turns, 1), (final_turns, 0), (transport_retries, 0), (transport_failure_limit, 0)):
        if type(value) is not int or value < minimum:
            raise ValueError("Invalid experiment budget")
    if type(wall_seconds) is not int or not 10 <= wall_seconds <= 3600:
        raise ValueError("Invalid session time limit")
    design = load_design(design_path)
    selected = list(tasks if tasks is not None else design["tasks"])
    if not selected or len(set(selected)) != len(selected) or any(t not in design["tasks"] for t in selected):
        raise ValueError("Tasks must be unique members of the design")
    world = map_world(design)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    load_adapter(agent).prepare(archive, output)
    # Freeze all locally executed package/audit code, independently for each run.
    repo = Path(__file__).resolve().parents[2]
    paths = sorted((repo / "memorybenchmark").rglob("*.py")) + sorted((repo / "scripts").glob("*.py"))
    paths += [Path(design_path).resolve()]
    report = {
        "protocol": PROTOCOL, "experiment_mode": "independent", "experiment_id": uuid4().hex,
        "memory_condition": condition, "agent": agent, "status": "ready", "created_at_utc": now(),
        "seed": seed, "design_id": design["design_id"], "world": world, "tasks": selected,
        "model_alias": model_alias, "max_turns": max_turns, "final_turns": final_turns,
        "wall_seconds": wall_seconds, "transport_retries": transport_retries,
        "transport_failure_limit": transport_failure_limit,
        "game_access": "native", "action_policy": "single", "movement_mode": "step",
        "clear_first_task": True, "feedback_mode": "compact",
        "feedback_protocol": FEEDBACK_PROTOCOLS["compact"], "prompt_protocol": PROMPT_PROTOCOL,
        "agent_game_interface": "ga-code-run-client-1" if agent == "ga" else "hermes-native-mcp-1",
        "world_sampling": "fixed map assignment; no runtime sampling",
        "map_configuration_sha256": sha256(Path(design_path).read_bytes()).hexdigest(),
        "station_assignment_sha256": sha256(json.dumps(design["private_worlds"][world], sort_keys=True).encode()).hexdigest(),
        "archive_sha256": sha256(Path(archive).read_bytes()).hexdigest(),
        "implementation_sha256": {str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in paths},
        "baseline_memory": memory_manifest(output / "baseline"),
        "history_policy": "advance only this experiment's own completed sessions",
        "memory_policy": "inherit own preceding memory" if condition == "retain" else "restore original native baseline before every task",
        "comparison": "independent longitudinal runs; compare offline after completion",
        "sessions": [], "attempt_history": [],
    }
    save_json(output / "design.json", design)
    save_json(output / "pilot.json", report)
    return report


def execute(output, jail, model, *, retry_delay=15):
    """Caller holds this output's ownership lock; no other run is consulted."""
    output = Path(output).resolve()
    report = read(output / "pilot.json")
    if report.get("protocol") != PROTOCOL or report.get("experiment_mode") != "independent":
        raise ValueError("Cannot convert or resume a paired pilot as an independent experiment")
    if report["memory_condition"] not in ("retain", "clear"):
        raise ValueError("Invalid memory condition")
    if report["status"] == "completed":
        return report
    for path, digest in report["implementation_sha256"].items():
        if sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Frozen experiment implementation changed")
    baseline = output / "baseline"
    if memory_manifest(baseline) != report["baseline_memory"]:
        raise RuntimeError("Original native baseline was modified")
    condition, agent = report["memory_condition"], report["agent"]
    names = [f"{i+1:02d}-{task}-{condition}" for i, task in enumerate(report["tasks"])]
    if len({r["name"] for r in report["sessions"]}) != len(report["sessions"]) or any(
        r["name"] not in names or r["condition"] != condition for r in report["sessions"]
    ):
        raise RuntimeError("Experiment manifest contains foreign or duplicate sessions")
    design = read(output / "design.json")
    sessions = StationNativeSessions(output / "source" / ("GenericAgent" if agent == "ga" else "hermes-agent"),
        output / "support", jail, agent=agent, feedback_mode=report["feedback_mode"],
        game_access="native", action_policy="single", movement_mode="step", model_alias=report["model_alias"],
        seed=report["seed"], max_turns=report["max_turns"], final_turns=report["final_turns"], wall_seconds=report["wall_seconds"])
    report["status"] = "running"
    report.setdefault("starts", []).append({"at_utc": now(), "pid": os.getpid()})
    save_json(output / "pilot.json", report)
    def event(kind, **fields):
        with (output / "scheduling.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind, "utc": now(), "experiment_id": report["experiment_id"], **fields}) + "\n")
    canonical, memory = [], baseline
    game = StationGame(report["world"], design)
    try:
        if not (output / "probe/summary.json").is_file():
            sessions.probe(baseline, output / "probe")
        for task, name in zip(report["tasks"], names):
            folder = output / "sessions" / name
            input_memory = memory if condition == "retain" else baseline
            while True:
                row = next((r for r in report["sessions"] if r["name"] == name), None)
                if row is not None:
                    # Validate recorded results as strictly as crash-orphaned ones.
                    verified = (_completed_peer if row["infrastructure_ok"] else _transport_peer)(
                        folder, game, task, condition, input_memory, report)
                    if {k: v for k, v in row.items() if k != "name"} != verified:
                        raise RuntimeError("Manifest differs from saved session")
                elif folder.exists():
                    saved = read(folder / "summary.json") if (folder / "summary.json").is_file() else {}
                    result = (_transport_peer if transport_failure(saved) else _completed_peer)(
                        folder, game, task, condition, input_memory, report)
                    row = {"name": name, **result}
                    report["sessions"].append(row)
                    report["sessions"].sort(key=lambda r: names.index(r["name"]))
                    save_json(output / "pilot.json", report)
                    event("saved_session_recovered", name=name, infrastructure_ok=row["infrastructure_ok"])
                if row is not None and row["infrastructure_ok"]:
                    break
                if row is not None:
                    if not transport_failure(row):
                        raise InfrastructureError("Unknown infrastructure failure; preserve this run for inspection")
                    count = sum(r["name"] == name for r in report["attempt_history"])
                    if count >= report["transport_retries"] or len(report["attempt_history"]) >= report["transport_failure_limit"]:
                        raise InfrastructureError("This experiment's transport retry budget is exhausted")
                    _archive_failed(output, report, row)
                    event("transport_retry", name=name, attempt=count + 2)
                    if retry_delay:
                        time.sleep(retry_delay)
                event("session_started", name=name, task=task, condition=condition,
                      prior_events_sha256=sha256(json.dumps(game.events, sort_keys=True).encode()).hexdigest())
                result = sessions.run(deepcopy(game), task, input_memory, folder, model, condition=condition)
                report["sessions"].append({"name": name, **result})
                report["sessions"].sort(key=lambda r: names.index(r["name"]))
                save_json(output / "pilot.json", report)
                event("session_finished", name=name, infrastructure_ok=result["infrastructure_ok"])
                print(json.dumps({"name": name, **{k: result.get(k) for k in ("success", "distance", "llm_calls", "content_changed")}}, ensure_ascii=False), flush=True)
                # Validation, retry, or continuation happens in this run only.
            canonical.append(folder)
            game = replay_checkpoint(design, report["world"], canonical)
            if condition == "retain":
                memory = folder / "memory-after"
        report["status"] = "completed"
        report["completed_at_utc"] = now()
        report.pop("last_error", None)
    except BaseException as error:
        report["status"] = "interrupted"
        report["last_error"] = {"type": type(error).__name__, "message": str(error), "at_utc": now()}
        save_json(output / "pilot.json", report)
        raise
    save_json(output / "pilot.json", report)
    return report


def experiment(output, jail, model, *, archive=None, resume=False, **options):
    with ownership(output):
        if not resume:
            if archive is None:
                raise ValueError("A native archive is required for a fresh experiment")
            initialize(output, archive, **options)
        elif options:
            report = read(Path(output) / "pilot.json")
            for key, value in options.items():
                if key == "design_path":
                    if sha256(Path(value).read_bytes()).hexdigest() != report["map_configuration_sha256"]:
                        raise ValueError("Cannot change experiment design on resume")
                    continue
                recorded_key = "memory_condition" if key == "condition" else key
                if recorded_key not in report or report[recorded_key] != value:
                    raise ValueError("Cannot change experiment configuration on resume: " + key)
        return execute(output, jail, model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--agent", choices=("ga", "hermes"))
    parser.add_argument("--condition", choices=("retain", "clear"))
    parser.add_argument("--design", type=Path, default=EASY20_REUSE_DESIGN)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Freeze a separate run without a model call")
    args = parser.parse_args()
    if args.resume and args.prepare_only:
        parser.error("prepare-only applies to fresh experiments")
    if not args.resume and (not args.archive or not args.agent or not args.condition):
        parser.error("A fresh experiment requires archive, agent and condition")
    if args.resume:
        frozen = read(args.output / "pilot.json")
        if args.agent is not None and args.agent != frozen["agent"]:
            parser.error("Cannot change agent on resume")
        if args.condition is not None and args.condition != frozen["memory_condition"]:
            parser.error("Cannot change memory condition on resume")
    if args.prepare_only:
        with ownership(args.output):
            initialize(args.output, args.archive, agent=args.agent, condition=args.condition, design_path=args.design, model_alias=args.model)
        return
    key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
    if not key:
        parser.error("Set MEMORYBENCH_GATEWAY_KEY in the parent host")
    model_alias = read(args.output / "pilot.json")["model_alias"] if args.resume else args.model
    model = GatewayModel(args.base_url, key, model_alias, None)
    options = {} if args.resume else dict(agent=args.agent, condition=args.condition, design_path=args.design, model_alias=args.model)
    experiment(args.output, WSLJail(args.distro, args.runtime, args.runtime_dependency), model,
               archive=args.archive, resume=args.resume, **options)


if __name__ == "__main__":
    main()
