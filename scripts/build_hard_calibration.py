"""Build a bounded candidate pilot, then exercise the real game without a model."""

import argparse
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import (
    build_world,
    commissions,
    assess_allocation,
    plans,
    DeliveredMemory,
    Outcome,
)
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    map_world,
    load_design,
)
from memorybenchmark.prototypes.station_interfaces import PROTOCOL, item, load, world
from memorybenchmark.prototypes.station_routes import shortest_route, walk
from scripts.assess_hard_interfaces import review_orcia_targets
from memorybenchmark.prototypes.interface_curriculum import (
    binding_world,
    once_commissions,
    check_once_allocation,
    pilot_materials,
    balanced_commissions,
    check_balanced_allocation,
)


PROJECT = Path(__file__).resolve().parents[1]


def build(
    seed=None,
    selected_materials=None,
    *,
    variant="interface",
    full=False,
    curriculum="once",
):
    if variant not in ("interface", "binding"):
        raise ValueError("Unknown candidate variant")
    if curriculum not in ("once", "balanced-three") or (
        curriculum == "balanced-three"
        and (variant != "binding" or not full or selected_materials is not None)
    ):
        raise ValueError("Balanced-three is a complete retained binding candidate")
    seed = seed if seed is not None else (61301 if variant == "interface" else 61401)
    source = PROJECT / "memorybenchmark/data/orcia_hard36.json"
    authored = json.loads(source.read_text(encoding="utf-8"))
    design = deepcopy(authored)
    original_world = (
        build_world(seed)
        if variant == "interface"
        else binding_world(
            seed, material_count=8 if curriculum == "balanced-three" else 12
        )
    )
    if selected_materials is None:
        selected_materials = (
            original_world.materials[:2]
            if variant == "interface"
            else pilot_materials(original_world)
        )
    if full:
        selected_materials = original_world.materials
    sequence = (
        commissions(original_world, selected_materials)
        if variant == "interface"
        else (
            balanced_commissions(original_world)
            if curriculum == "balanced-three"
            else once_commissions(original_world, selected_materials)
        )
    )
    allocation = (
        assess_allocation(original_world, sequence)
        if variant == "interface"
        else (
            check_balanced_allocation(original_world, sequence)
            if curriculum == "balanced-three"
            else check_once_allocation(original_world, sequence)
        )
    )
    if len(sequence) != (36 if full else 12):
        raise ValueError(
            "Select the bounded twelve-task pilot or the unlaunched 36-task full candidate"
        )
    profile_to_type = {
        f"P{i+1:02d}": name
        for i, name in enumerate(sorted(design["public"]["station_types"]))
    }
    table = {
        "formats": original_world.formats,
        "cataloguers": [
            {"material": m, "type": profile_to_type[s], "output": value}
            for (m, s), value in original_world.cataloguers.items()
        ],
        "verifiers": [
            {
                "material": m,
                "type": profile_to_type[s],
                "input": value[0],
                "output": value[1],
            }
            for (m, s), value in original_world.verifiers.items()
        ],
        "enforce_interface": True,
    }
    if variant == "binding":
        table["alternatives_per_goal"] = 2
    version = (
        3 if curriculum == "balanced-three" else 1 if variant == "interface" else 2
    )
    design_id = f"hard-{variant}-calibration-v{version}-{seed}-{len(sequence)}"
    design.update(
        design_id=design_id,
        world_generator="fixed_interface_station_sets",
        fixed_world=f"interfaces-{seed}",
        private_interfaces=table,
    )
    for key in ("private_worlds", "private_station_capabilities", "material_selection"):
        design.pop(key, None)
    public = design["public"]
    public.update(
        version=design_id,
        processing_model=PROTOCOL,
        kinds=dict(zip(original_world.materials, authored["public"]["kinds"].values())),
        station_query_enabled=False,
        manual_survey_required=True,
    )
    public["rules"] = [
        "每项委托两段独立，每段到目标survey采集规定的起始资料；达到本段交付规格才推进，全部完成后回营地submit。",
        "同型站功能等价且固定。全部站型均是候选，具体输入输出由实际process获知，站名不暗示能力。",
        "编目将原始资料转成某种中间规格；核验接受特定规格并产出特定标准。process只反馈本站本份样本的输入、输出和成败，不揭示完整能力列表。",
        "处理失败保留样本。可回本段采集点再次survey丢弃现有样本并取得本段原始起始资料，原尝试和路程仍计入。",
        "未来委托与私有配对不会提前提供。只有Agent自主保存的原生记忆可以跨会话传递。",
    ]
    if variant == "binding":
        public["rules"].append(
            "相同规格代号可在不同资料中重复；同型站对相同资料和输入的结果固定，但对其他资料的输出或核验能力可能不同，不能直接套用。"
        )
        targets = [
            {"targets": [s["target"] for s in t["stages"]]}
            for t in authored["tasks"].values()
        ]
    else:
        targets = review_orcia_targets(load_design(source), seed, 2000)["tasks"]
    tasks = {}
    originals = list(authored["tasks"].values())
    for number, pair in enumerate(sequence):
        stages = []
        for index, stage in enumerate(pair):
            stages.append(
                {
                    "target": targets[number]["targets"][index],
                    "required_kind": stage.material,
                    "requirement": (
                        "catalogue" if stage.mode == "catalogue" else "verify"
                    ),
                    "input_state": "catalogued" if stage.mode == "verify" else "raw",
                    "output_state": (
                        "catalogued" if stage.mode == "catalogue" else "verified"
                    ),
                    "input_format": stage.input_format,
                    "goal": stage.goal,
                }
            )
        tasks[f"T{number+1}"] = {
            "name": f"资料采集与交付 {number+1:02d}",
            "start": originals[number]["start"],
            "submit_at": originals[number]["submit_at"],
            **stages[0],
            "stages": stages,
            "max_steps": 352,
        }
    design["tasks"] = tasks
    design["evaluation"] = {
        "experience_protocol": "station-interface-opportunity-1",
        "allocation": allocation,
        "planned_exposure_is_not_actual_learning": True,
        "calibration_only": True,
    }
    design["provenance"]["interface_candidate"] = {
        "base_sha256": sha256(source.read_bytes()).hexdigest(),
        "seed": seed,
        "selected_materials": list(selected_materials),
        "original_geography_unchanged": True,
        "ordinary_scored_tasks_only": True,
        "stage_dependency": False,
    }
    design["native_session_budget"].update(
        main_model_calls=400,
        reasoning_effort="high",
        whole_session_transport_retries=0,
        whole_session_failure_limit=0,
    )
    return design


