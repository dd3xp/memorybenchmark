"""Assess one isolated Hard mechanism and project routes onto unchanged Orcia.

Run from the project root with ``python -m scripts.assess_hard_interfaces``.
This tool cannot call a model, create an experiment or change a map. Its route
projection is not StationGame execution or Hermes performance calibration.
"""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import platform
import random

from memorybenchmark.prototypes.composition_lab import (
    assess,
    build_world,
    commissions,
    plans,
)
from memorybenchmark.prototypes.station_capability import load_design, map_world
from memorybenchmark.prototypes.station_routes import shortest_route


PROJECT = Path(__file__).resolve().parents[1]
POLICY = PROJECT / "config/candidates/hard-interface36.json"


def old_cartesian_property(design):
    """Existing Hard's valid first/second choices combine without restriction."""
    world = design["private_worlds"][map_world(design)]
    stages = [
        s
        for t in design["tasks"].values()
        for s in t["stages"]
        if (s["input_state"], s["output_state"]) == ("raw", "verified")
    ]
    total = sum(
        sum(s["required_kind"] in value["catalogue"] for value in world.values())
        * sum(s["required_kind"] in value["verify"] for value in world.values())
        for s in stages
    )
    return {
        "combined_stages": len(stages),
        "locally_valid_station_pairs": total,
        "compatible_pairs": total,
        "reason": "every supported catalogue emits the same universal catalogued state",
    }


def project_orcia(design, seed):
    """Embed the candidate station profiles without editing roads or targets.

    The 24 abstract profiles use the existing 24 station types (two replicas
    each). Current task targets, start, submit and step budgets are reused.
    Distances and action counts are fully informed route upper bounds, not
    an exploration policy's cost. All baseline files remain untouched.
    """
    world = build_world(seed)
    profiles = sorted(
        {s for _, s in world.cataloguers} | {s for _, s in world.verifiers}
    )
    types = design["public"]["station_types"]
    if len(profiles) != len(types):
        raise ValueError("Review the station mapping for this geography separately")
    replicas = {
        profile: tuple(types[name]["stations"])
        for profile, name in zip(profiles, sorted(types))
    }
    tasks = list(design["tasks"].values())
    reference = commissions(world)
    if len(tasks) != len(reference):
        raise ValueError("Route projection requires the current 36-task Orcia")
    maximum = 0
    strict_utility = set()
    rows = []
    for number, (task, pair) in enumerate(zip(tasks, reference), 1):
        current = task["start"]
        actions, distance = 1, 0  # final submit
        for index, item in enumerate(pair):
            target = task["stages"][index]["target"]
            destination = (
                task["stages"][index + 1]["target"]
                if index + 1 < len(pair)
                else task["submit_at"]
            )
            choices = []
            for profile_plan in plans(world, item):
                for station_plan in product(*(replicas[p] for p in profile_plan)):
                    stops = (target, *station_plan, destination)
                    legs = [
                        shortest_route(design, a, b) for a, b in zip(stops, stops[1:])
                    ]
                    choices.append(
                        (
                            sum(cost for _, cost in legs),
                            sum(len(path) - 1 for path, _ in legs),
                            station_plan,
                        )
                    )
            best_distance = min(c[0] for c in choices)
            tied = [c for c in choices if c[0] == best_distance]
            best = min(tied, key=lambda c: (c[1], c[2]))
            for operation in range(len(best[2])):
                stations = {c[2][operation] for c in tied}
                if len(stations) == 1:
                    strict_utility.update(stations)
            prefix, prefix_distance = shortest_route(design, current, target)
            distance += prefix_distance + best[0]
            actions += len(prefix) - 1 + best[1] + 1 + len(best[2])  # collect + process
            current = destination
        if actions > task["max_steps"]:
            raise ValueError(f"T{number} lacks a route within the current step budget")
        maximum = max(maximum, actions)
        rows.append(
            {
                "task": f"T{number}",
                "targets": [s["target"] for s in task["stages"]],
                "reference_actions": actions,
                "reference_distance": distance,
                "budget": task["max_steps"],
            }
        )
    all_stations = {s for values in replicas.values() for s in values}
    return {
        "map": "orcia",
        "candidate_station_profiles": len(replicas),
        "existing_physical_stations": len(all_stations),
        "tasks_with_a_reference_route_inside_budget": len(rows),
        "maximum_reference_actions": maximum,
        "strict_shortest_route_useful_stations": len(strict_utility),
        "stations_without_strict_route_utility": sorted(all_stations - strict_utility),
        "roads_changed": False,
        "task_targets_changed": False,
        "production_station_capabilities_changed": False,
        "stationgame_execution_validated": False,
        "fully_informed_route_projection_only": True,
        "tasks": rows,
    }


