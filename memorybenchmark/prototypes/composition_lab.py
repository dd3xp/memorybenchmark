"""Isolated composition design lab; no gateway, live map, or native run changes.

This is an executable mechanism sample, not an estimate of an agent's score.
Opaque intermediate identifiers bind a cataloguer's output to a verifier's
input. The two commission stages remain independent throughout.
"""

from collections import Counter
from dataclasses import asdict, dataclass, replace
import random


@dataclass(frozen=True)
class Stage:
    material: str
    mode: str
    goal: str
    input_format: str | None = None

    def __post_init__(self):
        if self.mode not in ("catalogue", "verify", "combined"):
            raise ValueError("Unknown processing mode")
        if (self.mode == "verify") != (self.input_format is not None):
            raise ValueError("Only standalone verification starts with prepared input")

    def public(self):
        return asdict(self)


@dataclass(frozen=True)
class Outcome:
    station: str
    material: str
    operation: str
    input_format: str | None
    output_format: str | None
    result: str


@dataclass(frozen=True)
class World:
    materials: tuple[str, ...]
    formats: dict
    cataloguers: dict
    verifiers: dict
    enforce_interface: bool = True

    def process(self, station, material, input_format=None):
        operation = "catalogue" if input_format is None else "verify"
        if operation == "catalogue":
            value = self.cataloguers.get((material, station))
            return Outcome(
                station,
                material,
                operation,
                None,
                value,
                "processed" if value else "unsupported",
            )
        required = self.verifiers.get((material, station))
        success = required is not None and (
            required[0] == input_format or not self.enforce_interface
        )
        return Outcome(
            station,
            material,
            operation,
            input_format,
            required[1] if success else None,
            "processed" if success else "unsupported",
        )


def build_world(seed=61301, flip_catalogues=False):
    rng = random.Random(seed)
    materials = tuple(f"material-{i + 1}" for i in range(6))
    labels = rng.sample(range(100, 999), 12)
    stations = [f"P{i+1:02d}" for i in range(24)]
    rng.shuffle(stations)
    formats, cataloguers, verifiers = {}, {}, {}
    for i, material in enumerate(materials):
        fmts = (f"F{labels[2*i]}", f"F{labels[2*i+1]}")
        formats[material] = fmts
        output_order = list(fmts)
        if rng.randrange(2) ^ flip_catalogues:
            output_order.reverse()
        for j in range(2):
            cataloguers[(material, stations[i * 2 + j])] = output_order[j]
        input_order = list(fmts)
        if rng.randrange(2):
            input_order.reverse()
        standards = ["standard-1", "standard-2"]
        rng.shuffle(standards)
        for j in range(2):
            verifiers[(material, stations[12 + i * 2 + j])] = (
                input_order[j],
                standards[j],
            )
    return World(materials, formats, cataloguers, verifiers)


def cases(world):
    return [
        (material, standard)
        for material in world.materials
        for standard in ("standard-1", "standard-2")
    ]


def input_for_goal(world, material, goal):
    return next(
        value[0]
        for (kind, _), value in world.verifiers.items()
        if kind == material and value[1] == goal
    )


def stage(world, case, mode):
    material, goal = case
    fmt = input_for_goal(world, material, goal)
    return Stage(
        material,
        mode,
        fmt if mode == "catalogue" else goal,
        fmt if mode == "verify" else None,
    )


def commissions(world, selected_materials=None):
    """36 ordinary scored commissions; no injected lesson or memory document."""
    family = cases(world)
    if selected_materials is not None:
        family = [case for case in family if case[0] in selected_materials]
    count = len(family)
    if not count:
        raise ValueError("At least one material must have ordinary commissions")
    result = []
    for block in range(3):
        for i, case in enumerate(family):
            if block == 0:
                pair = (
                    stage(world, case, "catalogue"),
                    stage(world, family[(i + 5) % count], "verify"),
                )
            elif block == 1:
                pair = (
                    stage(world, case, "combined"),
                    stage(world, family[(i + 7) % count], "catalogue"),
                )
            else:
                pair = (
                    stage(world, family[(i + 3) % count], "verify"),
                    stage(world, case, "combined"),
                )
            result.append(pair)
    return result


def plans(world, item):
    cataloguers = [
        (station, fmt)
        for (kind, station), fmt in world.cataloguers.items()
        if kind == item.material
    ]
    verifiers = [
        (station, value)
        for (kind, station), value in world.verifiers.items()
        if kind == item.material
    ]
    if item.mode == "catalogue":
        return [(station,) for station, fmt in cataloguers if fmt == item.goal]
    if item.mode == "verify":
        return [
            (station,)
            for station, value in verifiers
            if value == (item.input_format, item.goal)
        ]
    return [
        (a, b)
        for a, fmt in cataloguers
        for b, value in verifiers
        if value[1] == item.goal and (value[0] == fmt or not world.enforce_interface)
    ]


