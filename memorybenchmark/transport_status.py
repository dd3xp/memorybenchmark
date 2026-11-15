"""Immutable observer status snapshots; readers never block writer replacement."""

from pathlib import Path
import json
import time
import threading
from uuid import uuid4

from .ga_runtime import filesystem_path

PROTOCOL = "immutable-transport-status-1"
_sequence_lock = threading.Lock()
_last_sequence = 0


def publish_status(path, event):
    path = filesystem_path(path)
    versions = path.with_name(path.stem + ".versions")
    versions.mkdir(parents=True, exist_ok=True)
    global _last_sequence
    with _sequence_lock:
        _last_sequence = max(time.time_ns(), _last_sequence + 1)
        target = versions / f"{_last_sequence:020d}-{uuid4().hex}.json"
    # Exclusive immutable creation needs no replace/delete access to any file
    # open by an observer. Readers skip an in-progress JSON snapshot.
    with target.open("x", encoding="utf-8") as stream:
        json.dump(event, stream, ensure_ascii=False)
    for old in sorted(versions.glob("*.json"))[:-16]:
        if old.is_symlink() or not old.resolve().is_relative_to(versions.resolve()):
            raise RuntimeError("Status snapshot escaped its owned directory")
        try:
            old.unlink()
        except (PermissionError, FileNotFoundError):
            pass


def read_status(path, ledger=None):
    path = Path(path)
    versions = path.with_name(path.stem + ".versions")
    candidates = sorted(versions.glob("*.json"))[-16:]
    for candidate in reversed(candidates):
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(
            versions.resolve()
        ):
            continue
        try:
            if candidate.stat().st_size > 256 * 1024:
                continue
            value = json.loads(candidate.read_text(encoding="utf-8-sig"))
            if isinstance(value, dict):
                return value
        except (OSError, ValueError):
            continue
    if ledger is not None and Path(ledger).is_file():
        with Path(ledger).open("rb") as stream:
            stream.seek(max(0, Path(ledger).stat().st_size - 256 * 1024))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except ValueError:
                continue
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return None