def validate(design, *, checkpoint_observer=None):
    design = load(deepcopy(design))
    game = StationGame(map_world(design), design)
    maximum = 0
    memory = DeliveredMemory()
    completed = []
    for task_id, task in design["tasks"].items():
        game.start_task(task_id)
        for index, stage in enumerate(task["stages"]):
            walk(game, stage["target"])
            game.step({"type": "survey"})
            destination = (
                task["stages"][index + 1]["target"]
                if index + 1 < len(task["stages"])
                else task["submit_at"]
            )
            choices = []
            if item(stage).mode == "combined":
                known = memory.compatible_plan(item(stage))
                if known is None:
                    raise AssertionError(
                        "The completed ordinary prefix did not deliver a compatible plan"
                    )
                profile_plans = [known]
            else:
                profile_plans = plans(world(design), item(stage))
            for profile_plan in profile_plans:
                for stations in product(
                    *(
                        design["public"]["station_types"][p]["stations"]
                        for p in profile_plan
                    )
                ):
                    stops = (stage["target"], *stations, destination)
                    choices.append(
                        (
                            sum(
                                shortest_route(design, a, b)[1]
                                for a, b in zip(stops, stops[1:])
                            ),
                            stations,
                        )
                    )
            for station in min(choices)[1]:
                walk(game, station)
                feedback = game.step({"type": "process"})["feedback"]
                memory.observe(
                    [
                        Outcome(
                            feedback["station_type"],
                            feedback["required_kind"],
                            feedback["requirement"],
                            feedback["input_format"],
                            feedback["output_format"],
                            feedback["result"],
                        )
                    ]
                )
        walk(game, task["submit_at"])
        game.step({"type": "submit"})
        if not game.state.success:
            raise AssertionError("Reference cannot complete the candidate task")
        maximum = max(maximum, game.steps)
        completed.append({"task_id": task_id, "success": game.state.success})
        if checkpoint_observer is not None:
            checkpoint_observer(
                {"sessions": completed, "tasks": list(design["tasks"])}, game
            )
    from memorybenchmark.prototypes.station_analysis import analyze_trace

    rows = [
        analyze_trace(design, game.events, f"session-{i+1}", exact_references=False)
        for i in range(len(design["tasks"]))
    ]
    return {
        "zero_model_game_tasks": len(rows),
        "successes": sum(r["success"] for r in rows),
        "maximum_reference_actions": maximum,
        "required_operations": sum(r["necessary_operation_denominator"] for r in rows),
        "actual_prior_feedback_for_every_combined_operation": all(
            r["prior_matching_feedback"]
            for row in rows
            for r in row["processing_operations"]
            if r["composition"]
        ),
        "native_model_calls": 0,
        "is_not_a_model_score": True,
        "combined_reference_uses_only_delivered_prior_interface_facts": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--variant", choices=("interface", "binding"), default="interface"
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Candidate source is immutable after writing")
    design = build(args.seed, variant=args.variant, full=args.full)
    proof = validate(design)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(design, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    args.output.with_suffix(".assessment.json").write_bytes(
        (json.dumps(proof, indent=2) + "\n").encode("utf-8")
    )
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
