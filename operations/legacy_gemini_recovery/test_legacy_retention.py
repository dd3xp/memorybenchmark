import json
from pathlib import Path
from hashlib import sha256
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import legacy_retention


class RetentionTests(unittest.TestCase):
    def test_only_verified_canonical_duplicates_are_removed_and_future_entries_disable(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "runtime-hermes/.runs/pilot-test"
            path = run / "sessions/01-T1-retain/model/001-request.json"
            unique = path.with_name("002-request.json")
            path.parent.mkdir(parents=True)
            path.write_bytes(b"fixture")
            unique.write_bytes(b"user revised evidence")
            manifest = {
                f"run/{path.relative_to(run).as_posix()}": {
                    "bytes": 7,
                    "sha256": sha256(b"fixture").hexdigest(),
                },
                f"run/{unique.relative_to(run).as_posix()}": {
                    "bytes": 7,
                    "sha256": sha256(b"fixture").hexdigest(),
                },
            }
            with zipfile.ZipFile(root / "evidence.zip", "w") as bundle:
                bundle.writestr(
                    "provenance/archive-content-manifest.json", json.dumps(manifest)
                )
                bundle.write(path, next(iter(manifest)))
            digest = legacy_retention.digest(root / "evidence.zip")
            for name, value in {
                "result.json": {
                    "archive": {
                        "name": "evidence.zip",
                        "bytes": (root / "evidence.zip").stat().st_size,
                        "sha256": digest,
                        "contents_verified": True,
                    }
                },
                "driver-exit.json": {"exit_code": 0},
                "driver-started.json": {"pid": 1, "created_filetime": 1},
            }.items():
                (root / name).write_text(json.dumps(value), encoding="utf-8")
            original = legacy_retention.read

            def read(path):
                if Path(path).name == "prepared.json":
                    return {
                        "runs": [
                            {
                                "root": str(root),
                                "task_name": "MemorybenchmarkGeminiEasyNormalHermes_fixture",
                            }
                        ]
                    }
                return original(path)

            with (
                patch("resume_legacy.identity", return_value=None),
                patch.object(legacy_retention, "read", side_effect=read),
                patch("legacy_retention.subprocess.run") as dispatch,
            ):
                legacy_retention.complete(root, run)
                legacy_retention.complete(root, run)
            self.assertFalse(path.exists())
            self.assertEqual(unique.read_bytes(), b"user revised evidence")
            self.assertEqual(legacy_retention.digest(root / "evidence.zip"), digest)
            self.assertEqual(dispatch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
