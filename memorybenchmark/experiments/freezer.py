"""Freeze executable science once; never package development history or caches."""

from hashlib import sha256
import json
from pathlib import Path
import shutil

from ..watch import atomic_json


def freeze(project, destination, design_name):
    project, destination = Path(project), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    sources = list((project / "memorybenchmark").rglob("*.py"))
    sources += list((project / "scripts").rglob("*.py"))
    sources += list((project / "scripts").glob("*.ps1"))
    sources += list((project / "memorybenchmark/data").rglob("*.json"))
    sources += list((project / "config").rglob("*.json"))
    # Legacy fixture readers remain executable; their tiny configs are code fixtures,
    # rather than raw experimental histories or generated outputs.
    sources += list((project / "design").glob("*.json"))
    manifest = {}
    for source in sorted(sources):
        relative = source.relative_to(project)
        if "__pycache__" in relative.parts:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        body = target.read_bytes()
        manifest[relative.as_posix()] = {
            "bytes": len(body),
            "sha256": sha256(body).hexdigest(),
        }
    if f"memorybenchmark/data/{design_name}" not in manifest:
        raise ValueError("Selected map was not frozen")
    atomic_json(destination / "source-manifest.json", manifest)
    return sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def verify(destination, expected_digest):
    """Validate the executable package, never replay or hash old task histories."""
    destination = Path(destination)
    manifest = json.loads(
        (destination / "source-manifest.json").read_text(encoding="utf-8")
    )
    if (
        sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
        != expected_digest
    ):
        raise ValueError("Frozen source manifest differs from the job specification")
    for name, expected in manifest.items():
        path = destination / name
        if path.is_symlink() or not path.resolve().is_relative_to(
            destination.resolve()
        ):
            raise ValueError("Frozen source member escaped its package")
        body = path.read_bytes()
        if (
            len(body) != expected["bytes"]
            or sha256(body).hexdigest() != expected["sha256"]
        ):
            raise ValueError("Frozen source file differs: " + name)
    return len(manifest)


def package_source(destination, expected_digest, output):
    """Keep every executable fixture/config with the scientific evidence."""
    import zipfile

    destination, output = Path(destination), Path(output)
    verify(destination, expected_digest)
    manifest = json.loads(
        (destination / "source-manifest.json").read_text(encoding="utf-8")
    )
    if output.exists():
        with zipfile.ZipFile(output) as bundle:
            recorded = json.loads(bundle.read("source-manifest.json"))
            if recorded != manifest:
                raise ValueError(
                    "Existing executable package belongs to another source"
                )
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    if temporary.exists():
        temporary.unlink()  # generated source-only package; raw evidence is elsewhere
    with zipfile.ZipFile(temporary, "x", zipfile.ZIP_DEFLATED) as bundle:
        for name, expected in manifest.items():
            body = (destination / name).read_bytes()
            if sha256(body).hexdigest() != expected["sha256"]:
                raise ValueError("Source changed while packaging")
            bundle.writestr(name, body)
        bundle.writestr("source-manifest.json", json.dumps(manifest))
    temporary.rename(output)
