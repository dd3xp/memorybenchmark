"""Context binding with shared format names and overlapping fixed station rules."""

from collections import Counter
from itertools import combinations
import random

from .composition_lab import World, cases, experience_keys, stage


def binding_world(seed=61401):
    rng = random.Random(seed)
    materials = tuple(f"material-{i+1}" for i in range(12))
    profiles = [f"P{i+1:02d}" for i in range(24)]
    rng.shuffle(profiles)
    shared = ("F-1", "F-2")
    cataloguers, verifiers = {}, {}
    for i, material in enumerate(materials):
        for offset in range(4):
            profile = profiles[(2 * i + offset) % 12]
            cataloguers[(material, profile)] = shared[(offset // 2 + i // 6) % 2]
        input_order = list(shared)
        rng.shuffle(input_order)
        goals = ["standard-1", "standard-2"]
        rng.shuffle(goals)
        for offset in range(4):
            profile = profiles[12 + (5 * i + offset) % 12]
            verifiers[(material, profile)] = (
                input_order[offset // 2],
                goals[offset // 2],
            )
    return World(materials, {m: shared for m in materials}, cataloguers, verifiers)


def pilot_materials(world):
    """Select a rule-only subset that exercises both contextual collisions.

    This consults no agent outcomes. A pilot lacking either collision cannot
    evaluate the conditional binding mechanism of the full world.
    """
    for selected in combinations(world.materials, 4):
        catalogue, verification = {}, {}
        for (material, station), output in world.cataloguers.items():
            if material in selected:
                catalogue.setdefault(station, set()).add(output)
        for (material, station), (input_format, output) in world.verifiers.items():
            if material in selected:
                verification.setdefault((station, input_format), set()).add(output)
        if sum(len(v) > 1 for v in catalogue.values()) >= 2 and any(
            len(v) > 1 for v in verification.values()
        ):
            return selected
    raise ValueError("No four-material pilot exercises both kinds of scope collision")


def once_commissions(world, selected_materials=None):
    family = [
        case
        for case in cases(world)
        if selected_materials is None or case[0] in selected_materials
    ]
    if not family or len(family) % 2:
        raise ValueError("The complete paired curriculum needs an even number of goals")
    count = len(family)
    normal = [
        (
            stage(world, case, "catalogue"),
            stage(world, family[(i + 5) % count], "verify"),
        )
        for i, case in enumerate(family)
    ]
    combined = [
        (
            stage(world, family[i], "combined"),
            stage(world, family[i + count // 2], "combined"),
        )
        for i in range(count // 2)
    ]
    return normal + combined


def check_once_allocation(world, tasks):
    single, combined = Counter(), Counter()
    earlier = set()
    for pair in tasks:
        if len(pair) != 2:
            raise ValueError("Every commission has two independent stages")
        before = set(earlier)
        for item in pair:
            keys = experience_keys(item, world)
            if item.mode == "combined":
                if not set(keys) <= before:
                    raise ValueError(
                        "Combination precedes prior ordinary opportunities"
                    )
                combined.update(keys)
            else:
                single.update(keys)
                earlier.update(keys)
    if (
        set(single) != set(combined)
        or set(single.values()) != {1}
        or set(combined.values()) != {1}
    ):
        raise ValueError(
            "Each complete goal class requires one standalone and one combined use"
        )
    return {
        "tasks": len(tasks),
        "stages": sum(map(len, tasks)),
        "fully_scoped_goal_classes": len(single),
        "necessary_operations": sum(single.values()) + sum(combined.values()),
        "single_uses_each": 1,
        "combined_uses_each": 1,
        "materials": len({s.material for pair in tasks for s in pair}),
        "unscored_lessons": 0,
        "stage_dependency": False,
        "private_positive_bindings_in_full_world": len(world.cataloguers)
        + len(world.verifiers),
        "all_alternative_bindings_are_not_claimed_learned": True,
    }