def execute(world, item, chosen):
    """One stage; recollect discards this sample and restores its public input.

    Recollection is an explicit lab action, not an automatic retry. It does not
    clear attempts or change the first-attempt score. A production map would
    additionally require travelling to the collection site again.
    """
    current = item.input_format
    outcomes = []
    for station in chosen:
        if current == item.goal:
            break
        if station == "recollect":
            current = item.input_format
            continue
        outcome = world.process(station, item.material, current)
        outcomes.append(outcome)
        if outcome.result == "processed":
            current = outcome.output_format
    return current == item.goal, outcomes


def score(world, item, outcomes):
    """Judge the first required operations, including unattempted operations.

    Local processing success is reported separately. A successful catalogue
    operation can still produce the wrong interface for the requested goal.
    Evaluator-only rules decide goal compatibility; they are never feedback.
    """
    operations = ("verify",) if item.mode == "verify" else ("catalogue",)
    if item.mode == "combined":
        operations += ("verify",)
    expected_format = (
        input_for_goal(world, item.material, item.goal)
        if item.mode == "combined"
        else item.goal
    )
    rows = []
    for operation in operations:
        first = next((o for o in outcomes if o.operation == operation), None)
        local = bool(first and first.result == "processed")
        compatible = False
        if local:
            if operation == "catalogue":
                compatible = (
                    item.mode == "combined" and not world.enforce_interface
                ) or first.output_format == expected_format
            else:
                compatible = first.output_format == item.goal
        rows.append(
            {
                "operation": operation,
                "attempted": first is not None,
                "local_first_success": local,
                "goal_compatible_first_success": compatible,
            }
        )
    return {
        "required_operations": len(rows),
        "operations": rows,
        "whole_stage_first_correct": all(
            r["goal_compatible_first_success"] for r in rows
        ),
    }


def interface_ablation(world):
    """Same tasks, labels and station rules; only the interface check differs.

    Enumerate choices of a known goal-producing verifier and either locally
    capable cataloguer. This is not a model or a claim about agent accuracy.
    """
    relaxed = replace(world, enforce_interface=False)
    strict_correct = relaxed_correct = total = 0
    for pair in commissions(world):
        for item in pair:
            if item.mode != "combined":
                continue
            cataloguers = [s for m, s in world.cataloguers if m == item.material]
            verifier = next(
                s
                for (m, s), value in world.verifiers.items()
                if m == item.material and value[1] == item.goal
            )
            for cataloguer in cataloguers:
                strict_correct += execute(world, item, (cataloguer, verifier))[0]
                relaxed_correct += execute(relaxed, item, (cataloguer, verifier))[0]
                total += 1
    return {
        "enumerated_goal_aware_choices": total,
        "strict_compatible_choices": strict_correct,
        "relaxed_compatible_choices": relaxed_correct,
        "only_changed_rule": "verifier_requires_matching_input_format",
        "agent_accuracy": None,
    }


def experience_keys(item, world):
    fmt = (
        input_for_goal(world, item.material, item.goal)
        if item.mode == "combined"
        else (item.goal if item.mode == "catalogue" else item.input_format)
    )
    keys = []
    if item.mode != "verify":
        keys.append((item.material, "catalogue", fmt))
    if item.mode != "catalogue":
        goal = item.goal
        keys.append((item.material, "verify", fmt, goal))
    return keys


def assess_allocation(world, tasks):
    single, combined, earlier = Counter(), Counter(), set()
    for pair in tasks:
        before = set(earlier)
        if len(pair) != 2:
            raise ValueError("Every commission needs two independent stages")
        for item in pair:
            keys = experience_keys(item, world)
            if item.mode == "combined":
                if not set(keys) <= before:
                    raise ValueError(
                        "Combination precedes an earlier ordinary experience"
                    )
                combined.update(keys)
            else:
                single.update(keys)
                earlier.update(keys)
    if (
        set(single) != set(combined)
        or set(single.values()) != {2}
        or set(combined.values()) != {2}
    ):
        raise ValueError(
            "Every fully scoped experience needs 2 single + 2 combined uses"
        )
    return {
        "tasks": len(tasks),
        "stages": sum(map(len, tasks)),
        "fully_scoped_experiences": len(single),
        "necessary_operations": sum(single.values()) + sum(combined.values()),
        "single_uses_each": 2,
        "combined_uses_each": 2,
        "materials": len({s.material for pair in tasks for s in pair}),
        "requested_standards": 2,
        "stage_dependency": False,
        "unscored_lessons": 0,
    }


