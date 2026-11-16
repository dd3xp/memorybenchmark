"""Export only newly sealed pair metadata; never collect or audit science twice."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def export(pair_root, output, *, condition=None):
    pair_root, output = Path(pair_root).resolve(), Path(output).resolve()
    pair = read(pair_root / "pair.json")
    if len(pair["jobs"]) != 2 or {j["condition"] for j in pair["jobs"]} != {
        "retain",
        "clear",
    }:
        raise ValueError("Select the authorized paired calibration")
    output.mkdir(parents=True, exist_ok=False)
    manifest, rows = {}, []
    for job in pair["jobs"]:
        if condition is not None and job["condition"] != condition:
            continue
        root = Path(job["root"]).resolve()
        if root.parent != pair_root or root.name != job["condition"]:
            raise ValueError("Job escaped its pair")
        if (
            not (root / "result.json").exists()
            or not (root / "driver-exit.json").exists()
        ):
            continue
        result, exited = read(root / "result.json"), read(root / "driver-exit.json")
        if exited.get("exit_code") != 0 or not result.get("archive", {}).get(
            "contents_verified"
        ):
            continue
        archive = result["archive"]
        if (
            archive["name"] != "evidence.zip"
            or (root / archive["name"]).stat().st_size != archive["bytes"]
        ):
            raise ValueError("Sealed archive publication differs")
        condition_output = output / job["condition"]
        condition_output.mkdir()
        for name in (
            "job.json",
            "result.json",
            "audit-result.json",
            "driver-exit.json",
            "driver-started.json",
            "transport-costs.json",
            "retention.json",
            "calibration-metrics.json",
            "preflight.json",
        ):
            path = root / name
            if not path.is_file():
                continue
            body = path.read_bytes()
            (condition_output / name).write_bytes(body)
            manifest[job["condition"] + "/" + name] = {
                "bytes": len(body),
                "sha256": sha256(body).hexdigest(),
            }
        rows.append(
            {
                "condition": job["condition"],
                "pair_id": pair["id"],
                "archive_path": str(root / "evidence.zip"),
                "archive": archive,
            }
        )
    (output / "manifest.json").write_text(
        json.dumps({"members": manifest, "sealed": rows}, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return {
        "exported_sealed_conditions": [r["condition"] for r in rows],
        "members": len(manifest),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--condition", choices=("retain", "clear"))
    args = parser.parse_args()
    print(json.dumps(export(args.pair, args.output, condition=args.condition)))


if __name__ == "__main__":
    main()
