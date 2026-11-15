"""Resume a completed managed run's failed source audit, never its game tasks.

This explicit operator entry handles only a proven CRLF/LF support mismatch.
The frozen executor and every original receipt remain byte-exact. The revised
auditor and its policy are packaged separately with the resulting evidence.
"""

import argparse
import ctypes
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time


def validate_completed(pilot, job, paused):
    sessions = pilot.get("sessions", [])
    if (
        pilot.get("status") != "completed"
        or len(sessions) != job["tasks_per_condition"]
        or len(pilot.get("tasks", [])) != len(sessions)
        or pilot.get("memory_condition") != job["condition"]
        or any(row.get("infrastructure_ok") is not True for row in sessions)
    ):
        raise ValueError("Only fully completed own-condition runs may resume archiving")
    message = paused.get("message", "")
    if (
        paused.get("type") != "AssertionError"
        or "executed support differs from frozen source" not in message
    ):
        raise ValueError("This repair does not handle other failures")


def creation_time(pid):
    if os.name != "nt":
        raise RuntimeError("Managed Windows process identity is required")
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        code = ctypes.c_ulong()
        stamps = [ctypes.c_ulonglong() for _ in range(4)]
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        ok = kernel.GetProcessTimes(
            ctypes.c_void_p(handle), *[ctypes.byref(stamp) for stamp in stamps]
        )
        return stamps[0].value if ok and code.value == 259 else None
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resume(job_path):
    job_path = Path(job_path).resolve()
    root = job_path.parent
    read = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
    job = read(job_path)
    if job.get("schema") != "benchmark-job-1" or Path(job["root"]).resolve() != root:
        raise ValueError("Job specification does not own this directory")
    runtime = root / "runtime-hermes"
    run = (
        runtime
        / ".runs"
        / f"pilot-hermes-{job['condition']}-{job['map']}-{job['pair_id'][:12]}"
    )
    sys.path.insert(0, str(runtime))
    from memorybenchmark.experiments.repository import exclusive, utc
    from memorybenchmark.experiments.freezer import verify
    from memorybenchmark.watch import atomic_json

    with exclusive(root / "runner.owner.lock"):
        if (root / "result.json").exists():
            raise ValueError("Existing sealed results must not be re-audited")
        paused = read(root / "paused.json")
        pilot = read(run / "pilot.json")
        validate_completed(pilot, job, paused)
        old_driver = read(root / "driver-started.json")
        if creation_time(old_driver["pid"]) == old_driver["created_filetime"]:
            raise ValueError("The original driver is still alive")
        verify(runtime, job["source_digest"])
        version = "completed-support-newlines-v1"
        recovery = root / "recovery" / version
        recovery.mkdir(parents=True, exist_ok=False)
        for name in (
            "paused.json",
            "driver-exit.json",
            "driver-started.json",
            "status.json",
        ):
            shutil.copy2(root / name, recovery / name)
        code_root = Path(__file__).resolve().parents[1]
        provenance = run / "provenance" / version
        provenance.mkdir(parents=True, exist_ok=False)
        files = (
            "operations/resume_completed_archive.py",
            "scripts/audit_station_native.py",
            "memorybenchmark/support_integrity.py",
        )
        hashes = {}
        for relative in files:
            original = code_root / relative
            target = provenance / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            hashes[relative] = sha256(target.read_bytes()).hexdigest()
        policy = {
            "utc": utc(),
            "policy": "crlf-equivalent-with-every-session-raw-hash",
            "model_calls": 0,
            "scientific_tasks_replayed": 0,
            "source_digest": job["source_digest"],
            "files": hashes,
            "original_failure_preserved": str(recovery / "paused.json"),
        }
        atomic_json(provenance / "repair.json", policy)
        load(
            "memorybenchmark.support_integrity",
            code_root / "memorybenchmark/support_integrity.py",
        )
        auditor = load(
            "scripts.audit_station_native",
            code_root / "scripts/audit_station_native.py",
        )
        auditor.audit = partial(auditor.audit, support_newlines="crlf-equivalent")
        # Report/archive/domain come from the original frozen executor. Only the
        # explicitly versioned support comparison is supplied by this repair.
        from memorybenchmark.experiments.archive import seal
        from memorybenchmark.agent_sessions import WorkerSessions

        def reject_worker(*args, **kwargs):
            raise RuntimeError("Archive-only continuation cannot start a model worker")

        WorkerSessions._worker = reject_worker
        state = read(root / "status.json")
        state.pop("error_type", None)
        state.update(
            phase="auditing_and_archiving",
            pid=os.getpid(),
            created_filetime=creation_time(os.getpid()),
            archive_continuation=version,
        )
        atomic_json(recovery / "started.json", {**state, **policy})
        stop = threading.Event()

        def publish():
            atomic_json(root / "status.json", {**state, "utc": utc()})

        def heartbeat():
            while not stop.wait(15):
                publish()

        publish()
        keeper = threading.Thread(target=heartbeat, daemon=True)
        keeper.start()
        try:
            seal(root, run, job)
            result = read(root / "result.json")
            if not result.get("archive", {}).get("contents_verified"):
                raise RuntimeError("Original archive verification did not finish")
            atomic_json(
                recovery / "completed.json",
                {
                    "utc": utc(),
                    "archive": result["archive"],
                    "model_calls": 0,
                    "scientific_tasks_replayed": 0,
                },
            )
            (root / "paused.json").unlink()
            atomic_json(
                root / "driver-exit.json",
                {"utc": utc(), "exit_code": 0, "archive_continuation": version},
            )
            state.update(phase="sealed", exit_code=0, completed=len(pilot["sessions"]))
        except BaseException as error:
            state.update(phase="needs_attention", error_type=type(error).__name__)
            atomic_json(
                recovery / "failed.json",
                {"utc": utc(), "type": type(error).__name__, "message": str(error)},
            )
            raise
        finally:
            stop.set()
            keeper.join(timeout=20)
            publish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-file", type=Path, required=True)
    resume(parser.parse_args().job_file)
