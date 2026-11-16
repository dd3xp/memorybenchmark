"""Metadata batches contain only the new, sealed condition selected by the operator."""

import json
from pathlib import Path
import tempfile
import unittest

from operations.export_calibration_receipts import export


class CalibrationExportTests(unittest.TestCase):
    def make_pair(self, directory):
        pair = Path(directory) / "pair"
        jobs = []
        for condition in ("retain", "clear"):
            root = pair / condition
            root.mkdir(parents=True)
            jobs.append({"root": str(root), "condition": condition})
            (root / "result.json").write_text(
                json.dumps(
                    {
                        "archive": {
                            "name": "evidence.zip",
                            "bytes": 3,
                            "sha256": "declared-server-seal",
                            "contents_verified": True,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (root / "driver-exit.json").write_text('{"exit_code":0}', encoding="utf-8")
            (root / "evidence.zip").write_bytes(b"zip")
        (pair / "pair.json").write_text(
            json.dumps({"id": "pair", "jobs": jobs}), encoding="utf-8"
        )
        return pair

    def test_unfiltered_export_preserves_both_conditions(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.make_pair(directory)
            result = export(pair, Path(directory) / "both")
            self.assertEqual(result["exported_sealed_conditions"], ["retain", "clear"])

    def test_missing_counterpart_needs_an_explicit_single_condition_review(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.make_pair(directory)
            path = pair / "pair.json"
            record = json.loads(path.read_text(encoding="utf-8"))
            record["jobs"] = record["jobs"][:1]
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError):
                export(pair, Path(directory) / "unlabelled")
            record["review"] = {"conditions": ["retain"]}
            path.write_text(json.dumps(record), encoding="utf-8")
            result = export(pair, Path(directory) / "explicit")
            self.assertEqual(result["exported_sealed_conditions"], ["retain"])

    def test_selected_clear_does_not_export_already_retained_condition(self):
        with tempfile.TemporaryDirectory() as directory:
            pair = self.make_pair(directory)
            output = Path(directory) / "export"
            result = export(pair, output, condition="clear")
            self.assertEqual(result["exported_sealed_conditions"], ["clear"])
            self.assertFalse((output / "retain").exists())
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                all(name.startswith("clear/") for name in manifest["members"])
            )
            self.assertFalse((output / "clear/evidence.zip").exists())
            with self.assertRaises(FileExistsError):
                export(pair, output, condition="clear")


if __name__ == "__main__":
    unittest.main()
