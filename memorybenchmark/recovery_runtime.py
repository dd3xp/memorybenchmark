"""Opt-in infrastructure overlay for an already frozen experiment.

The original evaluator/native/support files retain their hashes. Only the
benchmark's transport wait clock and external process lifetime are replaced.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import shutil
import threading
import time
from uuid import uuid4

from .ga_runtime import WSLJail
from .request_recovery import ActiveClock, RecoveringGatewayModel, WEEK, durable_json
from .recovery_lease import native_transport_environment

_WORKER_CLOCK = ContextVar("request_recovery_worker_clock", default=None)


class _TimeFacade:
    def monotonic(self):
        clock = _WORKER_CLOCK.get()
        return clock.monotonic() if clock is not None else time.monotonic()

    def __getattr__(self, name):
        return getattr(time, name)


class RecoveryJail(WSLJail):
    def __init__(self, *args, recovery_root, **kwargs):
        super().__init__(*args, **kwargs)
        self.recovery_root = Path(recovery_root)
        self.clock = ActiveClock()
        self.lease = None

    @contextmanager
    def session(self, output, model):
        self.clock.reset()
        self.control = self.recovery_root / "leases" / uuid4().hex
        self.control.mkdir(parents=True)
        self.lease = self.control / "lease.json"
        self.real_started = time.time()
        self.budget = 604800
        self.closed = False
        stop = threading.Event()
        sequence = 0
        def publish():
            nonlocal sequence
            sequence += 1
            # A new filename avoids replacing a file open through DrvFS.
            target = self.control / f"lease-{sequence:09d}.json"
            durable_json(target, {"heartbeat_epoch": time.time(), "active_elapsed": self.clock.elapsed(),
                "paused": self.clock.paused_at is not None, "active_budget": self.budget,
                "real_deadline_epoch": self.real_started + WEEK + self.budget, "closed": self.closed})
            for old in sorted(self.control.glob("lease-*.json"))[:-16]:
                if old.is_symlink() or not old.resolve().is_relative_to(self.control.resolve()):
                    raise RuntimeError("Clock lease escaped its owned directory")
                try:
                    old.unlink()
                except (PermissionError, FileNotFoundError):
                    pass
        def heartbeat():
            while not stop.wait(1):
                try:
                    publish()
                except OSError as error:
                    # A transient sharing violation must not kill the keeper.
                    # Persistent disk failure still expires the external lease.
                    with (self.control / "publication-errors.jsonl").open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({"utc_epoch":time.time(), "type":type(error).__name__,
                                                "errno":error.errno, "winerror":getattr(error,"winerror",None)})+"\n")
        publish()
        keeper = threading.Thread(target=heartbeat, daemon=True)
        keeper.start()
        if isinstance(model, RecoveringGatewayModel):
            model.clock, model.output = self.clock, Path(output)
            model.alive = lambda: not (self.control / "guard-exit.json").exists()
        try:
            yield
        finally:
            stop.set()
            keeper.join(timeout=6)
            if keeper.is_alive():
                raise RuntimeError("Clock publisher did not stop before final lease")
            self.closed = True
            publish()
            if isinstance(model, RecoveringGatewayModel):
                model.output = None

    def command(self, source, memory, support, wall_seconds, *, worker_filename="ga_worker.py"):
        if self.lease is None:
            raise RuntimeError("Recovery jail requires an owned worker session")
        self.budget = wall_seconds
        command = super().command(source, memory, support, wall_seconds, worker_filename=worker_filename)
        marker = command.index("bwrap")
        inner = command[marker:]
        at = inner.index("--clearenv")
        support_code = self.control / "code"
        support_code.mkdir()
        script = support_code / "recovery_lease.py"
        shutil.copyfile(Path(__file__).with_name(script.name), script)
        inner[at:at] = ["--ro-bind", self.path(support_code), "/runtime-support",
                        "--ro-bind", self.path(self.control), "/runtime-control"]
        inner[-1:] = ["/runtime-support/recovery_lease.py", "bootstrap", worker_filename]
        return command[:command.index("--exec")+1] + ["python3", self.path(script), "guard", self.path(self.lease), *inner]


def install():
    """Scope clock substitution to the benchmark host module, not native time."""
    from . import agent_sessions
    if getattr(agent_sessions.WorkerSessions._worker, "request_recovery", False):
        return
    original = agent_sessions.WorkerSessions._worker
    agent_sessions.time = _TimeFacade()
    def worker(self, memory, output, config, adapter=None, model=None, *args, **kwargs):
        if not isinstance(self.jail, RecoveryJail):
            return original(self, memory, output, config, adapter, model, *args, **kwargs)
        with self.jail.session(output, model):
            token = _WORKER_CLOCK.set(self.jail.clock)
            try:
                report = original(self, memory, output, config, adapter, model, *args, **kwargs)
                report["request_recovery"] = {"protocol": "same-request-recovery-1",
                    "active_seconds": round(self.jail.clock.elapsed(), 3),
                    "infrastructure_wait_seconds": round(max(0, self.jail.clock.infrastructure_seconds()), 3),
                    "native_transport_environment":native_transport_environment(self.worker_filename,self.wall_seconds),
                    "retry_window_seconds": WEEK, "lease_id": self.jail.control.name}
                return report
            finally:
                _WORKER_CLOCK.reset(token)
    worker.request_recovery = True
    agent_sessions.WorkerSessions._worker = worker
