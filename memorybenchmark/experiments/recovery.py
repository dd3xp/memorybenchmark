"""Classify abandoned sessions before any autonomous boundary continuation."""

import ctypes
import json
import os
from pathlib import Path
import shutil
import time
from uuid import uuid4

from ..ga_runtime import memory_manifest
from ..watch import atomic_json
from .repository import utc


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def boot_epoch():
    if os.name != "nt":
        return time.time() - float(Path("/proc/uptime").read_text().split()[0])
    ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    return time.time() - ctypes.windll.kernel32.GetTickCount64() / 1000


def recover_after_reboot(root, run, previous_status):
    from .boundary import events_at, restore
    from ..prototypes.station_capability import StationGame
    from ..prototypes.station_session import StationSession

    pilot = read(run / "pilot.json")
    for receipt_path in (root / "recovery").glob("*.json"):
        receipt = read(receipt_path)
        source, destination = Path(receipt["source"]), Path(receipt["preserved_at"])
        if not source.resolve().is_relative_to(
            run.resolve()
        ) or not destination.resolve().is_relative_to(run.resolve()):
            raise ValueError("Recovery transfer escaped its run")
        if source.exists() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
        if destination.exists() and not any(
            r.get("preserved_at") == str(destination)
            for r in pilot.get("attempt_history", [])
        ):
            pilot.setdefault("attempt_history", []).append(receipt)
            pilot["automatic_reboot_boundary_retries"] = (
                pilot.get("automatic_reboot_boundary_retries", 0) + 1
            )
            atomic_json(run / "pilot.json", pilot)
    count = len(pilot["sessions"])
    if count == len(pilot["tasks"]):
        return
    condition = pilot["memory_condition"]
    name = f"{count+1:02d}-{pilot['tasks'][count]}-{condition}"
    folder = run / "sessions" / name
    if not folder.exists():
        return
    if (folder / "summary.json").exists():
        return
    if (
        not previous_status
        or previous_status.get("started_epoch", time.time()) >= boot_epoch()
    ):
        raise ValueError(
            "Abandoned session has no proven host reboot; automatic task replay refused"
        )
    baseline = run / "baseline"
    if memory_manifest(baseline) != pilot["baseline_memory"]:
        raise ValueError("Original baseline changed")
    design = read(run / "design.json")
    game = StationGame(pilot["world"], design)
    expected = pilot["baseline_memory"]
    if count:
        previous = pilot["sessions"][-1]
        checkpoint = run / "sessions" / previous["name"]
        summary = read(checkpoint / "summary.json")
        if previous != {"name": checkpoint.name, **summary}:
            raise ValueError("Committed checkpoint summary differs")
        if memory_manifest(checkpoint / "memory-after") != summary["output_memory"]:
            raise ValueError("Committed checkpoint memory differs")
        game = restore(
            design,
            pilot["world"],
            events_at(checkpoint / "events.jsonl"),
            summary,
            count,
        )
        if condition == "retain":
            expected = summary["output_memory"]
    if read(folder / "memory-before.json") != expected:
        raise ValueError("Uncommitted task did not start from its own boundary")
    initial = StationSession(
        game, pilot["tasks"][count], feedback_mode=pilot["feedback_mode"]
    ).initial
    if read(folder / "initial-public.json")["observation"] != initial["observation"]:
        raise ValueError("Initial public state differs from the committed boundary")
    last = None
    with (folder / "game-deliveries.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            try:
                last = json.loads(line)
            except ValueError:
                continue
    observation = (last or {}).get("response", {}).get("observation", {})
    if observation.get("done") and not observation.get("success"):
        raise ValueError(
            "A real terminal game failure cannot be replayed by infrastructure recovery"
        )
    destination = run / "failed-attempts" / (name + "-host-reboot-" + uuid4().hex[:8])
    if not destination.resolve().is_relative_to(run.resolve()):
        raise ValueError("Recovery destination escaped its run")
    receipt = {
        "utc": utc(),
        "name": name,
        "condition": condition,
        "reason": "proven_host_reboot",
        "partial_game": {
            key: observation.get(key)
            for key in ("done", "success", "steps", "distance")
        },
        "source": str(folder),
        "preserved_at": str(destination),
        "partial_live_memory_imported": False,
        "unknown_usage_preserved": True,
    }
    atomic_json(root / "recovery" / (destination.name + ".json"), receipt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(folder), str(destination))
    atomic_json(destination / "reboot-recovery.json", receipt)
    pilot.setdefault("attempt_history", []).append(receipt)
    pilot["automatic_reboot_boundary_retries"] = (
        pilot.get("automatic_reboot_boundary_retries", 0) + 1
    )
    atomic_json(run / "pilot.json", pilot)
