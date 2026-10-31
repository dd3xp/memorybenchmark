"""Resume frozen station cohorts with isolated, concurrent current-task branches.

Only scheduling changes. Each pair forks the same canonical checkpoint, the
retained history advances in task order, and clear outputs are never inherited.
The original runner/agent files and completed session records remain unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

from ..errors import InfrastructureError
from ..ga_runtime import WSLJail, memory_manifest
from ..model_gateway import GatewayModel
from ..watch import atomic_json as save_json
from .station_capability import StationGame
from .station_pilot import StationNativeSessions, replay_checkpoint
from .station_session import StationSession
from scripts.check_station_capability import trace_graph


PROTOCOL = "station-paired-parallel-1"
GUARD = ".parallel-handoff.json"
TRANSPORT_ERRORS = ("gateway_transport_error", "gateway_http_429", "gateway_http_500",
                    "gateway_http_502", "gateway_http_503", "gateway_http_504",
                    "incomplete model stream", "model response did not complete", "model stream budget exceeded")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def transport_failure(row):
    error = str(row.get("infrastructure_error", "")) + " " + str(row.get("underlying_infrastructure_error", ""))
    return row.get("infrastructure_ok") is False and any(term in error for term in TRANSPORT_ERRORS)


def schedule(report):
    for index, task in enumerate(report["tasks"]):
        keep = "prefix" if index == 0 else "retain"
        conditions = (keep, "clear") if index or report.get("clear_first_task", False) else (keep,)
        yield task, [(f"{index+1:02d}-{task}-{condition}", condition) for condition in conditions]


def reserve_handoff(output):
    """Reserve the next unopened session directory as a non-destructive barrier.

    The serial runner finishes its active session, saves it, then its exclusive
    mkdir stops before the next worker can start. No running worker is killed
    and no frozen source is patched. The migration driver recognizes this
    planned FileExistsError and releases only its own empty reservation.
    """
    output = Path(output).resolve()
    report = read(output / "pilot.json")
    if report["status"] == "completed":
        raise ValueError("Cohort already completed")
    for _, pair in schedule(report):
        for name, _ in pair:
            folder = output / "sessions" / name
            try:
                folder.mkdir()
            except FileExistsError:
                continue
            reservation = {"protocol": PROTOCOL, "token": uuid4().hex, "reserved_session": name,
                           "created_at_utc": datetime.now(timezone.utc).isoformat()}
            save_json(folder / GUARD, reservation)
            return reservation
    raise ValueError("No unopened session remains")


def release_handoff(output, reservation):
    output = Path(output).resolve()
    folder = output / "sessions" / reservation["reserved_session"]
    if folder.is_symlink() or not folder.resolve().is_relative_to(output):
        raise ValueError("Handoff escaped its experiment")
    if read(folder / GUARD) != reservation or {p.name for p in folder.iterdir()} != {GUARD}:
        raise ValueError("Handoff reservation contains unexpected data")
    (folder / GUARD).unlink()
    folder.rmdir()  # Deliberately nonrecursive; never discard a worker artifact.


def _archive_failed(output, report, row):
    if not transport_failure(row):
        raise InfrastructureError("Unknown interruption; preserve evidence for review")
    source = output / "sessions" / row["name"]
    destination = output / "failed-attempts" / (row["name"] + "-" + str(len(report.get("attempt_history", [])) + 1))
    if source.is_symlink() or not source.resolve(strict=True).is_relative_to(output) or not destination.resolve().is_relative_to(output):
        raise ValueError("Attempt archive escaped its experiment")
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        raise FileExistsError("Attempt archive already exists")
    source.rename(destination)
    report.setdefault("attempt_history", []).append({**row, "archived_at": str(destination.relative_to(output))})
    report["sessions"].remove(row)
    save_json(output / "pilot.json", report)


def _completed_peer(folder, checkpoint, task, condition, memory, report):
    """Validate a completed worker result left behind by a coordinator failure.

    A saved directory alone is insufficient. Replay the complete game evidence,
    verify both memory manifests, native context isolation, response counts and
    delivery hashes before adopting the already executed result.
    """
    if folder.is_symlink() or not (folder / "summary.json").is_file():
        raise RuntimeError("Unrecorded session directory; inspect before retrying")
    result = read(folder / "summary.json")
    if not result.get("infrastructure_ok") or result.get("task_id") != task or result.get("condition") != condition:
        raise RuntimeError("Unrecorded session is not a completed matching branch")
    if read(folder / "prior-events.json") != checkpoint.events:
        raise RuntimeError("Completed peer has a different canonical history")
    expected = memory_manifest(memory)
    if read(folder / "memory-before.json") != expected or result.get("input_memory") != expected:
        raise RuntimeError("Completed peer has a different input memory")
    if memory_manifest(folder / "memory-after") != result.get("output_memory"):
        raise RuntimeError("Completed peer output memory differs from its saved manifest")
    current = deepcopy(checkpoint)
    initial = StationSession(current, task, feedback_mode=report["feedback_mode"]).initial
    if read(folder / "initial-public.json")["observation"] != initial["observation"]:
        raise RuntimeError("Completed peer has a different initial public state")
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    for event in events[len(current.events):]:
        if event["task_run_id"] != current.task_run_id:
            raise RuntimeError("Completed peer contains another task's actions")
        if event["kind"] == "action":
            current.step(event["action"])
        elif event["kind"] == "runner_terminated":
            current.finish_incomplete(event["delivered"]["feedback"]["reason"])
        else:
            raise RuntimeError("Unknown completed peer event")
        if current.events[-1] != event:
            raise RuntimeError("Completed peer feedback differs from replay")
    if not current.done or current.events != events or trace_graph(current) != read(folder / "graph.json"):
        raise RuntimeError("Completed peer trace differs from replay")
    if (current.state.success, current.steps, current.distance) != (result.get("success"), result.get("game_actions"), result.get("distance")):
        raise RuntimeError("Completed peer costs differ from replay")
    initial = result.get("initial_session", {})
    if initial.get("initial_history_size") != 0 or initial.get("initial_backend_history_size") != 0 or initial.get("working") != {}:
        raise RuntimeError("Completed peer context was not isolated")
    if not initial.get("isolation") or not all(v for k, v in initial["isolation"].items() if k != "pid"):
        raise RuntimeError("Completed peer worker isolation is unverified")
    calls = result.get("llm_calls")
    if len(list((folder / "model").glob("*-request.json"))) != calls or len(list((folder / "model").glob("*-response.json"))) != calls:
        raise RuntimeError("Completed peer has incomplete model responses")
    if not 0 <= result.get("main_calls", -1) <= report["max_turns"] or not 0 <= result.get("final_calls", -1) <= report["final_turns"]:
        raise RuntimeError("Completed peer exceeded its model budget")
    if result["main_calls"] + result["final_calls"] != calls or result.get("action_policy") != report["action_policy"]:
        raise RuntimeError("Completed peer has a different execution contract")
    from scripts.check_ga_single_action import check_boundaries
    if check_boundaries(folder)["rejected_extra_actions"] != result.get("action_policy_rejections"):
        raise RuntimeError("Completed peer action boundary log differs from its summary")
    if result.get("worker_returncode") != 0 or sha256((folder / "game-deliveries.jsonl").read_bytes()).hexdigest() != result.get("game_deliveries_sha256"):
        raise RuntimeError("Completed peer worker or feedback log is incomplete")
    return result


def _transport_peer(folder, checkpoint, task, condition, memory, report):
    """Validate an unregistered partial worker before recording its failed attempt."""
    result = read(folder / "summary.json")
    if folder.is_symlink() or not transport_failure(result) or (result.get("task_id"), result.get("condition")) != (task, condition):
        raise RuntimeError("Unregistered peer is not a matching transport failure")
    if read(folder / "prior-events.json") != checkpoint.events or read(folder / "memory-before.json") != memory_manifest(memory):
        raise RuntimeError("Unregistered transport peer has different inputs")
    current = deepcopy(checkpoint)
    initial = StationSession(current, task, feedback_mode=report["feedback_mode"]).initial
    if read(folder / "initial-public.json") != initial:
        raise RuntimeError("Unregistered transport peer has a different initial state")
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    for event in events[len(current.events):]:
        if event["task_run_id"] != current.task_run_id:
            raise RuntimeError("Unknown event in partial transport peer")
        if event["kind"] == "action":
            current.step(event["action"])
        elif event["kind"] == "runner_terminated":
            current.finish_incomplete(event["delivered"]["feedback"]["reason"])
        else:
            raise RuntimeError("Unknown event in partial transport peer")
        if current.events[-1] != event:
            raise RuntimeError("Partial transport feedback differs from replay")
    if current.events != events or trace_graph(current) != read(folder / "graph.json"):
        raise RuntimeError("Partial transport trace differs from replay")
    if (current.steps, current.distance) != (result.get("game_actions"), result.get("distance")):
        raise RuntimeError("Partial transport costs differ from replay")
    calls = result.get("llm_calls")
    if result.get("model_error_at_call") != calls or not isinstance(calls, int) or calls < 1:
        raise RuntimeError("Missing failed model-call identity")
    if len(list((folder / "model").glob("*-request.json"))) != calls or len(list((folder / "model").glob("*-response.json"))) != calls - 1:
        raise RuntimeError("Partial transport response boundary is inconsistent")
    initial = result.get("initial_session", {})
    if initial.get("initial_history_size") != 0 or initial.get("initial_backend_history_size") != 0 or initial.get("working") != {}:
        raise RuntimeError("Partial transport peer context was not isolated")
    if not initial.get("isolation") or not all(v for k, v in initial["isolation"].items() if k != "pid"):
        raise RuntimeError("Partial transport peer isolation is unverified")
    if not 0 <= result.get("main_calls", -1) <= report["max_turns"] or not 0 <= result.get("final_calls", -1) <= report["final_turns"] or result["main_calls"] + result["final_calls"] != calls:
        raise RuntimeError("Partial transport peer exceeded its budget")
    audit = [json.loads(line) for line in (folder / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    errors = [e for e in audit if e.get("kind") == "model_transport_error"]
    if not errors or errors[-1].get("call") != calls or not any(term in str(errors[-1].get("error", "")) for term in TRANSPORT_ERRORS):
        raise RuntimeError("Host audit does not confirm the transport failure")
    from scripts.check_ga_single_action import check_boundaries
    if result.get("action_policy") != report["action_policy"] or check_boundaries(folder)["rejected_extra_actions"] != result.get("action_policy_rejections"):
        raise RuntimeError("Partial transport action boundaries differ")
    if sha256((folder / "game-deliveries.jsonl").read_bytes()).hexdigest() != result.get("game_deliveries_sha256"):
        raise RuntimeError("Partial transport feedback delivery hash differs")
    return result


def resume_parallel(output, jail, model):
    output = Path(output).resolve()
    report = read(output / "pilot.json")
    if report["status"] == "completed":
        return report
    if report.get("action_policy") != "single" or report.get("movement_mode") != "step":
        raise ValueError("Parallel migration requires the existing single-step condition")
    for path, digest in report["implementation_sha256"].items():
        if sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Frozen pilot implementation changed")
    design = read(output / "design.json")
    if any(not row["infrastructure_ok"] and not transport_failure(row) for row in report["sessions"]):
        raise InfrastructureError("Unknown interruption; preserve evidence for review")
    agent = report["agent"]
    sessions = StationNativeSessions(output / "source" / ("GenericAgent" if agent == "ga" else "hermes-agent"),
        output / "support", jail, agent=agent, feedback_mode=report["feedback_mode"],
        game_access=report["game_access"], action_policy=report["action_policy"], movement_mode=report["movement_mode"],
        model_alias=report["model_alias"], seed=report["seed"], max_turns=report["max_turns"],
        final_turns=report["final_turns"], wall_seconds=report["wall_seconds"])
    if not (output / "probe/summary.json").is_file():
        raise RuntimeError("Existing native isolation probe is missing")
    baseline = output / "baseline"
    baseline_manifest = memory_manifest(baseline)
    report["scheduling_protocol"] = PROTOCOL
    report.setdefault("scheduling_events", []).append({"at_utc": datetime.now(timezone.utc).isoformat(),
        "scheduler_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "completed_sessions_at_start": [r["name"] for r in report["sessions"] if r["infrastructure_ok"]]})
    report["status"] = "running"
    save_json(output / "pilot.json", report)
    canonical, memory = [], baseline
    game = StationGame(report["world"], design)
    order = {name: i for i, (name, _) in enumerate(item for _, pair in schedule(report) for item in pair)}
    log_lock = threading.Lock()
    def event(kind, **fields):
        with log_lock, (output / "scheduling.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind, "utc": datetime.now(timezone.utc).isoformat(), **fields}) + "\n")
    def branch(checkpoint, task, memory, folder, condition):
        attempt = uuid4().hex
        event("branch_started", name=folder.name, attempt=attempt)
        try:
            return sessions.run(checkpoint, task, memory, folder, model, condition=condition)
        finally:
            event("branch_finished", name=folder.name, attempt=attempt)
    try:
        for task, pair in schedule(report):
            checkpoint = deepcopy(game)
            pending = []
            for name, condition in pair:
                row = next((r for r in report["sessions"] if r["name"] == name), None)
                if row and not row["infrastructure_ok"]:
                    _archive_failed(output, report, row)
                    row = None
                folder = output / "sessions" / name
                if row:
                    expected = baseline_manifest if condition == "clear" else memory_manifest(memory)
                    if read(folder / "memory-before.json") != expected or read(folder / "prior-events.json") != checkpoint.events:
                        raise RuntimeError("Recorded branch does not match its canonical checkpoint")
                    continue
                if folder.exists():
                    if (folder / "summary.json").is_file() and transport_failure(read(folder / "summary.json")):
                        result = _transport_peer(folder, checkpoint, task, condition,
                                                 baseline if condition == "clear" else memory, report)
                        row = {"name": name, **result}
                        report["sessions"].append(row)
                        report["sessions"].sort(key=lambda r: order[r["name"]])
                        save_json(output / "pilot.json", report)
                        _archive_failed(output, report, row)
                        event("unregistered_transport_peer_archived", name=name)
                        pending.append((name, condition, folder))
                        continue
                    result = _completed_peer(folder, checkpoint, task, condition,
                                             baseline if condition == "clear" else memory, report)
                    report["sessions"].append({"name": name, **result})
                    report["sessions"].sort(key=lambda r: order[r["name"]])
                    report.setdefault("adopted_completed_sessions", []).append({"name": name,
                        "at_utc": datetime.now(timezone.utc).isoformat(),
                        "summary_sha256": sha256((folder / "summary.json").read_bytes()).hexdigest()})
                    save_json(output / "pilot.json", report)
                    event("completed_peer_adopted", name=name)
                    continue
                pending.append((name, condition, folder))
            # Only the coordinator writes pilot.json. Branches have separate
            # games, writable memory, jailed workers, MCP services and logs.
            failures = []
            event("pair_ready", task=task, pending=[name for name, _, _ in pending],
                  prior_events_sha256=sha256(json.dumps(checkpoint.events, sort_keys=True).encode()).hexdigest())
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="station-branch") as pool:
                futures = {pool.submit(branch, deepcopy(checkpoint), task,
                    baseline if condition == "clear" else memory, folder, condition): (name, condition)
                    for name, condition, folder in pending}
                for future in as_completed(futures):
                    name, condition = futures[future]
                    try:
                        result = {"name": name, **future.result()}
                    except Exception as error:
                        failures.append(error)
                        continue
                    report["sessions"].append(result)
                    report["sessions"].sort(key=lambda r: order[r["name"]])
                    save_json(output / "pilot.json", report)
                    if not result["infrastructure_ok"]:
                        failures.append(InfrastructureError(result.get("infrastructure_error", "Native session failed")))
                    print(json.dumps({k: result.get(k) for k in ("name", "success", "distance", "llm_calls", "content_changed")}, ensure_ascii=False), flush=True)
            if failures:
                raise failures[0]  # The other active branch has already settled and been saved.
            keep_name = pair[0][0]
            canonical.append(output / "sessions" / keep_name)
            game = replay_checkpoint(design, report["world"], canonical)
            memory = canonical[-1] / "memory-after"
        report["status"] = "completed"
    except Exception:
        report["status"] = "interrupted"
        save_json(output / "pilot.json", report)
        raise
    save_json(output / "pilot.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-dependency", action="append", default=[])
    args = parser.parse_args()
    key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
    if not key:
        parser.error("Set MEMORYBENCH_GATEWAY_KEY in the parent host")
    report = read(args.output / "pilot.json")
    model = GatewayModel(args.base_url, key, report["model_alias"], None)
    resume_parallel(args.output, WSLJail(args.distro, args.runtime, args.runtime_dependency), model)


if __name__ == "__main__":
    main()