def review_orcia_targets(design, seed, iterations):
    """Review Orcia only: exchange collection targets without editing roads.

    The search uses route utility, never agent outcomes. It preserves the
    complete multiset of collection sites and all processing commissions.
    This returns a proposal; it does not mutate or write the source design.
    """
    candidate = deepcopy(design)
    stages = [s for t in candidate["tasks"].values() for s in t["stages"]]
    rng = random.Random(seed)
    best = project_orcia(candidate, seed)
    steps = 0
    for iteration in range(1, iterations + 1):
        if not best["stations_without_strict_route_utility"]:
            break
        steps = iteration
        first, second = rng.sample(stages, 2)
        first["target"], second["target"] = second["target"], first["target"]
        proposed = project_orcia(candidate, seed)
        gain = (
            proposed["strict_shortest_route_useful_stations"]
            - best["strict_shortest_route_useful_stations"]
        )
        if gain > 0 or (gain == 0 and rng.random() < 0.025):
            best = proposed
        else:
            first["target"], second["target"] = second["target"], first["target"]
    original = [s["target"] for t in design["tasks"].values() for s in t["stages"]]
    proposed = [s["target"] for s in stages]
    if sorted(original) != sorted(proposed):
        raise AssertionError("Target review changed the collection-site multiset")
    best.update(
        status="target_assignment_proposal_only",
        search_iterations=steps,
        changed_stage_targets=sum(a != b for a, b in zip(original, proposed)),
        task_targets_changed=original != proposed,
        original_target_multiset_preserved=True,
        model_outcomes_used_for_target_search=False,
    )
    return best


def assessment(policy, project=PROJECT):
    expected = {
        "tasks": 36,
        "stages_per_task": 2,
        "materials": 6,
        "intermediate_formats_per_material": 2,
        "requested_standards_per_material": 2,
        "standalone_uses_per_scoped_experience": 2,
        "combined_uses_per_scoped_experience": 2,
        "partner_offsets": [5, 7, 3],
    }
    if any(policy.get(key) != value for key, value in expected.items()):
        raise ValueError("This lab implements only the explicit interface36 contract")
    if policy["geography_review"] != "orcia_only":
        raise ValueError("Other maps need individual assessments")
    source = project / policy["geography_design"]
    before = source.read_bytes()
    design = load_design(source)
    seeds = [assess(seed) for seed in policy["mechanism_seeds"]]
    result = {
        "schema": "hard-interface-mechanism-assessment-1",
        "status": "candidate_not_promoted_no_model_calibration",
        "model_calls": 0,
        "current_hard_cartesian_property": old_cartesian_property(design),
        "candidate": seeds[0],
        "additional_seeds": [
            {
                "seed": r["seed"],
                "allocation": r["allocation"],
                "full_memory_combinations": r[
                    "delivered_memory_compatible_combinations"
                ],
                "interface_blind_choices": r["goal_aware_but_interface_blind_choices"],
            }
            for r in seeds[1:]
        ],
        "orcia_route_projection": project_orcia(design, policy["geography_seed"]),
        "orcia_target_review": review_orcia_targets(
            design, policy["geography_seed"], policy["target_review_iterations"]
        ),
        "source_map_sha256": sha256(before).hexdigest(),
        "production_files_changed": False,
        "target_model_gap_observed": None,
        "selection_on_diagnostic_policy_scores_is_forbidden": True,
    }
    if source.read_bytes() != before:
        raise AssertionError("Read-only assessment changed the map")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    result = assessment(policy)
    result["policy_sha256"] = sha256(POLICY.read_bytes()).hexdigest()
    result["implementation_sha256"] = sha256(
        (PROJECT / "memorybenchmark/prototypes/composition_lab.py").read_bytes()
    ).hexdigest()
    result["assessment_tool_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    result["python_version"] = platform.python_version()
    if args.output.exists():
        raise FileExistsError("Use a new assessment name; preserve previous results")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "model_calls": 0,
                "reference_route_tasks": result["orcia_route_projection"][
                    "tasks_with_a_reference_route_inside_budget"
                ],
                "target_model_gap_observed": None,
            }
        )
    )


if __name__ == "__main__":
    main()
