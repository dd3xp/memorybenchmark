"""Isolated composition design lab; no gateway, live map, or native run changes.

This is an executable mechanism sample, not an estimate of an agent's score.
Opaque intermediate identifiers bind a cataloguer's output to a verifier's
input. The two commission stages remain independent throughout.
"""

from collections import Counter
from dataclasses import InitVar, asdict, dataclass, field, replace
import random


SEAL_MATCH = "封签一致"
SEAL_MISMATCH = "封签不同"
SEAL_RELATIONS = (SEAL_MATCH, SEAL_MISMATCH)


def seal_relation(catalogue_seal, verifier_seal):
    if catalogue_seal is None or verifier_seal is None:
        return None
    return SEAL_MATCH if catalogue_seal == verifier_seal else SEAL_MISMATCH


@dataclass(frozen=True)
class Stage:
    material: str
    mode: str
    goal: str
    input_format: str | None = None
    delivery_condition: str | None = None

    def __post_init__(self):
        if self.mode not in ("catalogue", "verify", "combined"):
            raise ValueError("Unknown processing mode")
        if (self.mode == "verify") != (self.input_format is not None):
            raise ValueError("Only standalone verification starts with prepared input")
        if self.delivery_condition is not None and (
            not isinstance(self.delivery_condition, str)
            or not self.delivery_condition.strip()
        ):
            raise ValueError("Delivery condition must be a nonempty label")

    def public(self):
        fields = asdict(self)
        if self.delivery_condition is None:
            del fields["delivery_condition"]
        return fields


@dataclass(frozen=True)
class Outcome:
    station: str
    material: str
    operation: str
    input_format: str | None
    output_format: str | None
    result: str
    processing_seal: InitVar[str | None] = field(default=None, kw_only=True)
    delivery_condition = None

    def __post_init__(self, processing_seal):
        # Optional evidence stays out of the old unsealed dataclass records.
        object.__setattr__(self, "processing_seal", processing_seal)

    def public(self):
        fields = asdict(self)
        if self.processing_seal is not None:
            fields["processing_seal"] = self.processing_seal
        return fields

    def with_condition(self, condition):
        if condition is None:
            return self
        if isinstance(self, ConditionedOutcome):
            return replace(
                self, delivery_condition=condition, processing_seal=self.processing_seal
            )
        return ConditionedOutcome(
            **asdict(self),
            delivery_condition=condition,
            processing_seal=self.processing_seal,
        )


@dataclass(frozen=True)
class ConditionedOutcome(Outcome):
    delivery_condition: str


@dataclass(frozen=True)
class World:
    materials: tuple[str, ...]
    formats: dict
    cataloguers: dict
    verifiers: dict
    enforce_interface: bool = True
    format_conditions: dict | None = None
    verification_conditions: dict | None = None
    catalogue_seals: dict | None = None
    verifier_seals: dict | None = None

    def condition(self, material, fmt):
        return (self.format_conditions or {}).get((material, fmt))

    def catalogue_seal(self, material, fmt):
        return (self.catalogue_seals or {}).get((material, fmt))

    def verifier_seal(self, material, station):
        return (self.verifier_seals or {}).get(material, {}).get(station)

    def compares_seals(self, item):
        return item.mode == "combined" and item.material in (self.verifier_seals or {})

    def verifier_condition(self, material, station, fmt, *, compare_seals=False):
        raw_seal = self.verifier_seal(material, station)
        if raw_seal is not None:
            relation = (
                seal_relation(self.catalogue_seal(material, fmt), raw_seal)
                if compare_seals
                else None
            )
            return relation if relation is not None else raw_seal
        return (
            (self.verification_conditions or {})
            .get(material, {})
            .get(station, self.condition(material, fmt))
        )

    def verifiers_for_stage(self, item):
        return [
            (station, (fmt, goal))
            for (material, station), (fmt, goal) in self.verifiers.items()
            if material == item.material
            and goal == item.goal
            and (item.input_format is None or fmt == item.input_format)
            and condition_matches(
                item,
                self.verifier_condition(
                    material, station, fmt, compare_seals=self.compares_seals(item)
                ),
            )
        ]

    def required_verifier_seal(self, item):
        if item.mode == "catalogue" or item.material not in (self.verifier_seals or {}):
            return None
        (raw_seal,) = {
            self.verifier_seal(item.material, station)
            for station, _ in self.verifiers_for_stage(item)
        }
        return raw_seal

    def catalogue_condition_matches(self, item, actual):
        return (
            item.material in (self.verification_conditions or {})
            or item.material in (self.verifier_seals or {})
            or condition_matches(item, actual)
        )

    def process(self, station, material, input_format=None, *, compare_seals=False):
        operation = "catalogue" if input_format is None else "verify"
        if operation == "catalogue":
            value = self.cataloguers.get((material, station))
            outcome = Outcome(
                station,
                material,
                operation,
                None,
                value,
                "processed" if value else "unsupported",
                processing_seal=self.catalogue_seal(material, value) if value else None,
            )
            return outcome.with_condition(self.condition(material, value))
        required = self.verifiers.get((material, station))
        success = required is not None and (
            required[0] == input_format or not self.enforce_interface
        )
        outcome = Outcome(
            station,
            material,
            operation,
            input_format,
            required[1] if success else None,
            "processed" if success else "unsupported",
            processing_seal=self.verifier_seal(material, station) if success else None,
        )
        return (
            outcome.with_condition(
                self.verifier_condition(
                    material, station, input_format, compare_seals=compare_seals
                )
            )
            if success
            else outcome
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


def condition_matches(item, actual):
    return item.delivery_condition is None or actual == item.delivery_condition


def input_for_stage(world, item):
    if item.delivery_condition is None:
        return input_for_goal(world, item.material, item.goal)
    (fmt,) = {fmt for _, (fmt, _) in world.verifiers_for_stage(item)}
    return fmt


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
        and world.catalogue_condition_matches(item, world.condition(kind, fmt))
    ]
    if item.mode == "catalogue":
        return [(station,) for station, fmt in cataloguers if fmt == item.goal]
    verifiers = world.verifiers_for_stage(item)
    if item.mode == "verify":
        return [(station,) for station, _ in verifiers]
    return [
        (a, b)
        for a, fmt in cataloguers
        for b, (required_format, _) in verifiers
        if required_format == fmt or not world.enforce_interface
    ]


