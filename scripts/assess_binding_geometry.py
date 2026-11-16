"""Read-only Orcia review for the unlaunched full conditional-interface design."""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import plans
from memorybenchmark.prototypes.station_interfaces import load, world, item
from memorybenchmark.prototypes.station_routes import shortest_route


PROJECT = Path(__file__).resolve().parents[1]
GEOGRAPHY_FIELDS = ("locations", "edges", "station_types")


def geography(public):
    return {key: public[key] for key in GEOGRAPHY_FIELDS}


def assess(authored, original):
    """Separate fully informed utility from utility of a known station-type path.

    An alternative station need not be globally best to be useful to an agent
    who has observed only a subset of the valid type paths. Neither count is
    an estimate of model performance.
    """
    if geography(authored["public"]) != geography(original["public"]):
        raise ValueError("This review must use the unchanged Orcia geography")
    design = load(deepcopy(authored))
    w = world(design)
    replicas = {
        name: value["stations"]
        for name, value in design["public"]["station_types"].items()
    }
    all_stations = {s for values in replicas.values() for s in values}
    known_path_coverage, oracle_coverage, strict_oracle = set(), set(), set()
    rows = []
    for task_id, task in design["tasks"].items():
        current, actions, distance = task["start"], 1, 0
        for index, stage in enumerate(task["stages"]):
            destination = (
                task["stages"][index + 1]["target"]
                if index + 1 < len(task["stages"])
                else task["submit_at"]
            )
            choices = []
            for type_path in plans(w, item(stage)):
                branch = []
                for station_path in product(*(replicas[p] for p in type_path)):
                    stops = (stage["target"], *station_path, destination)
                    legs = [
                        shortest_route(design, a, b) for a, b in zip(stops, stops[1:])
                    ]
                    branch.append(
                        (
                            sum(cost for _, cost in legs),
                            sum(len(path) - 1 for path, _ in legs),
                            station_path,
                        )
                    )
                branch_cost = min(choice[0] for choice in branch)
                for choice in branch:
                    if choice[0] == branch_cost:
                        known_path_coverage.update(choice[2])
                choices.extend(branch)
            best_cost = min(choice[0] for choice in choices)
            tied = [choice for choice in choices if choice[0] == best_cost]
            for choice in tied:
                oracle_coverage.update(choice[2])
            best = min(tied, key=lambda choice: (choice[1], choice[2]))
            for operation in range(len(best[2])):
                stations = {choice[2][operation] for choice in tied}
                if len(stations) == 1:
                    strict_oracle.update(stations)
            prefix, cost = shortest_route(design, current, stage["target"])
            distance += cost + best[0]
            actions += len(prefix) - 1 + best[1] + 1 + len(best[2])
            current = destination
        if actions > task["max_steps"]:
            raise ValueError("The candidate lacks an original-budget reference path")
        rows.append(
            {
                "task": task_id,
                "fully_informed_actions": actions,
                "fully_informed_distance": distance,
            }
        )
    old_targets = [
        [s["target"] for s in task["stages"]] for task in original["tasks"].values()
    ]
    new_targets = [
        [s["target"] for s in task["stages"]] for task in design["tasks"].values()
    ]
    return {
        "kind": "orcia_conditional_interface_route_review_only",
        "model_calls": 0,
        "is_not_a_model_score": True,
        "production_maps_changed": False,
        "geography_unchanged": True,
        "geography_sha256": sha256(
            json.dumps(geography(authored["public"]), sort_keys=True).encode()
        ).hexdigest(),
        "targets_unchanged": old_targets == new_targets,
        "physical_stations": len(all_stations),
        "useful_given_a_known_valid_type_path": len(known_path_coverage),
        "without_known_path_utility": sorted(all_stations - known_path_coverage),
        "on_a_fully_informed_shortest_path": len(oracle_coverage),
        "strictly_required_on_a_fully_informed_shortest_path": len(strict_oracle),
        "maximum_fully_informed_actions": max(
            row["fully_informed_actions"] for row in rows
        ),
        "tasks": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a new immutable review name")
    original = json.loads(
        (PROJECT / "memorybenchmark/data/orcia_hard36.json").read_text(encoding="utf-8")
    )
    result = assess(json.loads(args.design.read_text(encoding="utf-8")), original)
    result["design_sha256"] = sha256(args.design.read_bytes()).hexdigest()
    result["tool_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode()
    )
    print(json.dumps({k: v for k, v in result.items() if k != "tasks"}))


if __name__ == "__main__":
    main()
