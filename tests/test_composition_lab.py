"""Behavioral checks for the isolated candidate, including failed shortcuts."""

import json
from dataclasses import asdict, replace
import unittest

from memorybenchmark.prototypes.composition_lab import (
    DeliveredMemory,
    assess,
    assess_allocation,
    build_world,
    commissions,
    execute,
    plans,
    score,
    interface_ablation,
    Stage,
)


class CompositionLabTests(unittest.TestCase):
    def test_every_combination_has_prior_scoped_experiences_and_four_uses(self):
        world = build_world()
        tasks = commissions(world)
        result = assess_allocation(world, tasks)
        self.assertEqual(
            (result["tasks"], result["stages"], result["necessary_operations"]),
            (36, 72, 96),
        )
        self.assertEqual(result["fully_scoped_experiences"], 24)
        with self.assertRaisesRegex(ValueError, "precedes"):
            assess_allocation(world, tasks[12:] + tasks[:12])

    def test_locally_capable_operations_can_form_an_invalid_combination(self):
        result = assess()
        self.assertEqual(
            result["all_locally_capable_cartesian_choices"],
            {"goal_compatible": 24, "enumerated_choices": 96},
        )
        self.assertEqual(
            result["goal_aware_but_interface_blind_choices"],
            {"goal_compatible": 24, "enumerated_choices": 48},
        )
        witness = result["wrong_interface_witnesses"][0]
        self.assertEqual(witness["actual_feedback"][0]["result"], "processed")
        self.assertEqual(witness["actual_feedback"][1]["result"], "unsupported")
        self.assertNotIn("capability", witness["actual_feedback"][1])

    def test_feedback_never_supplies_the_unused_catalogue_or_verifier(self):
        world = build_world()
        item = commissions(world)[0][0]
        ok, outcomes = execute(world, item, plans(world, item)[0])
        self.assertTrue(ok)
        payload = json.dumps([asdict(o) for o in outcomes])
        self.assertNotIn("verifiers", payload)
        self.assertNotIn("cataloguers", payload)
        self.assertEqual(
            set(asdict(outcomes[0])),
            {
                "station",
                "material",
                "operation",
                "input_format",
                "output_format",
                "result",
            },
        )

    def test_compatible_memory_is_built_only_from_completed_ordinary_commissions(self):
        world = build_world()
        tasks = commissions(world)
        memory = DeliveredMemory()
        combined = tasks[12][0]
        self.assertIsNone(memory.compatible_plan(combined))
        for pair in tasks[:12]:
            for item in pair:
                ok, outcomes = execute(world, item, plans(world, item)[0])
                self.assertTrue(ok)
                memory.observe(outcomes)
        self.assertTrue(execute(world, combined, memory.compatible_plan(combined))[0])

    def test_two_stages_do_not_inherit_each_others_intermediate_product(self):
        world = build_world()
        pair = commissions(world)[12]
        a = execute(world, pair[0], plans(world, pair[0])[0])
        b = execute(world, pair[1], plans(world, pair[1])[0])
        again = execute(world, pair[1], plans(world, pair[1])[0])
        self.assertEqual(b, again)
        self.assertTrue(a[0] and b[0])
        self.assertIsNone(b[1][0].input_format)

    def test_no_history_fixed_plan_cannot_fit_complementary_private_worlds(self):
        for seed in range(12):
            result = assess(seed)
            self.assertTrue(
                result[
                    "complementary_worlds_same_current_public_commission_disjoint_solutions"
                ]
            )
            self.assertTrue(
                result["complementary_worlds_all_public_commissions_identical"]
            )
            self.assertEqual(
                result["delivered_memory_compatible_combinations"],
                {"correct": 24, "denominator": 24},
            )

    def test_failure_preserves_input_and_permits_a_correct_followup(self):
        world = build_world()
        item = commissions(world)[12][0]
        valid = plans(world, item)[0]
        fmt = world.cataloguers[(item.material, valid[0])]
        wrong = next(
            s
            for (m, s), v in world.verifiers.items()
            if m == item.material and v[0] != fmt
        )
        ok, steps = execute(world, item, (valid[0], wrong, valid[1]))
        self.assertTrue(ok)
        self.assertEqual(
            [x.result for x in steps], ["processed", "unsupported", "processed"]
        )

    def test_local_success_is_not_goal_compatible_first_success(self):
        world = build_world()
        item = commissions(world)[12][0]
        good = plans(world, item)[0]
        wrong = next(
            s for m, s in world.cataloguers if m == item.material and s != good[0]
        )
        ok, outcomes = execute(world, item, (wrong, good[1], "recollect", *good))
        self.assertTrue(ok)
        result = score(world, item, outcomes)
        self.assertEqual(result["required_operations"], 2)
        self.assertTrue(result["operations"][0]["local_first_success"])
        self.assertFalse(result["operations"][0]["goal_compatible_first_success"])
        self.assertFalse(result["whole_stage_first_correct"])

    def test_unattempted_verification_remains_in_the_denominator(self):
        world = build_world()
        item = commissions(world)[12][0]
        _, outcomes = execute(world, item, plans(world, item)[0][:1])
        result = score(world, item, outcomes)
        self.assertEqual(result["required_operations"], 2)
        self.assertFalse(result["operations"][1]["attempted"])
        self.assertFalse(result["whole_stage_first_correct"])

    def test_planned_encounter_does_not_create_an_observed_fact(self):
        world = build_world()
        tasks = commissions(world)
        memory = DeliveredMemory()
        # The schedule is still valid, but one real observation is missing.
        assess_allocation(world, tasks)
        for pair in tasks[:12]:
            for item in pair:
                _, outcomes = execute(world, item, plans(world, item)[0])
                memory.observe(outcomes)
        required = tasks[12][0]
        correct = memory.compatible_plan(required)
        del memory.catalogue[(required.material, correct[0])]
        self.assertIsNone(memory.compatible_plan(required))

    def test_station_numbers_do_not_encode_material_or_requested_standard(self):
        first = build_world(61301)
        second = build_world(61401)
        self.assertNotEqual(first.cataloguers.keys(), second.cataloguers.keys())
        odd_standards = {
            value[1]
            for (_, station), value in first.verifiers.items()
            if int(station[1:]) % 2
        }
        self.assertEqual(odd_standards, {"standard-1", "standard-2"})

    def test_whole_stage_first_score_does_not_improve_after_recollection(self):
        world = build_world()
        item = commissions(world)[12][0]
        good = plans(world, item)[0]
        wrong = next(
            s for m, s in world.cataloguers if m == item.material and s != good[0]
        )
        _, before = execute(world, item, (wrong, good[1]))
        ok, after = execute(world, item, (wrong, good[1], "recollect", *good))
        self.assertTrue(ok)
        self.assertEqual(score(world, item, before), score(world, item, after))

    def test_matched_ablation_changes_only_acceptance_not_the_commissions(self):
        result = interface_ablation(build_world())
        self.assertEqual(result["strict_compatible_choices"], 24)
        self.assertEqual(result["relaxed_compatible_choices"], 48)
        self.assertEqual(result["enumerated_goal_aware_choices"], 48)
        self.assertIsNone(result["agent_accuracy"])

    def test_invalid_mode_or_input_contract_fails_before_execution(self):
        for mode, prepared in [
            ("invented", None),
            ("catalogue", "F123"),
            ("verify", None),
        ]:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                Stage("material-1", mode, "standard-1", prepared)

    def test_relaxed_ablation_scores_any_successful_input_as_goal_compatible(self):
        world = build_world()
        item = commissions(world)[12][0]
        good = plans(world, item)[0]
        wrong = next(
            s for m, s in world.cataloguers if m == item.material and s != good[0]
        )
        relaxed = replace(world, enforce_interface=False)
        ok, outcomes = execute(relaxed, item, (wrong, good[1]))
        self.assertTrue(ok)
        self.assertTrue(score(relaxed, item, outcomes)["whole_stage_first_correct"])
