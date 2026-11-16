"""Fetch only new sealed archives described by a SHA-checked metadata export."""

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from memorybenchmark.experiments.verification import (
    verify_download,
    authorized_task_count,
)


def fetch(metadata, destination, source_digest):
    metadata, destination = Path(metadata).resolve(), Path(destination).resolve()
    exported = json.loads((metadata / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in exported["members"].items():
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
        ):
            raise ValueError("Metadata member escaped its export")
        body = (metadata / name).read_bytes()
        if (
            len(body) != expected["bytes"]
            or sha256(body).hexdigest() != expected["sha256"]
        ):
            raise ValueError("Metadata download integrity differs")
    results = []
    for row in exported["sealed"]:
        pair_id, condition = row["pair_id"], row["condition"]
        if (
            len(pair_id) != 32
            or any(c not in "0123456789abcdef" for c in pair_id)
            or condition not in ("retain", "clear")
        ):
            raise ValueError("Unexpected calibration identity")
        folder = destination / pair_id / condition
        folder.mkdir(parents=True, exist_ok=True)
        receipt = folder / "local-verification.json"
        if receipt.exists():
            results.append(
                verify_download(folder, expected_source_digest=source_digest)
            )
            continue
        for name in exported["members"]:
            relative = PurePosixPath(name)
            if len(relative.parts) != 2 or relative.parts[0] != condition:
                continue
            path = metadata / name
            target = folder / path.name
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise ValueError(
                    "Preserve existing metadata; downloaded source differs"
                )
            if not target.exists():
                shutil.copyfile(path, target)
        job = json.loads((folder / "job.json").read_text(encoding="utf-8-sig"))
        if job["source_digest"] != source_digest:
            raise ValueError("Sealed job differs from this independently frozen batch")
        remote = row["archive_path"].replace("\\", "/")
        tasks = authorized_task_count(job, source_digest)
        namespace = "hard-calibration-native/" if tasks == 12 else ""
        expected_root = f"C:/Codes/memorybenchmark-private/{namespace}experiments/{pair_id}/{condition}"
        if remote != expected_root + "/evidence.zip":
            raise ValueError("Download source escaped the authorized calibration")
        archive = folder / "evidence.zip.download"
        if not archive.exists():
            transfer = subprocess.run(
                ["scp", "Squishy:" + remote, str(archive)], capture_output=True
            )
            if transfer.returncode:
                raise RuntimeError(
                    "Archive transfer interrupted; preserve partial bytes and diagnose before retry"
                )
        results.append(verify_download(folder, expected_source_digest=source_digest))
    return [
        {
            k: value[k]
            for k in (
                "pair_id",
                "condition",
                "passed",
                "archive_bytes",
                "archive_sha256",
            )
        }
        for value in results
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--source-digest", required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(args.metadata, args.destination, args.source_digest)))


if __name__ == "__main__":
    main()
