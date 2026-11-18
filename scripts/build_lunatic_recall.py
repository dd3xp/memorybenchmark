"""Author and check one region-free Lunatic map at a time."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from random import Random

from memorybenchmark.prototypes.composition_lab import execute, plans, stage
from memorybenchmark.prototypes.station_interfaces import PROTOCOL, item, world
from scripts.assess_binding_geometry import inspect_routes
from scripts.build_hard_calibration import validate


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "memorybenchmark/data"
POLICY = ROOT / "config/lunatic-recall.json"
FORMATS = ("F-1", "F-2")
STANDARDS = ("standard-1", "standard-2")


def interface_table(material_pairs, station_types, rng):
    """Publish the same labels across materials while reversing their bindings."""
    types = list(station_types)
    rng.shuffle(types)
    catalogue_types, verify_types = types[:12], types[12:]
    table = {
        "formats": {material: FORMATS for pair in material_pairs for material in pair},
        "cataloguers": [],
        "verifiers": [],
        "alternatives_per_goal": 2,
        "enforce_interface": True,
    }
    for index, pair in enumerate(material_pairs):
        standards = list(STANDARDS)
        rng.shuffle(standards)
        for material in pair:
            for slot in range(4):
                fmt = FORMATS[slot // 2]
                table["cataloguers"].append(
                    {
                        "material": material,
                        "type": catalogue_types[(2 * index + slot) % 12],
                        "output": fmt,
                    }
                )
                table["verifiers"].append(
                    {
                        "material": material,
                        "type": verify_types[(2 * index + slot) % 12],
                        "input": fmt,
                        "output": standards[slot // 2],
                    }
                )
            standards.reverse()
    return table


def commission(template, number, pair):
    stages = [
        {
            "target": original["target"],
            "required_kind": current.material,
            "requirement": "catalogue" if current.mode == "catalogue" else "verify",
            "input_state": "catalogued" if current.mode == "verify" else "raw",
            "output_state": "catalogued" if current.mode == "catalogue" else "verified",
            "input_format": current.input_format,
            "goal": current.goal,
        }
        for original, current in zip(template["stages"], pair, strict=True)
    ]
    return {
        "name": f"全域测绘委托 {number:02d}",
        "start": template["start"],
        "submit_at": template["submit_at"],
        "max_steps": template["max_steps"],
        **stages[0],
        "stages": stages,
    }


def curriculum(design, templates, material_pairs, rng):
    engine = world(design)
    contrast_pairs = [
        ((a, goal), (b, goal)) for a, b in material_pairs for goal in STANDARDS
    ]
    rng.shuffle(contrast_pairs)
    sequence = []
    for first, second in contrast_pairs:
        sequence.extend(
            (
                (stage(engine, first, "catalogue"), stage(engine, second, "verify")),
                (stage(engine, second, "catalogue"), stage(engine, first, "verify")),
            )
        )
    sequence.extend(
        tuple(stage(engine, case, "combined") for case in pair)
        for pair in contrast_pairs
    )
    sequence.extend(
        tuple(stage(engine, case, "combined") for case in reversed(pair))
        for pair in contrast_pairs
    )
    return {
        f"T{number}": commission(template, number, pair)
        for number, (template, pair) in enumerate(
            zip(templates, sequence, strict=True), 1
        )
    }


def assess_recall(design):
    """Check alternate bindings and the gap since both needed outcomes."""
    engine = world(design)
    observed_at = {}
    gaps = []
    conflicting_paths = 0
    for number, task in enumerate(design["tasks"].values(), 1):
        first, second = map(item, task["stages"])
        if first.mode != "combined":
            for current in (first, second):
                observed_at[current.material, current.goal] = number
            continue
        for current, other in ((first, second), (second, first)):
            required = stage(engine, (current.material, current.goal), "catalogue")
            key = current.material, current.goal
            gaps.append(
                number
                - max(observed_at[key], observed_at[required.material, required.goal])
            )
            for path in plans(engine, other):
                success, outcomes = execute(engine, current, path)
                if success or outcomes[-1].result != "processed":
                    raise ValueError(
                        "A paired rule must work locally and produce the other standard"
                    )
                conflicting_paths += 1
            observed_at[key] = number
    return {
        "combined_stages": len(gaps),
        "shortest_prior_experience_gap_tasks": min(gaps),
        "similar_material_paths_producing_wrong_standard": conflicting_paths,
    }


def build(theme):
    spec = json.loads(POLICY.read_bytes())["maps"][theme]
    source = (DATA / f"{theme}_lunatic64.json").read_bytes()
    design = json.loads(source)
    public = design["public"]
    if len(public["kinds"]) != 16 or len(public["station_types"]) != 24:
        raise ValueError("Review this landscape's material and station inventory")
    rng = Random(spec["seed"])
    kinds = tuple(public["kinds"])
    pairings = list(zip(kinds[::2], kinds[1::2], strict=True))
    version = design["design_id"].split("-v")[0] + "-v4.0"
    design.update(
        design_id=version,
        status="authored_recall_lunatic_pending_native_calibration",
        world_generator="fixed_interface_station_sets",
        fixed_world=f"lunatic-recall-{spec['seed']}",
        private_interfaces=interface_table(pairings, public["station_types"], rng),
    )
    design.pop("private_station_capabilities")
    design["presentation"].pop("regions")
    public.pop("processing_regions")
    for place in public["locations"].values():
        place.pop("region_category")
    public.update(version=version, processing_model=PROTOCOL)
    public["rules"] = [
        "道路权重是实验距离。逐点移动，过水连接已标明。连接线交叉处不能中途换乘。",
        "每项委托两段独立。到本段指定测绘点主动 survey，处理至本段目标。两段完成后返回营地 submit。",
        "同型站等价，处理能力由当前资料及其输入规格决定。所有处理站均可前往。",
        "编目把原始资料变为中间规格；核验接受特定中间规格并产出标准。相同规格与标准代号可以用于不同资料。",
        "process 只反馈本站对当前样本的输入、输出及成败。失败保留样本；返回本段采集点重新 survey 可恢复起始状态，原尝试和距离照计。",
        "优先减少总路程。同一任务的两段各自采集，不共享处理产物。只有你自主保存的持久记忆可以跨任务。",
    ]
    design["tasks"] = curriculum(design, list(design["tasks"].values()), pairings, rng)
    design["evaluation"] = {
        "experience_protocol": "station-interface-opportunity-1",
        "planned_exposure_is_not_actual_learning": True,
        "allocation": assess_recall(design),
    }
    transitions = spec["transit_stations"]
    if transitions:
        before = inspect_routes(design)
        if not transitions.keys() <= set(before["without_known_path_utility"]):
            raise ValueError(
                "A removed station still serves a shortest compatible route"
            )
        for station in transitions:
            place = public["locations"][station]
            station_type = place.pop("station_type")
            public["station_types"][station_type]["stations"].remove(station)
            place.update(kind="junction", transit=True, name=f"路标 {station}")
        if inspect_routes(design)["tasks"] != before["tasks"]:
            raise ValueError("Station changes altered the fully informed routes")
    design["provenance"]["recall_revision"] = {
        "original_design_sha256": sha256(source).hexdigest(),
        "world_seed": spec["seed"],
        "former_stations_now_transit": transitions,
        "survey_and_road_geometry_preserved": True,
    }
    return design


def assess_goal_switch(design):
    """Check that the other known route for a material yields the wrong goal."""
    engine = world(design)
    goals_by_material = defaultdict(set)
    for task in design["tasks"].values():
        for raw_stage in task["stages"]:
            current = item(raw_stage)
            if current.mode == "combined":
                goals_by_material[current.material].add(current.goal)
    dual_goals = {
        material: goals
        for material, goals in goals_by_material.items()
        if len(goals) == 2
    }
    conflicting_paths = 0
    for material, goals in sorted(dual_goals.items()):
        first, second = sorted(goals)
        for goal, other in ((first, second), (second, first)):
            current = stage(engine, (material, goal), "combined")
            alternate = stage(engine, (material, other), "combined")
            for route in plans(engine, alternate):
                success, outcomes = execute(engine, current, route)
                if success or outcomes[-1].output_format != other:
                    raise ValueError("Both known routes must lead to their own goal")
                conflicting_paths += 1
    if len(dual_goals) != 4 or conflicting_paths == 0:
        raise ValueError("The goal-switch pilot needs two standards on four materials")
    return {
        "materials_with_two_combined_goals": sorted(dual_goals),
        "same_material_paths_producing_the_other_standard": conflicting_paths,
    }


def pilot(design, *, goal_switch=False):
    """Keep the actual prerequisite commissions for both sides of each contrast."""
    config = json.loads(POLICY.read_bytes())
    if (
        design["design_id"] != "lunatic-01-v4.0"
        or design["provenance"]["recall_revision"]["world_seed"]
        != config["maps"]["scandinavia"]["seed"]
    ):
        raise ValueError("The pilots use the reviewed Scandinavia candidate")
    if goal_switch:
        ids = config["scandinavia_goal_switch_tasks"]
        version = "lunatic-01-v4.1-goal-switch-pilot18"
        task_count, combined_stages = 18, 12
    else:
        ids = config["scandinavia_pilot_tasks"]
        version = "lunatic-01-v4.0-pilot12"
        task_count, combined_stages = 12, 8
    if len(ids) != task_count or len(set(ids)) != task_count:
        raise ValueError("A pilot must select the reviewed distinct commissions")
    selected = [design["tasks"][key] for key in ids]
    pilot_design = {
        **design,
        "design_id": version,
        "public": {**design["public"], "version": version},
        "tasks": {
            f"T{i}": {**task, "name": f"全域测绘委托 {i:02d}"}
            for i, task in enumerate(selected, 1)
        },
        "provenance": {
            **design["provenance"],
            "pilot_from_tasks": ids,
        },
    }
    allocation = assess_recall(pilot_design)
    if allocation["combined_stages"] != combined_stages:
        raise ValueError("A pilot must have the reviewed number of combined stages")
    if goal_switch:
        allocation.update(assess_goal_switch(pilot_design))
    pilot_design["evaluation"] = {
        **design["evaluation"],
        "allocation": allocation,
    }
    return pilot_design


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map", choices=("scandinavia", "mongolia", "andes"), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--routes-only", action="store_true")
    variants = parser.add_mutually_exclusive_group()
    variants.add_argument("--pilot", action="store_true")
    variants.add_argument("--goal-switch-pilot", action="store_true")
    args = parser.parse_args()
    design = build(args.map)
    if args.pilot or args.goal_switch_pilot:
        design = pilot(design, goal_switch=args.goal_switch_pilot)
    routes = inspect_routes(design)
    summary = {
        "design_id": design["design_id"],
        **design["evaluation"]["allocation"],
        **{key: value for key, value in routes.items() if key != "tasks"},
    }
    if not args.routes_only:
        proof = validate(design)
        if (
            proof["successes"] != len(design["tasks"])
            or not proof["actual_prior_feedback_for_every_combined_operation"]
        ):
            raise ValueError("Prior game feedback did not support the full curriculum")
        summary.update(proof)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(design, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
