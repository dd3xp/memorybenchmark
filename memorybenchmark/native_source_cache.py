"""Verified immutable native source shared physically; task memory stays copied."""

from contextlib import contextmanager
import errno
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
from uuid import uuid4

from .ga_runtime import extract_native, filesystem_path


def digest(path):
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024**2), b""):
            h.update(block)
    return h.hexdigest()


@contextmanager
def cache_lock(path):
    policy_path = Path(__file__).resolve().parents[1] / "config/evidence-storage.json"
    policy = (
        json.loads(policy_path.read_text(encoding="utf-8"))
        if policy_path.exists()
        else {}
    )
    waiting = policy.get("native_source_cache_lock_wait_seconds", 604800)
    if not 1 <= waiting <= 604800:
        raise ValueError("Native cache waiting must fit the infrastructure week")
    with path.open("a+b") as f:
        f.seek(0, os.SEEK_END)
        if not f.tell():
            f.write(b"\0")
            f.flush()
        end = time.monotonic() + waiting
        while True:
            f.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= end:
                    raise RuntimeError(
                        "Native source cache is still owned by another preparation"
                    )
                time.sleep(0.1)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def extract_cached_native(archive, destination, *, native="ga"):
    if native not in ("ga", "hermes"):
        raise ValueError("Unknown native source type")
    archive = Path(archive).resolve()
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Native source destination must be new")
    identity = digest(archive)
    parent = archive.parent / "native-source-cache-v1"
    parent.mkdir(exist_ok=True)
    if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
        raise ValueError("Native cache cannot be a reparse directory")
    cache = parent / f"{native}-{identity}"
    with cache_lock(parent / (cache.name + ".lock")):
        if not cache.exists():
            temp = parent / (".build-" + uuid4().hex)
            try:
                temp.mkdir()
                source = extract_native(archive, temp / "source", native=native)
                files = {}
                directories = []
                for path in filesystem_path(source).rglob("*"):
                    rel = path.relative_to(filesystem_path(source)).as_posix()
                    if path.is_dir():
                        directories.append(rel)
                    elif path.is_file():
                        files[rel] = {
                            "size": path.stat().st_size,
                            "sha256": digest(path),
                        }
                    else:
                        raise ValueError("Native cache contains a special file")
                receipt = {
                    "version": 1,
                    "native": native,
                    "archive_sha256": identity,
                    "files": files,
                    "directories": directories,
                }
                body = json.dumps(
                    receipt, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                (temp / "manifest.json").write_bytes(body)
                (temp / "ready.json").write_text(
                    json.dumps(
                        {
                            "manifest_sha256": sha256(body).hexdigest(),
                            "archive_sha256": identity,
                        }
                    ),
                    encoding="utf-8",
                )
                if digest(archive) != identity:
                    raise ValueError("Native archive changed while creating its cache")
                os.replace(temp, cache)
            finally:
                if temp.exists():
                    assert temp.resolve().is_relative_to(parent.resolve())
                    shutil.rmtree(filesystem_path(temp))
    body = (cache / "manifest.json").read_bytes()
    ready = json.loads((cache / "ready.json").read_text(encoding="utf-8"))
    if (
        ready.get("manifest_sha256") != sha256(body).hexdigest()
        or ready.get("archive_sha256") != identity
    ):
        raise ValueError("Native cache manifest changed")
    receipt = json.loads(body)
    if receipt["archive_sha256"] != identity or receipt["native"] != native:
        raise ValueError("Native cache identity differs")
    name = "hermes-agent" if native == "hermes" else "GenericAgent"
    cached = filesystem_path(cache / "source" / name)
    # All consumers mount source read-only. Mutable baselines/working memory
    # continue to use copy_memory(), never these hard links.
    for relative in [*receipt["directories"], *receipt["files"]]:
        parts = PurePosixPath(relative)
        if (
            parts.is_absolute()
            or ".." in parts.parts
            or "\\" in relative
            or ":" in relative
        ):
            raise ValueError("Native cache path escaped its source")
    for relative, expected in receipt["files"].items():
        p = cached / relative
        if (
            p.is_symlink()
            or not p.resolve().is_relative_to(cached.resolve())
            or p.stat().st_size != expected["size"]
            or digest(p) != expected["sha256"]
        ):
            raise ValueError("Native cache contents changed; refusing preparation")
    destination.mkdir(parents=True)
    source = destination / name
    source.mkdir()
    for relative in receipt["directories"]:
        (filesystem_path(source) / relative).mkdir(parents=True, exist_ok=True)
    linked = copied = 0
    for relative in receipt["files"]:
        target = filesystem_path(source) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(cached / relative, target)
            linked += 1
        except OSError as error:
            if (
                error.errno != errno.EXDEV
                and getattr(error, "winerror", None) != 17
            ):
                raise
            shutil.copy2(cached / relative, target)
            copied += 1
    (destination.parent / "native-source-cache-receipt.json").write_text(
        json.dumps(
            {
                "version": 1,
                "native": native,
                "archive_sha256": identity,
                "cache": str(cache),
                "verified_files": len(receipt["files"]),
                "immutable_files_hardlinked": linked,
                "cross_volume_files_copied": copied,
                "mutable_memory_shared": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return source
