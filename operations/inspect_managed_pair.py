"""Read one owned pair's current receipts; never print prompts or credentials."""

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from memorybenchmark.agent_sessions import (
    native_model_request_kind,
    observed_reasoning_effort,
)


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def latest_version(folder):
    for path in sorted(Path(folder).glob("*.json"), reverse=True):
        value = read(path)
        if value is not None:
            return value
    return None


def model_pairs(session):
    rows = []
    for path in sorted((Path(session) / "model").glob("*-request.json"))[-6:]:
        request = read(path)
        if request is None:
            continue
        response = read(
            path.with_name(path.name.replace("-request.json", "-response.json"))
        )
        completed = None
        for line in (response or {}).get("lines", []):
            if line.startswith("data:") and line[5:].strip() != "[DONE]":
                try:
                    event = json.loads(line[5:])
                except ValueError:
                    continue
                if event.get("type") == "response.completed":
                    completed = event.get("response")
        kind = native_model_request_kind(request, "hermes-session-1")
        requested = observed_reasoning_effort(request)
        acknowledged = observed_reasoning_effort(completed or {})
        rows.append(
            {
                "call": path.name.split("-")[0],
                "kind": kind,
                "requested_effort": requested,
                "response_received": completed is not None,
                "response_model": (completed or {}).get("model"),
                "provider_effort": acknowledged,
                "paired_primary_high": kind == "agent"
                and requested == acknowledged == "high"
                and completed is not None,
            }
        )
    return rows


def initial_configuration(session):
    path = Path(session) / "audit.jsonl"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream):
            if number > 50:
                break
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if value.get("kind") == "session":
                context = value.get("native_context_configuration") or {}
                return {
                    "session_id": value.get("session_id"),
                    "context_tokens": context.get("model_context_length"),
                    "registry_sha256": context.get("registry_sha256"),
                    "execution_protocol": value.get("execution_protocol"),
                }
    return None


def last_delivery(session):
    path = Path(session) / "game-deliveries.jsonl"
    if not path.exists():
        return None
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 1024**2))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            delivery = json.loads(line)
        except ValueError:
            continue
        response = delivery.get("response") or {}
        observation = response.get("observation") or {}
        if observation:
            feedback = response.get("feedback") or {}
            return {
                "task": (observation.get("task") or {}).get("id"),
                "location": observation.get("location"),
                "stage_index": observation.get("stage_index"),
                "game_actions": observation.get("steps"),
                "distance": observation.get("distance"),
                "material_state": observation.get("material_state"),
                "done": observation.get("done"),
                "success": observation.get("success"),
                "feedback_kind": feedback.get("kind"),
                "processing_result": feedback.get("result"),
            }
    return None


def process_identity(receipt):
    if os.name != "nt" or not receipt or not receipt.get("pid"):
        return None
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(receipt["pid"]))
    if not handle:
        return {"original_alive": False}
    try:
        stamps = [ctypes.c_ulonglong() for _ in range(4)]
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        ok = kernel.GetProcessTimes(
            ctypes.c_void_p(handle), *[ctypes.byref(s) for s in stamps]
        )
        same = bool(ok and stamps[0].value == receipt.get("created_filetime"))
        return {
            "pid": receipt["pid"],
            "same_creation": same,
            "original_alive": same and code.value == 259,
            "cpu_seconds": (
                round((stamps[2].value + stamps[3].value) / 10**7, 2) if same else None
            ),
        }
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def inspect(pair_root):
    pair_root = Path(pair_root).resolve()
    pair = read(pair_root / "pair.json")
    if not pair or len(pair.get("jobs", [])) != 2:
        raise ValueError("Select one complete prepared retain/clear pair")
    rows = []
    for job in pair["jobs"]:
        if job["model"] not in ("gpt-5.6-luna", "gpt-5.6-terra"):
            raise ValueError(
                "This Responses inspector must not interpret Gemini Chat streams"
            )
        root = Path(job["root"]).resolve()
        if root.parent != pair_root or root.name != job["condition"]:
            raise ValueError("Job root escaped its condition in the selected pair")
        runtime = root / "runtime-hermes"
        run = (
            runtime
            / ".runs"
            / f"pilot-hermes-{job['condition']}-{job['map']}-{job['pair_id'][:12]}"
        )
        pilot = read(run / "pilot.json")
        status = read(root / "status.json") or {}
        result = read(root / "result.json")
        row = {
            "condition": job["condition"],
            "experiment_id": pilot.get("experiment_id") if pilot else None,
            "job_id": job["id"],
            "phase": status.get("phase", pair["phase"]),
            "planned": job["tasks_per_condition"],
            "completed": len(pilot["sessions"]) if pilot else None,
            "successes": (
                sum(s.get("success") is True for s in pilot["sessions"])
                if pilot
                else None
            ),
            "scientific_failures": (
                sum(
                    s.get("success") is False and s.get("infrastructure_ok") is True
                    for s in pilot["sessions"]
                )
                if pilot
                else None
            ),
            "driver": process_identity(read(root / "driver-started.json")),
            "driver_exit": read(root / "driver-exit.json"),
            "paused": {
                k: v
                for k, v in (read(root / "paused.json") or {}).items()
                if k in ("type", "utc", "policy")
            },
            "transport": status.get("transport"),
            "sealed": bool(
                result and result.get("archive", {}).get("contents_verified")
            ),
        }
        row["preflight_passed"] = (read(root / "preflight.json") or {}).get("passed")
        if pilot is None:
            row["preparation"] = {
                "run_exists": run.exists(),
                "native_source_exists": (run / "source").exists(),
                "baseline_exists": (run / "baseline").exists(),
                "probe_exists": (run / "probe").exists(),
            }
        if (
            pilot
            and pilot["status"] != "completed"
            and len(pilot["sessions"]) < len(pilot["tasks"])
        ):
            index = len(pilot["sessions"])
            session = (
                run
                / "sessions"
                / f"{index+1:02d}-{pilot['tasks'][index]}-{job['condition']}"
            )
            row.update(
                current_task=pilot["tasks"][index],
                current=last_delivery(session),
                native_configuration=initial_configuration(session),
                latest_model_pairs=model_pairs(session),
            )
            leases = sorted(
                (root / "request-recovery-state/leases").glob("*"),
                key=lambda p: p.stat().st_mtime,
            )
            if leases:
                row["lease"] = latest_version(leases[-1])
                row["guard_exit"] = read(leases[-1] / "guard-exit.json")
        rows.append(row)
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "pair_id": pair["id"],
        "rows": rows,
        "free_disk_gib": round(shutil.disk_usage(pair_root.anchor).free / 2**30, 2),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = inspect(args.pair)
    body = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(body)
    print(body)


if __name__ == "__main__":
    main()
