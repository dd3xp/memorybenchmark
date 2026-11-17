"""One final strict audit and one verified archive, followed by explicit retention."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time
from uuid import uuid4
import zipfile

from ..ga_runtime import filesystem_path
from ..watch import atomic_json
from .repository import utc


def file_digest(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def seal(root, run, job):
    from scripts.report_station_experiment import report

    root, run = filesystem_path(root), filesystem_path(run)
    result_path = root / "result.json"
    if result_path.exists() and json.loads(result_path.read_text(encoding="utf-8")).get(
        "archive", {}
    ).get("contents_verified"):
        finish_retention(root)
        return
    source = root / "runtime-hermes"
    pilot = json.loads((run / "pilot.json").read_text(encoding="utf-8"))
    from .freezer import package_source

    package_source(source, job["source_digest"], run / "provenance/executor-source.zip")
    for filename, expected in pilot["implementation_sha256"].items():
        original = filesystem_path(filename)
        if file_digest(original) != expected:
            raise ValueError("Frozen science changed before final audit")
        target = run / "provenance/frozen-source" / original.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(original, target)
    audit_path = root / "audit-result.json"
    if audit_path.exists():
        result = json.loads(audit_path.read_text(encoding="utf-8"))
    else:
        result = report(run, native_archive=Path(job["native_archive"]))
        atomic_json(audit_path, result)
    from .costs import transport_costs

    costs = transport_costs(run)
    atomic_json(root / "transport-costs.json", costs)
    files = []
    for directory, names, filenames in __import__("os").walk(run):
        if Path(directory) == run:
            names[:] = [name for name in names if name != "source"]
        files.extend(
            (
                "run/" + (Path(directory) / name).relative_to(run).as_posix(),
                Path(directory) / name,
            )
            for name in filenames
        )
    files += [
        ("provenance/" + name, root / name)
        for name in (
            "job.json",
            "audit-result.json",
            "driver-started.json",
            "transport-costs.json",
        )
    ]
    files += [("provenance/source-manifest.json", source / "source-manifest.json")]
    for name in (
        "development-metrics.json",
        "development-stop.json",
        "confirmation-authorization.json",
    ):
        if (root / name).is_file():
            files.append(("provenance/" + name, root / name))
    for path in (root / "development-observations").glob("*.json"):
        files.append(("development/" + path.name, path))
    files += [
        ("provenance/" + name, root / name)
        for name in ("entry.py", "launch.ps1", "task-definition.xml")
        if (root / name).exists()
    ]
    # Failed physical requests and operator/boot continuations remain in the run.
    for path in (root / "recovery").rglob("*.json"):
        files.append(
            ("recovery/" + path.relative_to(root / "recovery").as_posix(), path)
        )
    for path in (root / "request-recovery-state").rglob("*.json"):
        files.append(
            (
                "leases/"
                + path.relative_to(root / "request-recovery-state").as_posix(),
                path,
            )
        )
    if len({name for name, _ in files}) != len(files):
        raise ValueError("Archive member names are not unique")
    with ThreadPoolExecutor(max_workers=2) as workers:
        records = workers.map(
            lambda row: (
                row[0],
                {"bytes": row[1].stat().st_size, "sha256": file_digest(row[1])},
            ),
            files,
        )
        manifest = dict(records)
    archive = root / "evidence.zip"
    temporary = root / "evidence.zip.part"
    while shutil.disk_usage(root).free < job["minimum_free_gib"] * 2**30:
        atomic_json(
            root / "archive-wait.json", {"utc": utc(), "reason": "storage_reserve"}
        )
        time.sleep(60)
    if not archive.exists():
        if temporary.exists():
            temporary.rename(root / ("interrupted-" + uuid4().hex + ".zip.part"))
        with zipfile.ZipFile(
            temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as bundle:
            for name, path in files:
                bundle.write(path, name)
            bundle.writestr(
                "provenance/archive-content-manifest.json", json.dumps(manifest)
            )
    candidate = archive if archive.exists() else temporary
    with zipfile.ZipFile(candidate) as bundle:
        archived = json.loads(bundle.read("provenance/archive-content-manifest.json"))
        if set(bundle.namelist()) != set(archived) | {
            "provenance/archive-content-manifest.json"
        }:
            raise ValueError("Archive member inventory differs")
        for name, expected in archived.items():
            digest, size = sha256(), 0
            with bundle.open(name) as stream:
                for block in iter(lambda: stream.read(8 * 1024**2), b""):
                    digest.update(block)
                    size += len(block)
            if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                raise ValueError("Archive member integrity check failed: " + name)
    if candidate == temporary:
        temporary.rename(archive)
    from .costs import transport_costs

    atomic_json(
        result_path,
        {
            **result,
            "transport_costs": costs,
            "archive": {
                "name": archive.name,
                "bytes": archive.stat().st_size,
                "sha256": file_digest(archive),
                "contents_verified": True,
            },
        },
    )
    retire_unpacked_duplicates(root, run, manifest)


def finish_retention(root):
    """Resume only the verified duplicate-removal transaction after interruption."""
    root = filesystem_path(root)
    receipt = root / "retention.json"
    if (
        receipt.exists()
        and json.loads(receipt.read_text(encoding="utf-8")).get("phase") == "complete"
    ):
        return
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(root / "evidence.zip") as bundle:
        manifest = json.loads(bundle.read("provenance/archive-content-manifest.json"))
    retire_unpacked_duplicates(root, filesystem_path(status["run"]), manifest)


def retire_unpacked_duplicates(root, run, manifest):
    candidates = []
    for relative, expected in manifest.items():
        if not relative.startswith("run/sessions/"):
            continue
        parts = Path(relative).parts
        if len(parts) < 4:
            continue
        if parts[3] not in ("model", "model-streams", "audit.jsonl"):
            continue
        path = run / Path(*parts[1:])
        if (
            path.is_file()
            and path.stat().st_size == expected["bytes"]
            and file_digest(path) == expected["sha256"]
        ):
            candidates.append(relative)
    receipt = root / "retention.json"
    atomic_json(
        receipt,
        {
            "utc": utc(),
            "phase": "verified_before_removal",
            "archive": "evidence.zip",
            "members": candidates,
            "restore": "extract these members from the retained verified ZIP",
        },
    )
    for relative in candidates:
        path = run / Path(*Path(relative).parts[1:])
        if path.is_symlink() or not path.resolve().is_relative_to(run.resolve()):
            raise ValueError("Retention target escaped the run")
        path.unlink(missing_ok=True)
    atomic_json(
        receipt,
        {
            "utc": utc(),
            "phase": "complete",
            "archive": "evidence.zip",
            "removed_members": candidates,
        },
    )
