"""Versioned host-reboot recovery outside each frozen Gemini executor."""

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    os.replace(temporary, path)


def identity(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        code = ctypes.c_ulong()
        stamps = [ctypes.c_ulonglong() for _ in range(4)]
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        if code.value != 259 or not kernel.GetProcessTimes(
            ctypes.c_void_p(handle), *[ctypes.byref(t) for t in stamps]
        ):
            return None
        return stamps[0].value
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def last_json(path):
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 65536))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            pass
    return {}


def recover_partial(root, run, pilot, recovery):
    index = len(pilot["sessions"])
    if index == len(pilot["tasks"]):
        return
    name = f"{index+1:02d}-{pilot['tasks'][index]}-{pilot['memory_condition']}"
    folder = run / "sessions" / name
    if not folder.exists():
        return
    if (folder / "summary.json").exists():
        return  # The boundary executor adopts only a fully validated saved result.
    started = read(root / "driver-started.json")
    if identity(started["pid"]) == started["created_filetime"]:
        raise ValueError("The original driver is still alive")
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    boot_epoch = time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000
    leases = sorted(
        (root / "request-recovery-state/leases").glob("*"),
        key=lambda p: p.stat().st_mtime_ns,
    )
    latest = sorted(leases[-1].glob("lease-*.json"))[-1] if leases else None
    lease = read(latest) if latest else {}
    if not lease or lease["heartbeat_epoch"] >= boot_epoch:
        raise ValueError(
            "No proven server reboot after the abandoned worker; pause for diagnosis"
        )
    observation = (
        last_json(folder / "game-deliveries.jsonl")
        .get("response", {})
        .get("observation", {})
    )
    if observation.get("done") and not observation.get("success"):
        raise ValueError(
            "A genuine terminal game failure must be committed, never replayed"
        )
    from copy import deepcopy
    from memorybenchmark.ga_runtime import memory_manifest
    from memorybenchmark.prototypes.station_capability import StationGame
    from memorybenchmark.prototypes.station_session import StationSession
    from boundary_continuation import restore, events_at

    baseline = run / "baseline"
    if memory_manifest(baseline) != pilot["baseline_memory"]:
        raise ValueError("Original baseline differs from its receipt")
    design = read(run / "design.json")
    expected_memory = pilot["baseline_memory"]
    game = StationGame(pilot["world"], design)
    if index:
        previous = pilot["sessions"][-1]
        checkpoint = run / "sessions" / previous["name"]
        saved = read(checkpoint / "summary.json")
        if previous != {"name": checkpoint.name, **saved}:
            raise ValueError("Own preceding checkpoint receipt differs")
        if memory_manifest(checkpoint / "memory-after") != saved["output_memory"]:
            raise ValueError("Own preceding checkpoint bytes differ")
        game = restore(
            design, pilot["world"], events_at(checkpoint / "events.jsonl"), saved, index
        )
        if pilot["memory_condition"] == "retain":
            expected_memory = saved["output_memory"]
    if read(folder / "memory-before.json") != expected_memory:
        raise ValueError("Interrupted input memory differs from the own boundary")
    initial = StationSession(
        deepcopy(game), pilot["tasks"][index], feedback_mode=pilot["feedback_mode"]
    ).initial
    if read(folder / "initial-public.json")["observation"] != initial["observation"]:
        raise ValueError(
            "Interrupted initial public state differs from the own boundary"
        )
    attempt = sum(a.get("name") == name for a in pilot.get("attempt_history", [])) + 1
    destination = run / "failed-attempts" / f"{name}-host-reboot-{attempt}"
    if not folder.resolve().is_relative_to(run.resolve()) or destination.exists():
        raise ValueError("Unsafe or repeated recovery destination")
    record = {
        "utc": now(),
        "name": name,
        "task_id": pilot["tasks"][index],
        "condition": pilot["memory_condition"],
        "infrastructure_ok": False,
        "infrastructure_error": "host_reboot_during_same_request_wait",
        "success": None,
        "partial_game_done": observation.get("done"),
        "partial_game_success": (
            observation.get("success") if observation.get("done") else None
        ),
        "partial_game_actions": observation.get("steps"),
        "partial_distance": observation.get("distance"),
        "preserved_at": str(destination),
        "boot_epoch": boot_epoch,
        "old_heartbeat_epoch": lease["heartbeat_epoch"],
        "previous_driver": started,
        "recovery_kind": (
            "operator"
            if not pilot.get("reboot_boundary_recoveries")
            else "automatic_proven_host_reboot"
        ),
        "automatic_transport_task_retry_budget_unchanged": True,
        "failed_usage": "unknown unless reported in preserved raw evidence",
        "failed_live_memory_imported": False,
    }
    write(recovery / ("before-" + name + ".json"), record)
    destination.parent.mkdir(exist_ok=True)
    shutil.move(str(folder), str(destination))
    write(destination / "reboot-recovery.json", record)
    pilot.setdefault("attempt_history", []).append(record)
    pilot["reboot_boundary_recoveries"] = pilot.get("reboot_boundary_recoveries", 0) + 1
    counter = (
        "operator_whole_task_retries"
        if record["recovery_kind"] == "operator"
        else "automatic_reboot_boundary_retries"
    )
    pilot[counter] = pilot.get(counter, 0) + 1
    write(run / "pilot.json", pilot)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    private = Path("C:/Codes/memorybenchmark-private").resolve()
    if not root.is_relative_to(private) or not root.name.startswith(
        "easy20-gemini-gemini-"
    ):
        raise ValueError(
            "This continuation is restricted to the authorized Gemini cohort"
        )
    plan = read(root / "run-plan.json")
    run = root / "runtime-hermes/.runs" / plan["run_directory_name"]
    if (
        (root / "result.json").exists()
        and (root / "driver-exit.json").exists()
        and read(root / "driver-exit.json")["exit_code"] == 0
    ):
        from legacy_retention import complete

        complete(root, run)
        return
    recovery = root / "bootstrap-history/reboot-recovery-v1"
    recovery.mkdir(parents=True, exist_ok=True)
    if (recovery / "paused.json").exists():
        return
    sys.path.insert(0, str(root / "runtime-hermes"))
    from memorybenchmark.prototypes.station_independent import ownership

    with ownership(run):
        started = (
            read(root / "driver-started.json")
            if (root / "driver-started.json").exists()
            else None
        )
        if started and identity(started["pid"]) == started["created_filetime"]:
            return
        pilot = read(run / "pilot.json")
        recover_partial(root, run, pilot, recovery)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for name in ("driver-started.json", "driver-exit.json"):
            p = root / name
            if p.exists():
                shutil.copy2(p, recovery / (stamp + "-" + name))
        write(
            recovery / "dispatch.json",
            {
                "utc": now(),
                "completed_prefix": len(pilot["sessions"]),
                "condition": pilot["memory_condition"],
                "source_zip_sha256": plan["source_zip_sha256"],
                "frozen_science_changed": False,
                "new_probe_calls": 0,
            },
        )
    if args.prepare_only:
        return
    import boundary_continuation

    boundary_continuation.install()
    try:
        runpy.run_path(str(root / "driver.py"), run_name="__main__")
    except BaseException as error:
        write(
            recovery / "paused.json",
            {
                "utc": now(),
                "type": type(error).__name__,
                "reason": "Unknown or deterministic driver error requires diagnosis; no whole-task retry",
            },
        )
        raise


if __name__ == "__main__":
    main()
