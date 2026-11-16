"""Goal counts, conditional bindings and genuine earlier ordinary opportunities."""

from collections import defaultdict
import json
from pathlib import Path
import unittest

from memorybenchmark.prototypes.interface_curriculum import (
    binding_world,
    once_commissions,
    check_once_allocation,
    pilot_materials,
)
from memorybenchmark.prototypes.composition_lab import plans
from scripts.build_hard_calibration import build, validate


class BindingCurriculumTests(unittest.TestCase):
    def test_full_36_keeps_operation_work_but_doubles_goal_variety(self):
        world = binding_world()
        result = check_once_allocation(world, once_commissions(world))
        self.assertEqual(
            (result["tasks"], result["stages"], result["necessary_operations"]),
            (36, 72, 96),
        )
        self.assertEqual(result["fully_scoped_goal_classes"], 48)
        self.assertEqual(result["private_positive_bindings_in_full_world"], 96)
        self.assertTrue(result["all_alternative_bindings_are_not_claimed_learned"])

    def test_station_or_format_alone_is_not_a_sufficient_memory_key(self):
        world = binding_world()
        outputs = defaultdict(set)
        verification = defaultdict(set)
        for (material, station), value in world.cataloguers.items():
            outputs[station].add(value)
        for (material, station), value in world.verifiers.items():
            verification[(station, value[0])].add(value[1])
        self.assertTrue(all(len(v) == 2 for v in outputs.values()))
        self.assertTrue(any(len(v) > 1 for v in verification.values()))
        self.assertEqual(
            len({fmt for values in world.formats.values() for fmt in values}), 2
        )

    def test_actual_pilot_not_only_full_world_exercises_both_scope_collisions(self):
        world = binding_world()
        selected = pilot_materials(world)
        outputs, verification = defaultdict(set), defaultdict(set)
        for (material, station), value in world.cataloguers.items():
            if material in selected:
                outputs[station].add(value)
        for (material, station), value in world.verifiers.items():
            if material in selected:
                verification[station, value[0]].add(value[1])
        self.assertGreaterEqual(sum(len(v) > 1 for v in outputs.values()), 2)
        self.assertTrue(any(len(v) > 1 for v in verification.values()))
        design = build(variant="binding")
        self.assertEqual(
            {s["required_kind"] for t in design["tasks"].values() for s in t["stages"]},
            set(selected),
        )

    def test_pilot_and_full_game_have_prior_feedback_paths_within_original_budget(self):
        for full, count in ((False, 12), (True, 36)):
            with self.subTest(full=full):
                result = validate(build(variant="binding", full=full))
                self.assertEqual(result["successes"], count)
                self.assertTrue(
                    result[
                        "combined_reference_uses_only_delivered_prior_interface_facts"
                    ]
                )
                self.assertTrue(
                    result["actual_prior_feedback_for_every_combined_operation"]
                )
                self.assertLessEqual(result["maximum_reference_actions"], 352)

    def test_reordering_combination_before_ordinary_prefix_is_invalid(self):
        world = binding_world()
        tasks = once_commissions(world)
        with self.assertRaisesRegex(ValueError, "precedes"):
            check_once_allocation(world, tasks[24:] + tasks[:24])

    def test_round_one_frozen_design_remains_exactly_reproducible(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "memorybenchmark/data/calibration/orcia_interface12.json"
        )
        self.assertEqual(
            json.loads(json.dumps(build())),
            json.loads(source.read_text(encoding="utf-8")),
        )
