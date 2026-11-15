"""Opaque clock lease and process guard. No evaluator or credentials are mounted.

Run outside the jail as a guard, or inside as the benchmark-worker bootstrap.
Upstream agent modules and their own clocks/configuration are not modified.
"""
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def read(path):
    deadline = time.monotonic()+5
    while True:
        try:
            target = Path(path)
            if target.name == "lease.json":
                versions = sorted(target.parent.glob("lease-*.json"))
                target = versions[-1] if versions else target
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(.03)


def guard(path, command):
    child = subprocess.Popen(command, start_new_session=True)
    reason = "worker_exited"
    while child.poll() is None:
        try:
            lease = read(path)
            age = time.time() - lease["heartbeat_epoch"]
            active = lease["active_elapsed"] + (max(0, age) if not lease["paused"] else 0)
            reason = ("host_lease_closed" if lease.get("closed") else
                      "host_lease_expired" if age > 90 else
                      "worker_active_timeout" if active > lease["active_budget"] + 10 else
                      "infrastructure_week_expired" if time.time() > lease["real_deadline_epoch"] else "")
        except (OSError, ValueError, KeyError):
            reason = "unreadable_host_lease"
        if reason:
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            break
        time.sleep(.25)
    code = child.wait()
    result = Path(path).with_name("guard-exit.json")
    temporary = result.with_suffix(".tmp")
    temporary.write_text(json.dumps({"exit_code": code, "reason": reason or "worker_exited",
                                     "child_pid": child.pid, "utc_epoch": time.time()}), encoding="utf-8")
    temporary.replace(result)
    return code if code >= 0 else 128-code


class LeaseClock:
    def __init__(self, path):
        self.path = path
        self.last = 0.0
        self.lock = threading.Lock()

    def monotonic(self):
        lease = read(self.path)
        value = lease["active_elapsed"] + (max(0, time.time()-lease["heartbeat_epoch"]) if not lease["paused"] else 0)
        with self.lock:
            self.last = max(self.last, value)
            return self.last

    def __getattr__(self, name):
        return getattr(time, name)


def native_transport_environment(filename, active_budget):
    """Use upstream Hermes timeout settings; the host enforces active budgets.

    Native TTFB/stale watchdogs must not expire while the host is retrying the
    same RPC. These are transport limits, not reasoning or model-call budgets.
    """
    if filename != "hermes_worker.py":
        return {}
    limit = str(7 * 24 * 3600 + active_budget + 120)
    return {name:limit for name in (
        "HERMES_API_TIMEOUT", "HERMES_API_CALL_STALE_TIMEOUT", "HERMES_STREAM_STALE_TIMEOUT",
        "HERMES_CODEX_HARD_TIMEOUT_SECONDS", "HERMES_CODEX_TTFB_TIMEOUT_SECONDS",
        "HERMES_CODEX_TTFB_MAX_SECONDS", "HERMES_CODEX_EVENT_STALE_TIMEOUT_SECONDS")}


class NativeConfigJSON:
    """Extend only the benchmark-created Hermes config, via native settings.

    The frozen benchmark worker writes this config twice (before/after MCP
    discovery). Native agent JSON, prompts and responses are not intercepted.
    """
    def __init__(self, active_budget):
        self.limit = 7*24*3600+active_budget+120

    def dumps(self, value, *args, **kwargs):
        if (isinstance(value,dict) and isinstance(value.get('model'),dict)
                and value['model'].get('base_url')=='https://model.invalid/v1'
                and value.get('terminal',{}).get('backend')=='local'):
            value=dict(value)
            providers=dict(value.get('providers',{}));custom=dict(providers.get('custom',{}))
            custom.update(request_timeout_seconds=self.limit,stale_timeout_seconds=self.limit)
            providers['custom']=custom;value['providers']=providers
            tasks={'compression','title_generation'}
            try:
                from hermes_cli.config import DEFAULT_CONFIG
                tasks.update(key for key,item in DEFAULT_CONFIG.get('auxiliary',{}).items()
                             if isinstance(item,dict) and {'model','provider','timeout','no_progress_timeout'} & item.keys())
            except ImportError:
                pass
            auxiliary=dict(value.get('auxiliary',{}))
            for name in tasks:
                auxiliary[name]={**auxiliary.get(name,{}),'timeout':self.limit,'no_progress_timeout':self.limit}
            value['auxiliary']=auxiliary
        return json.dumps(value,*args,**kwargs)

    def __getattr__(self,name):
        return getattr(json,name)


def bootstrap(filename):
    clock = LeaseClock("/runtime-control/lease.json")
    lease = read(clock.path)
    os.environ.update(native_transport_environment(filename, lease['active_budget']))
    common = importlib.import_module("ga_worker")
    common.time = clock
    original_drain = common.drain_background_reviews
    def drain(*args, **kwargs):
        kwargs["clock"] = clock.monotonic
        return original_drain(*args, **kwargs)
    common.drain_background_reviews = drain
    worker = importlib.import_module(Path(filename).stem)
    worker.time = clock
    if filename=='hermes_worker.py':
        worker.json=NativeConfigJSON(lease['active_budget'])
    worker.main()


if __name__ == "__main__":
    if sys.argv[1] == "guard":
        sys.exit(guard(sys.argv[2], sys.argv[3:]))
    try:
        bootstrap(sys.argv[2])
    except Exception as error:
        sys.__stdout__.write(json.dumps({"kind": "worker_error", "error_type": type(error).__name__,
                                        "message": str(error)[:300]}) + "\n")
        sys.__stdout__.flush()
        raise SystemExit(2)
