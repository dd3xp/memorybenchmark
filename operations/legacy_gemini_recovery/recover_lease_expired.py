"""Stage one diagnosed legacy Gemini lease expiry for the registered scheduler."""

import argparse
from copy import deepcopy
import ctypes
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from boundary_continuation import events_at, restore
from resume_legacy import now, read, write

PRIVATE = Path("C:/Codes/memorybenchmark-private")
MODEL = "gemini-3.1-flash-lite"
TARGETS = {
    ("dingo-normal", "retain"): 16,
    ("dingo-normal", "clear"): 16,
    ("boar-normal", "clear"): 8,
}
PAUSE = "bootstrap-history/reboot-recovery-v1/paused.json"


def creation_if_alive(pid):
    """An unqueryable process is different from a stopped process."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: no process with this PID.
            return None
        raise ctypes.WinError(error)
    try:
        code = ctypes.c_ulong()
        stamps = [ctypes.c_ulonglong() for _ in range(4)]
        for succeeded in (
            kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)),
            kernel.GetProcessTimes(
                ctypes.c_void_p(handle), *[ctypes.byref(stamp) for stamp in stamps]
            ),
        ):
            if not succeeded:
                raise OSError("Cannot prove the driver process identity")
        return stamps[0].value if code.value == 259 else None
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def owned_run(root, private):
    root, private = root.resolve(), private.resolve()
    for (map_id, condition), task_index in TARGETS.items():
        if root != private / f"easy20-gemini-{MODEL}-{map_id}-{condition}-20261111":
            continue
        plan = read(root / "run-plan.json")
        run = (
            root
            / "runtime-hermes"
            / ".runs"
            / f"pilot-hermes-{condition}-{map_id}-{MODEL}-20261111"
        )
        prepared = read(private / "gemini-easy-normal-hermes-20261111/prepared.json")
        matching = [s for s in prepared["runs"] if Path(s["root"]).resolve() == root]
        if len(matching) != 1 or (
            plan["run_directory_name"],
            plan["model_alias"],
            plan["map_id"],
            plan["condition"],
            plan["context_tokens_configured"],
            matching[0]["experiment_id"],
            Path(matching[0]["run"]).resolve(),
        ) != (run.name, MODEL, map_id, condition, 250000, plan["experiment_id"], run):
            raise ValueError("Prepared run identity differs")
        if run.resolve() != run:
            raise ValueError("Resolved run differs from the owned path")
        return root, run, plan, condition, task_index, matching[0]["task_name"]
    raise ValueError("Root is outside this lease-expiry recovery authorization")


def last_game_observation(body):
    """StationSession records its public responses before wrapping them in MCP."""
    latest = None
    for line in body.splitlines():
        response = json.loads(line)["response"]
        if "observation" not in response and isinstance(response.get("error"), str):
            continue
        observation = response["observation"]
        if observation["done"] is not False or observation["success"] is not False:
            raise ValueError("A delivered terminal game outcome cannot be repeated")
        latest = observation
    if latest is None:
        raise ValueError("The interrupted task has no delivered game observation")
    return latest


def failure_evidence(root, folder, summary_sha256, *, name, task, condition):
    summary_path = folder / "summary.json"
    body = summary_path.read_bytes()
    if sha256(body).hexdigest() != summary_sha256:
        raise ValueError("Failed summary differs from inspected evidence")
    summary = json.loads(body)
    if (
        (summary.get("task_id"), summary.get("condition")) != (task, condition)
        or summary["infrastructure_ok"] is not False
        or summary["done"] is not False
        or summary["success"] is not None
        or summary["infrastructure_error"] != "OSError"
        or summary["worker_returncode"] != 137
    ):
        raise ValueError("Summary is outside the diagnosed failure class")
    host = summary["host_io_error"]
    if (host["type"], host["errno"], host["winerror"]) != ("OSError", 22, None):
        raise ValueError("Host I/O error differs from the diagnosed failure")
    deliveries = (folder / "game-deliveries.jsonl").read_bytes()
    if sha256(deliveries).hexdigest() != summary["game_deliveries_sha256"]:
        raise ValueError("Failed task deliveries differ from their recorded SHA")
    observation = last_game_observation(deliveries)
    if (observation["steps"], observation["distance"]) != (
        summary["game_actions"],
        summary["distance"],
    ):
        raise ValueError("Last delivered game state does not match an interrupted task")
    lease_id = summary["request_recovery"]["lease_id"]
    if not re.fullmatch(r"[0-9a-f]{32}", lease_id):
        raise ValueError("Invalid owned lease identity")
    guard_path = root / "request-recovery-state/leases" / lease_id / "guard-exit.json"
    if guard_path.resolve() != guard_path:
        raise ValueError("Guard evidence escaped its owned location")
    guard = read(guard_path)
    if (guard["reason"], guard["exit_code"]) != ("host_lease_expired", -9):
        raise ValueError("Guard did not prove this lease expiry")
    return {
        "name": name,
        "task_id": task,
        "condition": condition,
        "infrastructure_ok": False,
        "infrastructure_error": "host_lease_expired",
        "success": None,
        "partial_game_done": False,
        "partial_game_success": None,
        "partial_game_actions": summary["game_actions"],
        "partial_distance": summary["distance"],
        "summary_sha256": summary_sha256,
        "lease_id": lease_id,
        "guard": guard,
        "host_io_error": host,
        "recovery_kind": "operator",
        "automatic_transport_task_retry_budget_unchanged": True,
        "failed_usage": "unknown unless reported in preserved raw evidence",
        "failed_live_memory_imported": False,
    }, guard_path


def validate_inputs(run, pilot, folder, task):
    from memorybenchmark.ga_runtime import memory_manifest
    from memorybenchmark.prototypes.station_capability import StationGame
    from memorybenchmark.prototypes.station_session import StationSession

    baseline = pilot["baseline_memory"]
    if memory_manifest(run / "baseline") != baseline:
        raise ValueError("Original baseline differs")
    previous = pilot["sessions"][-1]
    checkpoint = run / "sessions" / previous["name"]
    saved = read(checkpoint / "summary.json")
    if previous != {"name": checkpoint.name, **saved}:
        raise ValueError("Own preceding checkpoint receipt differs")
    if memory_manifest(checkpoint / "memory-after") != saved["output_memory"]:
        raise ValueError("Own preceding checkpoint bytes differ")
    design = read(run / "design.json")
    game = restore(
        design,
        pilot["world"],
        events_at(checkpoint / "events.jsonl"),
        saved,
        len(pilot["sessions"]),
    )
    expected_memory = (
        saved["output_memory"] if pilot["memory_condition"] == "retain" else baseline
    )
    if read(folder / "memory-before.json") != expected_memory:
        raise ValueError("Interrupted input memory differs from the own boundary")
    initial = StationSession(
        deepcopy(game), task, feedback_mode=pilot["feedback_mode"]
    ).initial
    if read(folder / "initial-public.json")["observation"] != initial["observation"]:
        raise ValueError(
            "Interrupted initial public state differs from the own boundary"
        )


def save_preimage(destination, source):
    expected = source.read_bytes()
    if destination.exists():
        if destination.read_bytes() != expected:
            raise ValueError("Recovery preimage differs")
        return
    destination.write_bytes(expected)


def stage(
    root,
    summary_sha256,
    driver_filetime,
    *,
    private=PRIVATE,
    process_identity=creation_if_alive,
):
    if not re.fullmatch(r"[0-9a-f]{64}", summary_sha256):
        raise ValueError("Expected a complete lowercase summary SHA-256")
    root, run, plan, condition, task_index, task_name = owned_run(root, private)
    sys.path.insert(0, str(root / "runtime-hermes"))
    try:
        from memorybenchmark.ga_runtime import filesystem_path
        from memorybenchmark.prototypes.station_independent import ownership
    finally:
        sys.path.pop(0)
    with ownership(run):
        return stage_locked(
            filesystem_path(root),
            filesystem_path(run),
            plan,
            condition,
            task_index,
            task_name,
            summary_sha256,
            driver_filetime,
            process_identity,
        )


def stage_locked(
    root,
    run,
    plan,
    condition,
    task_index,
    task_name,
    summary_sha256,
    driver_filetime,
    process_identity,
):
    started, exited = read(root / "driver-started.json"), read(
        root / "driver-exit.json"
    )
    if (
        started["created_filetime"] != driver_filetime
        or process_identity(started["pid"]) == driver_filetime
        or exited["exit_code"] != 1
    ):
        raise ValueError("Could not attest that the inspected driver has exited")
    if (root / "result.json").exists() or (root / "paused.json").exists():
        raise ValueError("An archive or additional operator pause already exists")

    pilot_path = run / "pilot.json"
    pilot = read(pilot_path)
    names = [
        f"{index:02d}-{task}-{condition}"
        for index, task in enumerate(pilot["tasks"], 1)
    ]
    task, name = pilot["tasks"][task_index - 1], names[task_index - 1]
    if (
        pilot["experiment_id"] != plan["experiment_id"]
        or pilot["memory_condition"] != condition
        or pilot["model_alias"] != MODEL
        or len(names) != 24
        or pilot["status"] != "interrupted"
        or task != f"T{task_index}"
        or [s["name"] for s in pilot["sessions"]] != names[: task_index - 1]
    ):
        raise ValueError("Run is no longer at the exact authorized boundary")

    transaction_name = f"{name}-{summary_sha256[:12]}"
    evidence = root / "bootstrap-history/lease-expired-operator-v1" / transaction_name
    destination = (
        run
        / "failed-attempts"
        / (name + "-lease-expired-operator-" + summary_sha256[:12])
    )
    source = run / "sessions" / name
    pause = root / PAUSE
    saved_pause = evidence / "paused-cleared.json"
    if evidence.resolve() != evidence or (destination.exists() and source.exists()):
        raise ValueError("Unsafe or conflicting recovery destination")
    pending = destination if destination.exists() else source
    if not pending.is_dir() or pending.is_symlink() or pending.resolve() != pending:
        raise ValueError("Interrupted session escaped its owned directory")
    if not pause.is_file() and not saved_pause.is_file():
        raise ValueError("The diagnosed pause receipt is missing")
    if pause.resolve() != pause or (pause.exists() and saved_pause.exists()):
        raise ValueError("Pause ownership changed")

    failure, guard_path = failure_evidence(
        root, pending, summary_sha256, name=name, task=task, condition=condition
    )
    validate_inputs(run, pilot, pending, task)
    receipt_path = evidence / "intent.json"
    if not receipt_path.exists():
        if pending != source or not pause.is_file():
            raise ValueError("Recovery changes lack their original transaction")
        pause_data = read(pause)
        if pause_data["type"] != "RuntimeError":
            raise ValueError("Unexpected pause classification")
        evidence.mkdir(parents=True, exist_ok=True)
        for label, path in (
            ("pilot.before.json", pilot_path),
            ("driver-started.before.json", root / "driver-started.json"),
            ("driver-exit.before.json", root / "driver-exit.json"),
            ("paused.before.json", pause),
            ("guard-exit.before.json", guard_path),
        ):
            save_preimage(evidence / label, path)
        write(
            receipt_path,
            {
                **failure,
                "utc": now(),
                "preserved_at": str(destination),
                "previous_driver": started,
                "scheduled_task": task_name,
                "source_zip_sha256": plan["source_zip_sha256"],
                "prepared_without_model_calls": True,
            },
        )

    receipt = read(receipt_path)
    if (
        any(receipt[k] != value for k, value in failure.items())
        or receipt["preserved_at"] != str(destination)
        or receipt["previous_driver"] != started
        or (pause if pause.exists() else saved_pause).read_bytes()
        != (evidence / "paused.before.json").read_bytes()
    ):
        raise ValueError("Receipt or original pause differs during continuation")
    before = read(evidence / "pilot.before.json")
    expected = deepcopy(before)
    expected.setdefault("attempt_history", []).append(receipt)
    expected["operator_whole_task_retries"] = (
        before.get("operator_whole_task_retries", 0) + 1
    )
    if pilot not in (before, expected):
        raise ValueError("Pilot changed after recovery was staged")
    if pending == source:
        destination.parent.mkdir(exist_ok=True)
        if destination.parent.resolve() != destination.parent:
            raise ValueError("Recovery destination parent escaped the run")
        source.rename(destination)
    if pilot == before:
        write(pilot_path, expected)
    if read(pilot_path) != expected:
        raise ValueError("Operator attempt was not committed")
    if pause.exists():
        pause.rename(saved_pause)
    return {
        "prepared": True,
        "task_name": task_name,
        "committed_sessions": task_index - 1,
        "next_task": task,
        "preserved_at": str(destination),
        "receipt": str(receipt_path),
        "model_calls": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--summary-sha256", required=True)
    parser.add_argument("--driver-filetime", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(stage(args.root, args.summary_sha256, args.driver_filetime)))


if __name__ == "__main__":
    main()
