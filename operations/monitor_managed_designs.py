"""Record a compact status snapshot for selected managed design versions."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re


def read_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path.name}")
    return value


def latest_status(root):
    for version in sorted((root / "status.versions").glob("*.json"), reverse=True):
        try:
            if value := read_object(version):
                return value
        except (OSError, ValueError):
            continue
    return read_object(root / "status.json") or {}


def observe_job(root, spec, observed):
    job = read_object(root / "job.json")
    if job is None or any(
        job.get(key) != spec.get(key) for key in ("id", "condition", "design_id")
    ):
        return {"condition": spec.get("condition"), "phase": "job_receipt_unavailable"}
    status = latest_status(root)
    phase = status.get("phase", "registered")
    timestamp = status.get("utc")
    archived = (read_object(root / "result.json") or {}).get("archive") or {}
    retention = read_object(root / "retention.json") or {}
    exited = read_object(root / "driver-exit.json") or {}
    transport = status.get("transport") or {}
    return {
        "condition": job["condition"],
        "model": job["model"],
        "phase": phase,
        "completed": status.get("completed"),
        "planned": job["tasks_per_condition"],
        "heartbeat_utc": timestamp,
        "heartbeat_stale": bool(
            timestamp
            and phase
            in {"running", "waiting_for_gateway", "preparing", "auditing_and_archiving"}
            and (observed - datetime.fromisoformat(timestamp)).total_seconds() > 300
        ),
        "gateway_retry_at": (
            transport.get("retry_at") if phase == "waiting_for_gateway" else None
        ),
        "archive_verified": archived.get("contents_verified") is True,
        "retention_complete": retention.get("phase") == "complete",
        "driver_exit_code": exited.get("exit_code"),
    }


def snapshot(experiments, designs):
    if not experiments.is_dir():
        raise FileNotFoundError("Managed experiment directory is unavailable")
    now = datetime.now(timezone.utc)
    matches = {design: [] for design in designs}
    unreadable = 0
    for path in sorted(experiments.glob("*/pair.json")):
        try:
            pair = read_object(path)
            if pair is None or pair.get("phase") == "superseded":
                continue
            design = pair["review"]["design_id"]
            if design not in matches:
                continue
            if pair["id"] != path.parent.name or not re.fullmatch(
                r"[0-9a-f]{32}", pair["id"]
            ):
                raise ValueError("Invalid experiment identity")
            jobs = [
                observe_job(path.parent / job["condition"], job, now)
                for job in pair["jobs"]
                if job["condition"] in {"retain", "clear"}
                and job["design_id"] == design
            ]
            matches[design].append(
                {"pair_id": pair["id"], "registration": pair["phase"], "jobs": jobs}
            )
        except (OSError, ValueError, KeyError, TypeError):
            unreadable += 1
    return {
        "observed_utc": now.isoformat(),
        "unreadable_manifests": unreadable,
        "designs": {
            name: {
                "phase": "registered" if rows else "awaiting_registration",
                "pairs": rows,
            }
            for name, rows in matches.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = read_object(args.config)
    report = snapshot(Path(config["experiments"]), config["designs"])
    latest = args.config.with_name("latest.json")
    pending = latest.with_suffix(".json.part")
    pending.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pending.replace(latest)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
