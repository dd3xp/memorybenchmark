"""Frozen job entry point; requests wait in place, host reboots resume at a boundary."""

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time

from ..ga_runtime import filesystem_path
from ..watch import atomic_json
from .archive import seal
from .repository import exclusive, utc


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def process_creation():
    if os.name != "nt":
        return None
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    stamps = [ctypes.c_ulonglong() for _ in range(4)]
    kernel.GetProcessTimes(
        ctypes.c_void_p(kernel.GetCurrentProcess()), *[ctypes.byref(t) for t in stamps]
    )
    return stamps[0].value


def run_job(job_file):
    job_file = filesystem_path(job_file)
    job = read(job_file)
    root = job_file.parent
    if (
        job.get("schema") != "benchmark-job-1"
        or filesystem_path(job["root"]).resolve() != root.resolve()
    ):
        raise ValueError("Job specification does not own this directory")
    if (root / "result.json").exists() and read(root / "result.json").get(
        "archive", {}
    ).get("contents_verified"):
        from .archive import finish_retention

        with exclusive(root / "runner.owner.lock"):
            finish_retention(root)
            status = read(root / "status.json")
            status.update(phase="sealed", utc=utc(), exit_code=0)
            atomic_json(root / "status.json", status)
            atomic_json(
                root / "driver-exit.json",
                {"utc": utc(), "exit_code": 0, "retention_continuation": True},
            )
        return
    if (root / "paused.json").exists():
        return
    with exclusive(root / "runner.owner.lock"):
        from .freezer import verify

        verify(root / "runtime-hermes", job["source_digest"])
        _execute(root, job)


def _execute(root, job):
    from ..recovery_runtime import RecoveryJail, install
    from ..request_recovery import RecoveringGatewayModel
    from ..prototypes.station_independent import initialize, experiment, ownership
    from .boundary import install as install_boundary

    runtime = root / "runtime-hermes"
    run = (
        runtime
        / ".runs"
        / (
            "pilot-hermes-"
            + job["condition"]
            + "-"
            + job["map"]
            + "-"
            + job["pair_id"][:12]
        )
    )
    previous = read(root / "status.json") if (root / "status.json").exists() else None
    started_epoch = time.time()
    state = {
        "utc": utc(),
        "phase": "preparing",
        "pid": os.getpid(),
        "created_filetime": process_creation(),
        "started_epoch": started_epoch,
        "completed": 0,
        "planned": job["tasks_per_condition"],
        "run": str(run),
    }
    atomic_json(root / "driver-started.json", state)
    stop = threading.Event()

    def publish():
        current = dict(state, utc=utc())
        if (run / "pilot.json").exists():
            current["completed"] = len(read(run / "pilot.json")["sessions"])
        versions = sorted((root / "transport-status.versions").glob("*.json"))
        if versions:
            transport = read(versions[-1])
            current["transport"] = {
                k: transport.get(k)
                for k in ("kind", "utc", "reason", "attempt", "retry_at", "retry_after")
            }
            if state["phase"] == "running" and transport.get("kind") == "network_retry":
                current["phase"] = "waiting_for_gateway"
        atomic_json(root / "status.json", current)

    def heartbeat():
        while not stop.wait(15):
            try:
                publish()
            except (OSError, ValueError):
                pass

    publish()
    keeper = threading.Thread(target=heartbeat, daemon=True)
    keeper.start()
    try:
        if not (run / "pilot.json").exists():
            if run.exists():
                if (run / "sessions").exists() or not run.resolve().is_relative_to(
                    root.resolve()
                ):
                    raise ValueError(
                        "Unregistered preparation contains scientific sessions"
                    )
                from uuid import uuid4

                preserved = root / "failed-preparations" / uuid4().hex
                preserved.parent.mkdir(parents=True, exist_ok=True)
                run.rename(preserved)
                atomic_json(
                    preserved / "interruption.json",
                    {
                        "utc": utc(),
                        "model_calls": 0,
                        "reason": "pre_pilot_initialization_interruption",
                    },
                )
            with ownership(run):
                initialize(
                    run,
                    Path(job["native_archive"]),
                    agent="hermes",
                    condition=job["condition"],
                    design_path=runtime / "memorybenchmark/data" / job["design_file"],
                    model_alias=job["model"],
                    reasoning_effort="high",
                    movement_mode=job["movement_mode"],
                    transport_retries=0,
                    transport_failure_limit=0,
                    wall_seconds=604800,
                )
        else:
            from .recovery import recover_after_reboot

            recover_after_reboot(root, run, previous)
        install()
        install_boundary()
        registry = read(runtime / "config/model-gateways.json")
        gateway = registry["gateways"][registry["models"][job["model"]]["gateway"]]
        key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
        if not key:
            raise ValueError(
                "Configured gateway credential is unavailable to the scheduled user"
            )
        if gateway["api_mode"] == "chat_completions":
            from ..transports.gemini import GeminiGateway
            from ..experiments.chat_accounting import install as install_accounting

            install_accounting()
            model = GeminiGateway(
                gateway["base_url"],
                key,
                job["model"],
                None,
                status_path=root / "transport-status.json",
            )
        else:
            from ..transports.subscription import install as install_subscription

            install_subscription()
            model = RecoveringGatewayModel(
                gateway["base_url"],
                key,
                job["model"],
                None,
                connect_host=gateway.get("connect_host"),
                status_path=root / "transport-status.json",
            )
        state["phase"] = "running"
        publish()
        result = experiment(
            run,
            RecoveryJail(
                job["distro"],
                job["native_runtime"],
                job["runtime_dependencies"],
                recovery_root=root / "request-recovery-state",
            ),
            model,
            resume=True,
            reasoning_effort="high",
        )
        if result["status"] != "completed":
            raise RuntimeError("Native experiment did not finish")
        state["phase"] = "auditing_and_archiving"
        publish()
        seal(root, run, job)
        state.update(phase="sealed", completed=len(result["sessions"]), exit_code=0)
        atomic_json(root / "driver-exit.json", {"utc": utc(), "exit_code": 0})
    except BaseException as error:
        state.update(phase="needs_attention", error_type=type(error).__name__)
        atomic_json(
            root / "paused.json",
            {
                "utc": utc(),
                "type": type(error).__name__,
                "message": str(error),
                "policy": "No blind whole-task replay of unknown or deterministic errors",
            },
        )
        atomic_json(
            root / "driver-exit.json",
            {"utc": utc(), "exit_code": 1, "type": type(error).__name__},
        )
        raise
    finally:
        stop.set()
        keeper.join(timeout=20)
        publish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_job(args.job_file)
    except BlockingIOError:
        return


if __name__ == "__main__":
    main()
