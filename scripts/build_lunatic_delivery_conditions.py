"""Build and play a Scandinavia delivery-condition candidate without a model."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import execute, plans, score
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.assess_binding_geometry import geography, inspect_routes
from scripts.build_hard_calibration import validate


DESIGN_ID = "lunatic-01-v4.4-delivery-conditions20"
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "memorybenchmark/data/calibration/scandinavia_lunatic_goal_switch64.json"
)
MATERIALS = ("lithology", "water_quality", "shore", "drainage")
STANDARDS = ("standard-1", "standard-2")
CONDITIONS = ("湿季转运", "寒季转运")


def build():
    source = SOURCE.read_bytes()
    design = json.loads(source)
    original_tasks = design["tasks"]
    templates = {}
    for task in original_tasks.values():
        for stage in task["stages"]:
            current = item(stage)
            scope = current.input_format if current.mode == "verify" else current.goal
            templates.setdefault((current.material, current.mode, scope), stage)

    table = design["private_interfaces"]
    table["format_conditions"] = {}
    for index, material in enumerate(MATERIALS):
        formats = table["formats"][material]
        labels = CONDITIONS if index % 2 == 0 else CONDITIONS[::-1]
        table["format_conditions"][material] = dict(zip(formats, labels, strict=True))
        for fmt in formats:
            first, second = [
                row
                for row in table["verifiers"]
                if row["material"] == material and row["input"] == fmt
            ]
            second["output"] = next(
                goal for goal in STANDARDS if goal != first["output"]
            )

    # Standalone catalogue and verify tasks disclose one entry at a time. Their
    # outcomes, rather than a private assignment or a lesson, supply both facts.
    ordinary = []
    for format_index in range(2):
        for material in MATERIALS:
            fmt = table["formats"][material][format_index]
            ordinary.append(templates[material, "catalogue", fmt])
        for goal in STANDARDS:
            for material in MATERIALS:
                fmt = table["formats"][material][format_index]
                ordinary.append({**templates[material, "verify", fmt], "goal": goal})

    combined = [
        {**templates[material, "combined", goal], "delivery_condition": condition}
        for goal in STANDARDS
        for condition in CONDITIONS
        for material in MATERIALS
    ]
    tasks = {}
    stages = ordinary + combined
    for number, (first, second) in enumerate(
        zip(stages[::2], stages[1::2], strict=True), 1
    ):
        template = original_tasks[f"T{number}"]
        tasks[f"T{number}"] = {
            "name": f"全域测绘委托 {number:02d}",
            **{key: template[key] for key in ("start", "submit_at", "max_steps")},
            **first,
            "stages": [first, second],
        }
    design.update(
        design_id=DESIGN_ID,
        status="delivery_conditions_candidate_pending_native_calibration",
        fixed_world=f"{design['fixed_world']}-delivery-conditions",
        tasks=tasks,
        evaluation={"calibration_only": True},
        provenance={
            "source_design": design["design_id"],
            "source_design_sha256": sha256(source).hexdigest(),
            "reviewed_materials": list(MATERIALS),
        },
    )
    design["public"]["version"] = DESIGN_ID
    design["public"]["rules"].append(
        "有交付条件的委托要求标准和条件同时符合。编目产物有自己的适用条件，"
        "核验保留该条件并产出标准。实际处理反馈只显示本份产物的条件。"
    )
    return design


def assess(design):
    original = json.loads(SOURCE.read_bytes())
    if geography(design["public"]) != geography(original["public"]):
        raise ValueError("Review this candidate on the original Scandinavia geography")

    engine = world(design)
    by_goal = defaultdict(list)
    for task in design["tasks"].values():
        for stage in task["stages"]:
            current = item(stage)
            if current.mode == "combined":
                by_goal[current.material, current.goal].append(stage)
    wrong_condition_routes = 0
    for first, second in by_goal.values():
        left, right = item(first), item(second)
        if first["target"] != second["target"] or {
            first["delivery_condition"],
            second["delivery_condition"],
        } != set(CONDITIONS):
            raise ValueError(
                "Compare the two distinct condition routes at one survey point"
            )
        for required, alternate in ((left, right), (right, left)):
            for route in plans(engine, alternate):
                success, outcomes = execute(engine, required, route)
                if (
                    success
                    or outcomes[-1].output_format != required.goal
                    or any(outcome.result != "processed" for outcome in outcomes)
                    or score(engine, required, outcomes)["whole_stage_first_correct"]
                ):
                    raise ValueError(
                        "An alternate chain must meet the standard and fail the condition"
                    )
                wrong_condition_routes += 1

    routes = inspect_routes(design)
    proof = validate(design)
    if (
        proof["successes"] != len(design["tasks"])
        or not proof["actual_prior_feedback_for_every_combined_operation"]
    ):
        raise ValueError("Ordinary game feedback must support each composed route")
    return {
        "design_id": DESIGN_ID,
        "matched_condition_pairs": len(by_goal),
        "conditioned_stages": sum(map(len, by_goal.values())),
        "valid_standard_wrong_condition_type_routes": wrong_condition_routes,
        "physical_stations": routes["physical_stations"],
        "maximum_fully_informed_actions": routes["maximum_fully_informed_actions"],
        **proof,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    design = build()
    assessment = assess(design)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(design, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(assessment, ensure_ascii=True))


if __name__ == "__main__":
    main()
