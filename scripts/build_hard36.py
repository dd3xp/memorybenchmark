"""Build and assess one Hard geography at a time, without model outcomes."""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import random

from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_composition import (
    PROTOCOL,
    requirements,
    validate_allocation,
    active_requirement,
)
from memorybenchmark.prototypes.station_routes import shortest_route, walk

THEMES = {
    "orcia": ("hard-01", 61301),
    "hampi": ("hard-02", 61302),
    "angkor": ("hard-03", 61303),
}


def processing_stations(design, stage, operation):
    world = design["private_worlds"][map_world(design)]
    return [s for s in world if stage["required_kind"] in world[s][operation]]


def best_stage(design, stage, destination):
    choices = [
        processing_stations(design, stage, operation)
        for operation in requirements(stage)
    ]
    candidates = []
    for stations in product(*choices):
        nodes = (stage["target"], *stations, destination)
        distance = sum(
            shortest_route(design, a, b)[1] for a, b in zip(nodes, nodes[1:])
        )
        candidates.append((distance, stations))
    best = min(d for d, _ in candidates)
    return best, [stations for d, stations in candidates if d == best]


def route_utility(design):
    useful = set()
    for task in design["tasks"].values():
        for i, stage in enumerate(task["stages"]):
            destination = (
                task["stages"][i + 1]["target"]
                if i + 1 < len(task["stages"])
                else task["submit_at"]
            )
            _, plans = best_stage(design, stage, destination)
            for index in range(len(plans[0])):
                stations = {p[index] for p in plans}
                if len(stations) == 1:
                    useful.update(stations)
    return useful


def assign_targets(design, seed):
    rng = random.Random(seed)
    targets = [
        n for n, p in design["public"]["locations"].items() if p["kind"] == "survey"
    ]
    stages = [s for t in design["tasks"].values() for s in t["stages"]]
    pool = (targets * 5)[: len(stages)]
    rng.shuffle(pool)
    for stage, target in zip(stages, pool):
        stage["target"] = target
    best = route_utility(design)
    accepted = 0
    for iteration in range(6000):
        if len(best) == 48:
            break
        a, b = rng.sample(range(len(stages)), 2)
        stages[a]["target"], stages[b]["target"] = (
            stages[b]["target"],
            stages[a]["target"],
        )
        candidate = route_utility(design)
        if len(candidate) > len(best) or (
            len(candidate) == len(best) and rng.random() < 0.025
        ):
            best = candidate
            accepted += 1
        else:
            stages[a]["target"], stages[b]["target"] = (
                stages[b]["target"],
                stages[a]["target"],
            )
    for task in design["tasks"].values():
        task.update(task["stages"][0])
    return {
        "unique_shortest_route_useful_stations": len(best),
        "unused_stations": sorted(
            set(
                s
                for s, p in design["public"]["locations"].items()
                if p["kind"] == "station"
            )
            - best
        ),
        "target_swaps_accepted": accepted,
        "geometry_changed": False,
        "model_results_used": False,
    }


