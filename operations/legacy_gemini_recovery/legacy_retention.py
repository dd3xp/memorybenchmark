"""Retire only byte-proven duplicates after the original Gemini driver has sealed."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import re
import zipfile
from datetime import datetime, timezone


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    h = sha256()
    with path.open("rb") as stream:
        for b in iter(lambda: stream.read(8 * 1024**2), b""):
            h.update(b)
    return h.hexdigest()


def complete(root, run):
    from resume_legacy import identity, write

    result = read(root / "result.json")
    archive = root / result["archive"]["name"]
    if (
        not result["archive"].get("contents_verified")
        or read(root / "driver-exit.json")["exit_code"] != 0
    ):
        raise ValueError("Original strict archive is not complete")
    started = read(root / "driver-started.json")
    if identity(started["pid"]) == started["created_filetime"]:
        return
    receipt = root / "retention-reboot-v2.json"
    if not receipt.exists():
        if (
            archive.stat().st_size != result["archive"]["bytes"]
            or digest(archive) != result["archive"]["sha256"]
        ):
            raise ValueError("Retained archive differs")
        with zipfile.ZipFile(archive) as bundle:
            manifest = json.loads(
                bundle.read("provenance/archive-content-manifest.json")
            )
        candidates = []
        for name, expected in manifest.items():
            parts = Path(name).parts
            if (
                len(parts) < 4
                or parts[:2] != ("run", "sessions")
                or parts[3] not in ("model", "model-streams", "audit.jsonl")
            ):
                continue
            path = run / Path(*parts[1:])
            if (
                path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(run.resolve())
                and path.stat().st_size == expected["bytes"]
                and digest(path) == expected["sha256"]
            ):
                candidates.append(name)
        write(
            receipt,
            {
                "utc": datetime.now(timezone.utc).isoformat(),
                "phase": "verified_before_removal",
                "members": candidates,
                "archive_sha256": result["archive"]["sha256"],
            },
        )
    state = read(receipt)
    if state["phase"] != "complete":
        for name in state["members"]:
            path = run / Path(*Path(name).parts[1:])
            if not path.resolve().is_relative_to(run.resolve()) or path.is_symlink():
                raise ValueError("Retention target escaped own run")
            path.unlink(missing_ok=True)
        write(
            receipt,
            {
                **state,
                "phase": "complete",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    prepared = read(
        Path(
            "C:/Codes/memorybenchmark-private/gemini-easy-normal-hermes-20261111/prepared.json"
        )
    )
    spec = next(
        s for s in prepared["runs"] if Path(s["root"]).resolve() == root.resolve()
    )
    task = spec["task_name"]
    if not re.fullmatch(r"MemorybenchmarkGeminiEasyNormalHermes_[A-Za-z0-9_.-]+", task):
        raise ValueError("Unexpected task ownership")
    command = (
        "$s=New-Object -ComObject Schedule.Service;$s.Connect();$s.GetFolder('\\').GetTask('"
        + task
        + "').Enabled=$false"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
