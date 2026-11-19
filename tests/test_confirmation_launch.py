"""Explicit single-condition confirmation never silently creates a counterpart."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.experiments.config import RuntimeConfig
from memorybenchmark.experiments.service import ExperimentService
from operations.inspect_managed_pair import inspect
from memorybenchmark.experiments.verification import authorized_task_count
from memorybenchmark.experiments.repository import PairRepository
from scripts.run_hard_confirmation import LUNA6_POLICY, validate
from scripts.run_lunatic_recall_pilot import (
    EXPANDED_GOAL_SWITCH_POLICY,
    GOAL_SWITCH_POLICY,
    execute,
)


PROJECT = Path(__file__).resolve().parents[1]


class ConfirmationLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dispatched = []
        self.scheduler = type(
            "Scheduler",
            (),
            {"dispatch": lambda _, job, config: self.dispatched.append(job)},
        )()
        self.config = RuntimeConfig(
            PROJECT,
            self.root,
            self.root / "native.tar.gz",
            "/runtime",
            (),
            Path("python"),
        )
        self.policy = json.loads((PROJECT / LUNA6_POLICY).read_text(encoding="utf-8"))
        self.request = {
            k: self.policy[k] for k in ("model", "map", "movement_mode", "request_id")
        }
        self.maps = {"orcia-hard": ("Confirmation", "Hard", self.policy["design_file"])}
        self.service = ExperimentService(
            self.config, self.scheduler, maps=self.maps, conditions=("retain",)
        )

    @staticmethod
    def freeze(project, destination, design):
        destination.mkdir(parents=True)
        return "frozen-source"

    def test_prepare_and_dispatch_exactly_one_retained_job_idempotently(self):
        review = self.service.preview(self.request)
        validate(review, self.policy, PROJECT)
        self.assertEqual(review["total_tasks"], 36)
        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=self.freeze
        ):
            prepared = self.service.prepare(self.request)
            self.assertEqual(self.dispatched, [])
            first = self.service.create(self.request)
            self.assertEqual(first, self.service.create(self.request))
        self.assertEqual([j["condition"] for j in self.dispatched], ["retain"])
        pair = self.service.repository.pair_directory(prepared["id"])
        self.assertFalse((pair / "clear").exists())
        observed = inspect(pair)
        self.assertEqual([r["condition"] for r in observed["rows"]], ["retain"])

    def test_same_request_cannot_expand_single_condition_into_a_pair(self):
        with patch(
            "memorybenchmark.experiments.service.freeze", side_effect=self.freeze
        ):
            self.service.prepare(self.request)
        paired = ExperimentService(self.config, self.scheduler, maps=self.maps)
        with self.assertRaisesRegex(ValueError, "different experiment"):
            paired.create(self.request)
        self.assertEqual(self.dispatched, [])

    def test_default_browser_request_cannot_override_server_conditions(self):
        paired = ExperimentService(self.config, self.scheduler, maps=self.maps)
        self.assertEqual(
            paired.preview(self.request)["conditions"], ["retain", "clear"]
        )
        with self.assertRaises(ValueError):
            paired.preview({**self.request, "conditions": ["retain"]})

    def test_changed_context_or_extra_condition_is_rejected_before_preparation(self):
        review = self.service.preview(self.request)
        for changed in (
            {"context_tokens": 64000},
            {"conditions": ["retain", "clear"]},
            {"total_tasks": 72},
            {"model": "gpt-5.6-luna"},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate({**review, **changed}, self.policy, PROJECT)
        policy = deepcopy(self.policy)
        policy["launch_clear"] = True
        with self.assertRaises(ValueError):
            validate(review, policy, PROJECT)
        self.assertEqual(self.dispatched, [])

    def test_full_archive_verifier_requires_this_condition_and_an_independent_source(
        self,
    ):
        job = {
            **self.service.preview(self.request),
            "condition": "retain",
            "pair_id": PairRepository.pair_id(self.policy["request_id"]),
            "design_file": self.policy["design_file"],
        }
        self.assertEqual(authorized_task_count(job, "independent-frozen-source"), 36)
        for changed, source in (
            ({}, None),
            ({"condition": "clear"}, "source"),
            ({"design_id": "another-world"}, "source"),
            ({"model": "gpt-5.6-luna"}, "source"),
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                authorized_task_count({**job, **changed}, source)

    def test_lunatic_goal_switch_dispatches_and_verifies_only_the_retained_pilot(self):
        with (
            patch(
                "scripts.run_lunatic_recall_pilot.RuntimeConfig.load",
                return_value=self.config,
            ),
            patch(
                "scripts.run_lunatic_recall_pilot.WindowsScheduler",
                return_value=self.scheduler,
            ),
            patch("scripts.run_lunatic_recall_pilot.probe", return_value="baseline"),
            patch(
                "memorybenchmark.experiments.service.freeze", side_effect=self.freeze
            ),
        ):
            for policy in (GOAL_SWITCH_POLICY, EXPANDED_GOAL_SWITCH_POLICY):
                first = execute(None, policy)
                self.assertEqual(first, execute(None, policy))
        self.assertEqual(
            [job["condition"] for job in self.dispatched], ["retain", "retain"]
        )
        for job, count in zip(self.dispatched, (18, 24), strict=True):
            self.assertFalse((Path(job["root"]).parent / "clear").exists())
            self.assertEqual(authorized_task_count(job, "independent-source"), count)
            for changed in ({"condition": "clear"}, {"pair_id": "unregistered"}):
                with self.subTest(count=count, changed=changed), self.assertRaises(
                    ValueError
                ):
                    authorized_task_count({**job, **changed}, "independent-source")


if __name__ == "__main__":
    unittest.main()
