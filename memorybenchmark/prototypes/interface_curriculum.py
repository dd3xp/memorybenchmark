"""Context binding with shared format names and overlapping fixed station rules."""

from collections import Counter
from itertools import combinations
import random

from .composition_lab import World, cases, experience_keys, stage


def binding_world(seed=61401, *, material_count=12):
    if type(material_count) is not int or material_count not in (6, 8, 12):
        raise ValueError("Binding worlds need six, eight or twelve materials")
    rng = random.Random(seed)
    materials = tuple(f"material-{i+1}" for i in range(material_count))
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


def balanced_commissions(world):
    """Eight materials, three scored uses per complete experience, 36 tasks.

    Every goal first appears in an ordinary commission. For each material one
    goal has two standalone uses and one combination, the other one standalone
    use and two combinations. The assignment alternates between materials.
    """
    if len(world.materials) != 8:
        raise ValueError("The balanced-three curriculum needs eight materials")
    family = cases(world)
    count = len(family)
    ordinary = [
        (
            stage(world, case, "catalogue"),
            stage(world, family[(i + 5) % count], "verify"),
        )
        for i, case in enumerate(family)
    ]
    twice_standalone = [(i // 2 + i % 2) % 2 == 0 for i in range(count)]
    extra = [
        stage(world, case, mode)
        for i, case in enumerate(family)
        if twice_standalone[i]
        for mode in ("catalogue", "verify")
    ]
    combined = [stage(world, case, "combined") for case in family]
    combined += [
        stage(world, case, "combined")
        for i, case in enumerate(family)
        if not twice_standalone[i]
    ]
    mixed = [(combined[i], item) for i, item in enumerate(extra)]
    remaining = combined[len(extra) :]
    tail = list(zip(remaining[:4], remaining[4:]))
    return ordinary + mixed + tail


def check_balanced_allocation(world, tasks):
    single, combined, earlier = Counter(), Counter(), set()
    for pair in tasks:
        if len(pair) != 2:
            raise ValueError("Every commission needs two independent stages")
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
        len(tasks) != 36
        or len(world.materials) != 8
        or len(single) != 32
        or set(single) != set(combined)
        or any((single[k], combined[k]) not in ((1, 2), (2, 1)) for k in single)
        or sum(single.values()) != 48
        or sum(combined.values()) != 48
    ):
        raise ValueError("Each complete experience needs three balanced scored uses")
    return {
        "tasks": 36,
        "stages": 72,
        "fully_scoped_goal_classes": 32,
        "necessary_operations": 96,
        "uses_each": 3,
        "standalone_plus_combined_uses": [[1, 2], [2, 1]],
        "materials": 8,
        "first_combination_task": 17,
        "stage_dependency": False,
        "unscored_lessons": 0,
        "all_alternative_bindings_are_not_claimed_learned": True,
    }


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