def execute(world, item, chosen):
    """One stage; recollect discards this sample and restores its public input.

    Recollection is an explicit lab action, not an automatic retry. It does not
    clear attempts or change the first-attempt score. A production map would
    additionally require travelling to the collection site again.
    """
    current = item.input_format
    outcomes = []
    completed = current == item.goal and item.delivery_condition is None
    compare_seals = world.compares_seals(item)
    for station in chosen:
        if completed:
            break
        if station == "recollect":
            current = item.input_format
            continue
        outcome = world.process(
            station, item.material, current, compare_seals=compare_seals
        )
        outcomes.append(outcome)
        if outcome.result == "processed":
            current = outcome.output_format
            if current == item.goal and condition_matches(
                item, outcome.delivery_condition
            ):
                completed = True
    return completed, outcomes


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
        input_for_stage(world, item) if item.mode == "combined" else item.goal
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
                compatible = compatible and world.catalogue_condition_matches(
                    item, first.delivery_condition
                )
            else:
                compatible = first.output_format == item.goal and condition_matches(
                    item, first.delivery_condition
                )
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
        input_for_stage(world, item)
        if item.mode == "combined"
        else (item.goal if item.mode == "catalogue" else item.input_format)
    )
    keys = []
    if item.mode != "verify":
        keys.append((item.material, "catalogue", fmt))
    if item.mode != "catalogue":
        key = (item.material, "verify", fmt, item.goal)
        seal = world.required_verifier_seal(item)
        if seal is not None:
            key += (seal,)
        elif item.material in (world.verification_conditions or {}):
            key += (item.delivery_condition,)
        keys.append(key)
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
            key = (item.material, item.station)
            if item.operation == "catalogue":
                self.catalogue[key] = item
            else:
                # A combined result's relation describes the whole route.
                # Keep the verification station's own seal for later pairings.
                self.verify[key] = item.with_condition(item.processing_seal)

    def compatible_plan(self, item):
        if item.mode == "catalogue":
            return next(
                (
                    (station,)
                    for (kind, station), observed in self.catalogue.items()
                    if kind == item.material
                    and observed.output_format == item.goal
                    and condition_matches(item, observed.delivery_condition)
                ),
                None,
            )
        needs_relation = (
            item.mode == "combined" and item.delivery_condition in SEAL_RELATIONS
        )
        choices = [
            (station, observed)
            for (kind, station), observed in self.verify.items()
            if kind == item.material
            and observed.output_format == item.goal
            and (needs_relation or condition_matches(item, observed.delivery_condition))
        ]
        if item.mode == "verify":
            return next(
                (
                    (station,)
                    for station, observed in choices
                    if observed.input_format == item.input_format
                ),
                None,
            )
        return next(
            (
                (a, b)
                for (kind, a), catalogue in self.catalogue.items()
                for b, verifier in choices
                if kind == item.material
                and catalogue.output_format == verifier.input_format
                and _observed_catalogue_accepts(
                    item, catalogue, verifier, needs_relation
                )
            ),
            None,
        )


def _observed_catalogue_accepts(item, catalogue, verifier, needs_relation):
    if needs_relation:
        return condition_matches(
            item, seal_relation(catalogue.processing_seal, verifier.processing_seal)
        )
    return catalogue.delivery_condition is None or condition_matches(
        item, catalogue.delivery_condition
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
                                    "actual_feedback": [x.public() for x in outcome],
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