def build(theme):
    root = (
        Path(__file__).resolve().parents[1]
        if Path(__file__).parent.name == "scripts"
        else Path.cwd()
    )
    base = root / "memorybenchmark/data" / f"{theme}_hard48.json"
    authored = json.loads(base.read_text(encoding="utf-8-sig"))
    d = deepcopy(authored)
    policy = json.loads((root / "config/hard36.json").read_text(encoding="utf-8"))
    if (
        policy["tasks"],
        policy["materials"],
        policy["stages_per_task"],
        policy["standalone_uses_per_operation"],
        policy["combined_uses_per_operation"],
    ) != (36, 12, 2, 2, 2):
        raise ValueError("This builder implements only the reviewed Hard36 allocation")
    prefix = policy["maps"][theme]["design_prefix"]
    seed = policy["maps"][theme]["target_seed"]
    offsets = policy["standalone_partner_offsets"]
    d["design_id"] = prefix + "-v5.0-composition36"
    d["public"].update(version=d["design_id"], processing_model=PROTOCOL)
    d["public"]["rules"] += [
        "资料具有原始、已编目、已核验状态。归档编目：原始→已编目；关联核验：已编目→已核验。",
        "每段公开给出采集所得资料状态和最终交付目标。process按当前资料状态执行下一种操作；得到中间产物时本段尚未完成。",
        "两段资料相互独立。已编目资料可直接作为采集所得输入；普通委托也可只要求交付已编目资料。所有任务都正常计分。",
    ]
    kinds = list(d["public"]["kinds"])

    def stage(kind, mode):
        initial, goal = {
            "a": ("raw", "catalogued"),
            "b": ("catalogued", "verified"),
            "ab": ("raw", "verified"),
        }[mode]
        return {
            "target": "",
            "required_kind": kind,
            "requirement": "catalogue" if mode == "a" else "verify",
            "input_state": initial,
            "output_state": goal,
        }

    tasks = {}
    for block in range(3):
        for i, kind in enumerate(kinds):
            if block == 0:
                stages = [stage(kind, "a"), stage(kinds[(i + offsets[0]) % 12], "b")]
            elif block == 1:
                stages = [stage(kind, "ab"), stage(kinds[(i + offsets[1]) % 12], "a")]
            else:
                stages = [stage(kinds[(i + offsets[2]) % 12], "b"), stage(kind, "ab")]
            name = f"T{len(tasks)+1}"
            tasks[name] = {
                "name": f"资料采集与交付 {len(tasks)+1:02d}",
                "start": "C",
                "submit_at": "C",
                **stages[0],
                "stages": stages,
                "max_steps": 352,
            }
    d["tasks"] = tasks
    d["evaluation"].update(
        experience_protocol="station-composition-opportunity-1",
        planned_use_unit="material x basic operation",
        planned_uses=4,
        first_use_in_earlier_normal_standalone_task=True,
    )
    d["provenance"]["composition_authoring"] = {
        "base_sha256": sha256(base.read_bytes()).hexdigest(),
        "seed": seed,
        "user_decision": "Hard36: 2 standalone + 2 combined uses per basic experience",
        "teaching_tasks": 0,
        "stage_dependency": False,
        "geometry_changed": False,
    }
    # Load the unchanged capability fixture before assigning task geography.
    from memorybenchmark.prototypes.station_capability import (
        _load_conditional_capabilities,
    )

    # The loader also validates targets, so start with a real measurement node.
    target = next(
        n for n, p in d["public"]["locations"].items() if p["kind"] == "survey"
    )
    for task in tasks.values():
        for s in task["stages"]:
            s["target"] = target
        task.update(task["stages"][0])
    d = _load_conditional_capabilities(d)
    utility = assign_targets(d, seed)
    allocation = validate_allocation(d)
    return d, {"allocation": allocation, "geography": utility, "base_file": base.name}


def validate_games(design):
    game = StationGame(map_world(design), design)
    maximum = 0
    for task_id, task in design["tasks"].items():
        game.start_task(task_id)
        for i, stage in enumerate(task["stages"]):
            walk(game, stage["target"])
            game.step({"type": "survey"})
            destination = (
                task["stages"][i + 1]["target"]
                if i + 1 < len(task["stages"])
                else task["submit_at"]
            )
            _, plans = best_stage(design, stage, destination)
            for station in plans[0]:
                walk(game, station)
                game.step({"type": "process"})
        walk(game, task["submit_at"])
        game.step({"type": "submit"})
        if not game.state.success:
            raise AssertionError(f"{task_id} exceeds its original budget")
        maximum = max(maximum, game.steps)
    return {
        "zero_model_tasks": len(design["tasks"]),
        "successes": 36,
        "maximum_reference_operations": maximum,
        "reference_is_not_agent_performance": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=tuple(THEMES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    d, assessment = build(args.map)
    assessment["feasibility"] = validate_games(d)
    if assessment["geography"]["unused_stations"]:
        raise ValueError(
            "Assess this map separately: some stations have no strict route utility"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    d.pop("private_worlds", None)
    args.output.write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_suffix(".assessment.json").write_text(
        json.dumps(assessment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"map": args.map, **assessment}, ensure_ascii=False))


if __name__ == "__main__":
    main()
