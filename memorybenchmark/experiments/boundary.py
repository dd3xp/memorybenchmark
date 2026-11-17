"""Resume an independent run at its own committed task boundary.

Installed outside frozen science. Existing history is read once from the last
checkpoint; new tasks still use the original strict validator and final audit.
"""

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def events_at(path):
    try:
        from memorybenchmark.event_store import read_events
    except ImportError:
        return [
            json.loads(line)
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return read_events(path)


def restore(design, world, events, summary, count):
    from memorybenchmark.prototypes.station_capability import StationGame, State

    if not summary["infrastructure_ok"] or not summary["done"]:
        raise ValueError("The last task is not a committed checkpoint")
    last = events[-1]
    obs = last["delivered"]["observation"]
    expected = (True, summary["success"], summary["game_actions"], summary["distance"])
    if (obs["done"], obs["success"], obs["steps"], obs["distance"]) != expected:
        raise ValueError("Checkpoint outcome and summary differ")
    if last["task_id"] != summary["task_id"]:
        raise ValueError("Checkpoint belongs to another task")
    game = StationGame(world, design)
    game.events, game._runs = events, count
    game.task_id, game.task_run_id = last["task_id"], last["task_run_id"]
    game.state = State(
        position=obs["location"],
        raw=obs["raw"],
        processed=obs["processed"],
        done=obs["done"],
        success=obs["success"],
        stage=obs["stage_index"],
        **(
            {"material_state": obs["material_state"]} if "material_state" in obs else {}
        ),
    )
    game.steps, game.distance, game.clock = obs["steps"], obs["distance"], obs["time"]
    return game


def execute(output, jail, model, *, checkpoint_observer=None):
    """The original experiment() caller already holds this run's ownership lock."""
    from memorybenchmark.ga_runtime import filesystem_path, memory_manifest
    from memorybenchmark.prototypes.station_capability import StationGame
    from memorybenchmark.prototypes.station_independent import now, save_json
    from memorybenchmark.prototypes.station_pilot import StationNativeSessions
    from memorybenchmark.prototypes.station_parallel import _completed_peer

    output = filesystem_path(output)
    report = read(output / "pilot.json")
    if report["protocol"] != "station-independent-experiment-1":
        raise ValueError("Only independently owned runs may resume")
    if report["status"] == "completed":
        return report
    condition = report["memory_condition"]
    names = [f"{i+1:02d}-{task}-{condition}" for i, task in enumerate(report["tasks"])]
    if [r["name"] for r in report["sessions"]] != names[: len(report["sessions"])]:
        raise ValueError("Completed tasks must be an unchanged canonical prefix")
    for path, expected in report["implementation_sha256"].items():
        if sha256(filesystem_path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen implementation changed")
    baseline = output / "baseline"
    if memory_manifest(baseline) != report["baseline_memory"]:
        raise ValueError("Original baseline changed")
    design = read(output / "design.json")
    count = len(report["sessions"])
    memory = baseline
    if count:
        folder = output / "sessions" / names[count - 1]
        summary = read(folder / "summary.json")
        if report["sessions"][-1] != {"name": folder.name, **summary}:
            raise ValueError("Last summary differs from the committed manifest")
        if memory_manifest(folder / "memory-after") != summary["output_memory"]:
            raise ValueError("Own last checkpoint memory changed")
        game = restore(
            design, report["world"], events_at(folder / "events.jsonl"), summary, count
        )
        if condition == "retain":
            memory = folder / "memory-after"
    else:
        game = StationGame(report["world"], design)
    native = StationNativeSessions(
        output / "source/hermes-agent",
        output / "support",
        jail,
        agent="hermes",
        feedback_mode=report["feedback_mode"],
        game_access="native",
        action_policy=report["action_policy"],
        movement_mode=report.get("movement_mode", "step"),
        model_alias=report["model_alias"],
        reasoning_effort=report["reasoning_effort"],
        seed=report["seed"],
        max_turns=report["max_turns"],
        final_turns=report["final_turns"],
        wall_seconds=report["wall_seconds"],
    )
    if not (output / "probe/summary.json").is_file():
        if count == 0 and report["status"] == "ready":
            native.probe(baseline, output / "probe")
        else:
            raise ValueError("Existing zero-model preparation receipt is missing")
    probe = read(output / "probe/summary.json")
    if (
        not probe.get("infrastructure_ok")
        or probe.get("model_requests") != 0
        or probe.get("llm_calls") != 0
    ):
        raise ValueError("Existing zero-model preparation did not pass")
    report["status"] = "running"
    report.setdefault("starts", []).append(
        {
            "at_utc": now(),
            "pid": os.getpid(),
            "resume_policy": "own_committed_boundary; unchanged_prefix; original_final_strict_audit",
        }
    )
    save_json(output / "pilot.json", report)
    try:
        if count and checkpoint_observer is not None:
            checkpoint_observer(report, game)
        for index in range(count, len(report["tasks"])):
            task, name = report["tasks"][index], names[index]
            folder = output / "sessions" / name
            task_memory = memory if condition == "retain" else baseline
            if folder.exists():
                result = _completed_peer(
                    folder, game, task, condition, task_memory, report
                )
            else:
                result = native.run(
                    deepcopy(game),
                    task,
                    task_memory,
                    folder,
                    model,
                    condition=condition,
                )
            from memorybenchmark.model_context import context_configuration

            if result["initial_session"][
                "native_context_configuration"
            ] != context_configuration(report["model_alias"]):
                raise ValueError(
                    "Actual native context differs from frozen configuration"
                )
            if not result["infrastructure_ok"]:
                raise RuntimeError(
                    "Native infrastructure failed; preserve task for classification"
                )
            verified = _completed_peer(
                folder, game, task, condition, task_memory, report
            )
            report["sessions"].append({"name": name, **verified})
            save_json(output / "pilot.json", report)
            game = restore(
                design,
                report["world"],
                events_at(folder / "events.jsonl"),
                verified,
                index + 1,
            )
            if condition == "retain":
                memory = folder / "memory-after"
            if checkpoint_observer is not None:
                checkpoint_observer(report, game)
            print(
                json.dumps(
                    {
                        "task": task,
                        "completed": index + 1,
                        "success": verified["success"],
                    }
                ),
                flush=True,
            )
        report.update(status="completed", completed_at_utc=now())
        report.pop("last_error", None)
    except BaseException as error:
        report.update(
            status="interrupted",
            last_error={
                "type": type(error).__name__,
                "message": str(error),
                "at_utc": now(),
            },
        )
        save_json(output / "pilot.json", report)
        raise
    save_json(output / "pilot.json", report)
    return report


def install(checkpoint_observer=None):
    from functools import partial
    import memorybenchmark.prototypes.station_independent as module

    module.execute = partial(execute, checkpoint_observer=checkpoint_observer)
