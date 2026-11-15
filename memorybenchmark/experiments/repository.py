"""Atomic pair records; immutable specs and mutable status have separate files."""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from ..watch import atomic_json


def utc():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def exclusive(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if __import__("os").name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class PairRepository:
    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def pair_id(request_id):
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,80}", request_id
        ):
            raise ValueError("Invalid experiment request ID")
        return sha256(request_id.encode()).hexdigest()[:32]

    def pair_directory(self, pair_id):
        if not re.fullmatch(r"[0-9a-f]{32}", pair_id):
            raise ValueError("Invalid pair ID")
        return self.root / pair_id

    def read(self, pair_id):
        path = self.pair_directory(pair_id) / "pair.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def save(self, pair_id, value):
        atomic_json(self.pair_directory(pair_id) / "pair.json", value)

    def listing(self):
        rows = []
        for path in sorted(self.root.glob("*/pair.json"), reverse=True):
            try:
                pair = json.loads(path.read_text(encoding="utf-8"))
                if pair.get("phase") == "superseded":
                    continue
                jobs = []
                for job in pair["jobs"]:
                    status = Path(job["root"]) / "status.json"
                    value = (
                        json.loads(status.read_text(encoding="utf-8"))
                        if status.exists()
                        else {"phase": "queued"}
                    )
                    jobs.append(
                        {"id": job["id"], "condition": job["condition"], **value}
                    )
                rows.append(
                    {
                        "id": pair["id"],
                        "created_at": pair["created_at"],
                        "model": pair["selection"]["model"],
                        "map": pair["selection"]["map"],
                        "movement_mode": pair["selection"]["movement_mode"],
                        "jobs": jobs,
                    }
                )
            except (OSError, ValueError, KeyError):
                continue
        return rows
