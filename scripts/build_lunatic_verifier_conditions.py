"""Build and verify a candidate with verifier-specific delivery conditions."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import execute, plans, score
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.assess_binding_geometry import geography, inspect_routes
from scripts.build_hard_calibration import validate
from scripts.build_lunatic_delivery_conditions import CONDITIONS, MATERIALS, STANDARDS


DESIGN_ID = "lunatic-01-v4.5-verifier-conditions20"
ROOT = Path(__file__).resolve().parents[1] / "memorybenchmark/data/calibration"
SOURCE = ROOT / "scandinavia_lunatic_delivery_conditions20.json"
SAME_FORMAT = ("lithology", "shore")


def verifier_routes(design):
    table = design["private_interfaces"]
    del table["format_conditions"]
    conditions = {}
    table["verification_conditions"] = conditions
    routes = {}
    for material_index, material in enumerate(MATERIALS):
        formats = table["formats"][material]
        rules = [r for r in table["verifiers"] if r["material"] == material]
        if material in SAME_FORMAT:
            # Keep both existing verifiers for each format. Assign their common
            # standard so the two otherwise compatible routes differ at delivery.
            for rule in rules:
                goal_index = (formats.index(rule["input"]) + material_index // 2) % 2
                rule["output"] = STANDARDS[goal_index]
        conditions[material] = {}
        for standard_index, goal in enumerate(STANDARDS):
            choices = sorted(
                (r["input"], r["type"]) for r in rules if r["output"] == goal
            )
            labels = (
                CONDITIONS
                if (material_index + standard_index) % 2 == 0
                else CONDITIONS[::-1]
            )
            for (fmt, station), condition in zip(choices, labels, strict=True):
                conditions[material][station] = condition
                routes[material, goal, condition] = fmt
    return routes


def build():
    source = SOURCE.read_bytes()
    design = json.loads(source)
    routes = verifier_routes(design)
    exposures = Counter()
    for task in design["tasks"].values():
        for stage in task["stages"]:
            current = item(stage)
            if current.mode != "verify":
                continue
            key = current.material, current.goal
            available = sorted(
                CONDITIONS,
                key=lambda condition: (
                    routes[(*key, condition)] != current.input_format,
                    condition,
                ),
            )
            condition = next(c for c in available if not exposures[(*key, c)])
            exposures[(*key, condition)] += 1
            stage.update(
                input_format=routes[(*key, condition)], delivery_condition=condition
            )
        task.update(task["stages"][0])

    design.update(
        design_id=DESIGN_ID,
        status="verifier_conditions_candidate_pending_native_calibration",
        fixed_world=f"{design['fixed_world'].removesuffix('-delivery-conditions')}-verifier-conditions",
        provenance={
            "source_design": design["design_id"],
            "source_design_sha256": sha256(source).hexdigest(),
            "same_format_materials": list(SAME_FORMAT),
            "reviewed_materials": list(MATERIALS),
        },
    )
    design["public"]["version"] = DESIGN_ID
    design["public"]["rules"][-1] = (
        "有交付条件的委托要求标准和条件同时符合。条件由核验产物决定，"
        "相同编目格式不保证条件相同。处理反馈只显示本份产物实际取得的条件。"
    )
    return design


def assess(design):
    original = json.loads(SOURCE.read_bytes())
    if geography(design["public"]) != geography(original["public"]):
        raise ValueError("Review this candidate on the original Scandinavia geography")

    engine = world(design)
    combined = defaultdict(list)
    witnessed = set()
    for task in design["tasks"].values():
        standalone_this_task = set()
        for stage in task["stages"]:
            current = item(stage)
            key = current.material, current.goal
            if current.mode == "combined":
                if any((*key, condition) not in witnessed for condition in CONDITIONS):
                    raise ValueError("Both conditions need earlier scored verification")
                combined[key].append(stage)
            elif current.mode == "verify":
                standalone_this_task.add((*key, current.delivery_condition))
        witnessed.update(standalone_this_task)

    same_format = split_format = wrong_routes = 0
    for (material, goal), (first, second) in combined.items():
        if first["target"] != second["target"] or {
            first["delivery_condition"], second["delivery_condition"]
        } != set(CONDITIONS):
            raise ValueError("Compare both conditions at the same point and standard")
        left, right = item(first), item(second)
        for required, alternate in ((left, right), (right, left)):
            for route in plans(engine, alternate):
                success, outcomes = execute(engine, required, route)
                measurement = score(engine, required, outcomes)
                catalogue_correct, verify_correct = (
                    row["goal_compatible_first_success"]
                    for row in measurement["operations"]
                )
                if (
                    success
                    or outcomes[-1].output_format != goal
                    or any(outcome.result != "processed" for outcome in outcomes)
                    or catalogue_correct != (material in SAME_FORMAT)
                    or verify_correct
                ):
                    raise ValueError("Standard-only routes must fail the assigned condition")
                wrong_routes += 1
        if material in SAME_FORMAT:
            same_format += 1
        else:
            split_format += 1

    routes = inspect_routes(design)
    proof = validate(design)
    if (
        proof["successes"] != len(design["tasks"])
        or not proof["actual_prior_feedback_for_every_combined_operation"]
    ):
        raise ValueError("Ordinary game feedback must support each composed route")
    return {
        "design_id": DESIGN_ID,
        "matched_condition_pairs": len(combined),
        "same_format_pairs": same_format,
        "split_format_pairs": split_format,
        "valid_standard_wrong_condition_type_routes": wrong_routes,
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