class DeliveredMemory:
    """A diagnostic policy memory, explicitly NOT Hermes or an agent score."""

    def __init__(self):
        self.catalogue = {}
        self.verify = {}

    def observe(self, outcomes):
        for item in outcomes:
            if item.result != "processed":
                continue
            if item.operation == "catalogue":
                self.catalogue[(item.material, item.station)] = item.output_format
            else:
                self.verify[(item.material, item.station)] = (
                    item.input_format,
                    item.output_format,
                )

    def compatible_plan(self, item):
        if item.mode == "catalogue":
            return next(
                (
                    (station,)
                    for (kind, station), fmt in self.catalogue.items()
                    if kind == item.material and fmt == item.goal
                ),
                None,
            )
        choices = [
            (station, value)
            for (kind, station), value in self.verify.items()
            if kind == item.material and value[1] == item.goal
        ]
        if item.mode == "verify":
            return next(
                (
                    (station,)
                    for station, value in choices
                    if value[0] == item.input_format
                ),
                None,
            )
        return next(
            (
                (a, b)
                for (kind, a), fmt in self.catalogue.items()
                for b, value in choices
                if kind == item.material and fmt == value[0]
            ),
            None,
        )


def assess(seed=61301):
    world = build_world(seed)
    tasks = commissions(world)
    allocation = assess_allocation(world, tasks)
    memory = DeliveredMemory()
    known_success = coarse_success = goal_aware_success = 0
    combinations = reference_success = 0
    wrong_interfaces = []
    for number, pair in enumerate(tasks, 1):
        for index, item in enumerate(pair):
            valid = plans(world, item)
            if len(valid) != 1:
                raise AssertionError("Sample must have one feasible goal plan")
            success, observations = execute(world, item, valid[0])
            if not success:
                raise AssertionError("Fully informed reference cannot finish")
            reference_success += success
            if item.mode == "combined":
                combinations += 1
                learned = memory.compatible_plan(item)
                if learned is None:
                    raise AssertionError(
                        "Earlier successful commissions did not provide both interface facts"
                    )
                known_success += execute(world, item, learned)[0]
                # Both station categories can process this material locally.
                # Enumerate their product, rather than choosing a fortunate pair.
                cats = [s for kind, s in world.cataloguers if kind == item.material]
                vers = [s for kind, s in world.verifiers if kind == item.material]
                for a in cats:
                    for b in vers:
                        ok, outcome = execute(world, item, (a, b))
                        coarse_success += ok
                        if world.verifiers[(item.material, b)][1] == item.goal:
                            goal_aware_success += ok
                        if (
                            outcome[-1].result == "unsupported"
                            and world.verifiers[(item.material, b)][1] == item.goal
                            and len(wrong_interfaces) < 4
                        ):
                            wrong_interfaces.append(
                                {
                                    "task": number,
                                    "stage": index + 1,
                                    "public_commission": item.public(),
                                    "chosen": [a, b],
                                    "actual_feedback": [asdict(x) for x in outcome],
                                }
                            )
            memory.observe(observations)
    other = build_world(seed, flip_catalogues=True)
    same_public = [[s.public() for s in pair] for pair in tasks] == [
        [s.public() for s in pair] for pair in commissions(other)
    ]
    disjoint = all(
        set(plans(world, item)).isdisjoint(plans(other, item))
        for pair in tasks
        for item in pair
        if item.mode == "combined"
    )
    return {
        "seed": seed,
        "status": "mechanism_validation_only_not_model_calibration",
        "allocation": allocation,
        "fully_informed_stage_successes": reference_success,
        "delivered_memory_compatible_combinations": {
            "correct": known_success,
            "denominator": combinations,
        },
        "all_locally_capable_cartesian_choices": {
            "goal_compatible": coarse_success,
            "enumerated_choices": combinations * 4,
        },
        "goal_aware_but_interface_blind_choices": {
            "goal_compatible": goal_aware_success,
            "enumerated_choices": combinations * 2,
        },
        "matched_rule_ablation": interface_ablation(world),
        "complementary_worlds_same_current_public_commission_disjoint_solutions": same_public
        and disjoint,
        "complementary_worlds_all_public_commissions_identical": same_public,
        "two_complementary_worlds_fixed_plan_average_success_upper_bound": (
            0.5 if same_public and disjoint else None
        ),
        "world_rules_fixed_during_each_run": True,
        "current_requirements_imply_private_intermediate_format": False,
        "wrong_interface_witnesses": wrong_interfaces,
        "actual_model_calls": 0,
        "diagnostic_history_source": "oracle-completed ordinary commissions; not an observed agent learning trajectory",
        "choice_enumeration_is_not_a_policy_or_agent_score": True,
        "does_not_estimate_luna_performance": True,
    }
