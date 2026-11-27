"""Build a matched Scandinavia candidate that removes cross-standard seal inversion."""

import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import (
    SEAL_MATCH,
    SEAL_MISMATCH,
    SEAL_RELATIONS,
    execute,
    input_for_stage,
    plans,
    score,
)
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.assess_binding_geometry import inspect_routes
from scripts.build_hard_calibration import validate
from scripts.build_lunatic_delivery_conditions import STANDARDS


DESIGN_ID = "lunatic-01-v4.7-independent-seals20"
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "memorybenchmark/data/calibration/scandinavia_lunatic_seal_comparison20.json"
)
SOURCE_SHA256 = "4c7d5f5613d0e2bb80be95ebb557cdd4be79daedd4126881bd8c88509185be06"

# Each standard keeps a common seal across the two accepted formats. Change
# only the second standard for the first material in each original pair.
# These two materials share their F-1 catalogue seal, which preserves a 2/2
# format split for each standard and relation across the four materials.
VERIFICATION_SEALS = {
    "lithology": ("甲", "甲"),
    "water_quality": ("甲", "乙"),
    "shore": ("乙", "乙"),
    "drainage": ("乙", "甲"),
}


def source_design():
    raw = SOURCE.read_bytes()
    if sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("The frozen v4.6 reference changed")
    return json.loads(raw)


def build():
    design = source_design()
    table = design["private_interfaces"]
    verifier_seals = table["seal_comparison"]["verify"]
    for rule in table["verifiers"]:
        material = rule["material"]
        if material in VERIFICATION_SEALS:
            verifier_seals[material][rule["type"]] = VERIFICATION_SEALS[material][
                STANDARDS.index(rule["output"])
            ]
    design.update(
        design_id=DESIGN_ID,
        status="independent_seals_candidate_pending_native_calibration",
        fixed_world=f"{design['fixed_world'].removesuffix('-seal-comparison')}-independent-seals",
        provenance={
            "source_design": design["design_id"],
            "source_design_sha256": SOURCE_SHA256,
            "reviewed_materials": list(VERIFICATION_SEALS),
        },
    )
    design["public"]["version"] = DESIGN_ID
    return design


def assess(design):
    original = source_design()
    if (
        list(design["tasks"]) != list(original["tasks"])
        or design["tasks"] != original["tasks"]
    ):
        raise ValueError("Keep every v4.6 commission and its order")
    if design["public"] != dict(original["public"], version=DESIGN_ID):
        raise ValueError("Keep the v4.6 map and public rules")

    engine = world(design)
    formats = Counter()
    rejected = 0
    for task in design["tasks"].values():
        for stage in task["stages"]:
            required = item(stage)
            if required.mode != "combined":
                continue
            fmt = input_for_stage(engine, required)
            formats[required.goal, required.delivery_condition, fmt] += 1
            alternate = (
                SEAL_MISMATCH
                if required.delivery_condition == SEAL_MATCH
                else SEAL_MATCH
            )
            wrong_routes = plans(
                engine, replace(required, delivery_condition=alternate)
            )
            if set(plans(engine, required)) & set(wrong_routes):
                raise ValueError("One route cannot satisfy both relations")
            for route in wrong_routes:
                completed, outcomes = execute(engine, required, route)
                if (
                    completed
                    or any(event.result != "processed" for event in outcomes)
                    or outcomes[-1].output_format != required.goal
                    or score(engine, required, outcomes)["whole_stage_first_correct"]
                ):
                    raise ValueError(
                        "A valid standard with the wrong relation must be rejected"
                    )
                rejected += 1
    if formats != {
        (goal, relation, fmt): 2
        for goal in STANDARDS
        for relation in SEAL_RELATIONS
        for fmt in ("F-1", "F-2")
    }:
        raise ValueError(
            "The required format must balance within each standard and relation"
        )

    before, after = inspect_routes(original), inspect_routes(design)
    before_distance = sum(row["fully_informed_distance"] for row in before["tasks"])
    after_distance = sum(row["fully_informed_distance"] for row in after["tasks"])
    if before_distance != after_distance:
        raise ValueError("Keep the total fully informed travel distance")
    proof = validate(design, feedback_only_repeats=True)
    if proof["feedback_only_repeat_operations_by_encounter"] != {"2": 24, "3": 8}:
        raise ValueError("Keep all 32 repeated operations supported by prior feedback")
    return {
        "design_id": DESIGN_ID,
        "source_design_sha256": SOURCE_SHA256,
        "verifier_seals_by_standard": VERIFICATION_SEALS,
        "required_formats_by_standard_and_relation": {
            goal: {
                relation: {fmt: formats[goal, relation, fmt] for fmt in ("F-1", "F-2")}
                for relation in SEAL_RELATIONS
            }
            for goal in STANDARDS
        },
        "valid_standard_wrong_relation_routes": rejected,
        "fully_informed_travel_distance_v46": before_distance,
        "fully_informed_travel_distance_v47": after_distance,
        "maximum_fully_informed_actions_v46": before["maximum_fully_informed_actions"],
        "maximum_fully_informed_actions_v47": after["maximum_fully_informed_actions"],
        **proof,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    design = build()
    proof = assess(design)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(design, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(proof, ensure_ascii=True))


if __name__ == "__main__":
    main()
