"""Zero-model contracts for paired creation, validation and idempotency."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.experiments.config import RuntimeConfig
from memorybenchmark.experiments.service import ExperimentService

PROJECT = Path(__file__).resolve().parents[1]


class RecordingScheduler:
    def __init__(self):
        self.jobs = []

    def dispatch(self, job, config):
        self.jobs.append(job)


class ExperimentServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.scheduler = RecordingScheduler()
        self.config = RuntimeConfig(
            PROJECT,
            self.root,
            self.root / "native.tar.gz",
            "/runtime",
            (),
            Path("python"),
        )
        self.service = ExperimentService(self.config, self.scheduler)
        self.selection = {
            "model": "gpt-5.6-luna",
            "map": "capulin-easy",
            "movement_mode": "route",
            "request_id": "test-request-123",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_preview_has_pair_and_registered_context_without_dispatch(self):
        review = self.service.preview(self.selection)
        self.assertEqual(review["conditions"], ["retain", "clear"])
        self.assertEqual(review["context_tokens"], 272000)
        self.assertEqual(review["total_tasks"], 32)
        self.assertEqual(self.scheduler.jobs, [])

    def test_preparation_freezes_both_specs_without_dispatch(self):
        def fake_freeze(project, destination, design):
            destination.mkdir(parents=True)
            return "frozen-pair"

        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=fake_freeze
        ):
            prepared = self.service.prepare(self.selection)
            self.assertEqual(prepared["phase"], "prepared")
            self.assertEqual(self.scheduler.jobs, [])
            launched = self.service.create(self.selection)
            self.assertEqual(launched["phase"], "dispatched")
            self.assertEqual(len(self.scheduler.jobs), 2)

    def test_operator_catalog_is_injected_without_extending_the_public_default(self):
        candidate = "orcia-interface-calibration"
        service = ExperimentService(
            self.config,
            self.scheduler,
            maps={
                candidate: (
                    "候选",
                    "Hard calibration",
                    "calibration/orcia_interface12.json",
                )
            },
        )
        review = service.preview(
            {**self.selection, "map": candidate, "movement_mode": "step"}
        )
        self.assertEqual(review["tasks_per_condition"], 12)
        with self.assertRaises(ValueError):
            self.service.preview(
                {**self.selection, "map": candidate, "movement_mode": "step"}
            )

    def test_unknown_model_and_remote_path_injection_are_rejected(self):
        for invalid in (
            {"model": "unknown"},
            {"base_url": "http://evil.invalid"},
            {"map": "../../outside"},
        ):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    self.service.preview({**self.selection, **invalid})
        self.assertEqual(self.scheduler.jobs, [])

    def test_hard_is_single_step_and_has_new_allocation(self):
        with self.assertRaises(ValueError):
            self.service.preview({**self.selection, "map": "orcia-hard"})
        review = self.service.preview(
            {**self.selection, "map": "orcia-hard", "movement_mode": "step"}
        )
        self.assertEqual(review["tasks_per_condition"], 36)
        self.assertIn("composition36", review["design_id"])

    def test_pair_specs_are_both_committed_before_dispatch_and_retries_are_idempotent(
        self,
    ):
        def fake_freeze(project, destination, design):
            destination.mkdir(parents=True)
            return "same-frozen-source"

        def check_dispatch(job, config):
            pair = self.service.repository.read(job["pair_id"])
            self.assertEqual(len(pair["jobs"]), 2)
            for spec in pair["jobs"]:
                self.assertTrue((Path(spec["root"]) / "job.json").exists())
            self.scheduler.jobs.append(job)

        self.scheduler.dispatch = check_dispatch
        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=fake_freeze
        ):
            first = self.service.create(self.selection)
            second = self.service.create(self.selection)
        self.assertEqual(first, second)
        self.assertEqual(len(self.scheduler.jobs), 2)
        self.assertEqual(
            {job["condition"] for job in self.scheduler.jobs}, {"retain", "clear"}
        )
        self.assertEqual(
            {job["movement_mode"] for job in self.scheduler.jobs}, {"route"}
        )

    def test_pending_pairs_have_public_identity_matching_pilot_grouping(self):
        from hashlib import sha256

        pair_id = self.service.repository.pair_id(self.selection["request_id"])
        self.service.repository.pair_directory(pair_id).mkdir(parents=True)
        self.service.repository.save(
            pair_id,
            {
                "id": pair_id,
                "phase": "dispatched",
                "created_at": "2026-11-15T12:00:00Z",
                "selection": self.selection,
                "jobs": [
                    {
                        "id": condition,
                        "root": str(self.root / condition),
                        "condition": condition,
                    }
                    for condition in ("retain", "clear")
                ],
            },
        )
        (row,) = self.service.listing()
        self.assertEqual(
            row["comparison_key"], sha256(pair_id.encode()).hexdigest()[:16]
        )
        self.assertEqual(row["map_name"], "卡普林火山")
        self.assertEqual({j["condition"] for j in row["jobs"]}, {"retain", "clear"})
        self.assertTrue(all(j["phase"] == "queued" for j in row["jobs"]))
        self.assertNotIn(str(self.root), json.dumps(row))
        self.assertEqual(self.scheduler.jobs, [])

    def test_frozen_executor_imports_its_own_code_and_required_map_fixtures(self):
        import subprocess
        import sys
        from memorybenchmark.experiments.freezer import freeze

        destination = self.root / "frozen"
        freeze(PROJECT, destination, "orcia_hard36.json")
        code = "import sys;sys.path.insert(0,sys.argv[1]);import memorybenchmark.experiments.runner;from memorybenchmark.prototypes.station_independent import initialize;from scripts.report_station_experiment import report"
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", code, str(destination)],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_changed_frozen_code_is_rejected_before_any_worker_starts(self):
        from memorybenchmark.experiments.freezer import freeze, verify

        destination = self.root / "frozen"
        expected = freeze(PROJECT, destination, "orcia_hard36.json")
        self.assertGreater(verify(destination, expected), 1)
        source = destination / "memorybenchmark/experiments/runner.py"
        source.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(destination, expected)

    def test_source_package_preserves_import_fixtures_and_registry(self):
        import zipfile
        from memorybenchmark.experiments.freezer import freeze, package_source

        destination = self.root / "frozen"
        expected = freeze(PROJECT, destination, "orcia_hard36.json")
        output = self.root / "source.zip"
        package_source(destination, expected, output)
        package_source(destination, expected, output)
        with zipfile.ZipFile(output) as bundle:
            self.assertIn("memorybenchmark/data/history/valley.json", bundle.namelist())
            self.assertIn("config/model-gateways.json", bundle.namelist())

    def test_same_request_id_cannot_change_scientific_inputs(self):
        def fake_freeze(project, destination, design):
            destination.mkdir(parents=True)
            return "same"

        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=fake_freeze
        ):
            self.service.create(self.selection)
        with self.assertRaises(ValueError):
            self.service.create({**self.selection, "map": "nessie-normal"})

    def test_changed_source_never_dispatches_half_a_pair(self):
        def fake_freeze(project, destination, design):
            destination.mkdir(parents=True)
            return str(destination)

        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=fake_freeze
        ):
            with self.assertRaises(ValueError):
                self.service.create(self.selection)
        self.assertEqual(self.scheduler.jobs, [])


if __name__ == "__main__":
    unittest.main()
