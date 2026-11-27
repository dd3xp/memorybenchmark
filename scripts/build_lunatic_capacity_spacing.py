"""Build and verify a capacity and spacing candidate from frozen Scandinavia v4.7."""

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from memorybenchmark.prototypes.composition_lab import (
    SEAL_RELATIONS,
    execute,
    experience_keys,
    input_for_stage,
    plans,
    score,
)
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.assess_binding_geometry import inspect_routes
from scripts.build_hard_calibration import validate


DESIGN_ID = "lunatic-01-v4.8-capacity-spacing30"
DATA = Path(__file__).resolve().parents[1] / "memorybenchmark/data/calibration"
SOURCE = DATA / "scandinavia_lunatic_independent_seals20.json"
SOURCE_SHA256 = "b0fbae15839a241d8dc58c53e52556e6e7cc8a3291c6c21c2ad14b56c0ded600"
SURVEY_SOURCE = DATA / "scandinavia_lunatic_goal_switch64.json"
SURVEY_SHA256 = "a7132c2da3ae92a656b7b8e441f825a95ec6c609e305bf06d48fc9460f9ae90c"
NEW_MATERIALS = {"otter_signs": "甲", "elevation": "乙"}
FORMATS = ("F-1", "F-2")
STANDARDS = ("standard-1", "standard-2")
ORDINARY_TARGETS = (
    ("v45", "v12"),
    ("v13", "v30"),
    ("v13", "v30"),
    ("v46", "v42"),
    ("v36", "v14"),
    ("v36", "v14"),
)
COMBINED_TARGETS = (("v61", "v42"), ("v57", "v41"))


def read_frozen(path, expected):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f"Unexpected frozen source bytes for {path.name}")
    return json.loads(raw)


def add_seal_facts(design):
    table = design["private_interfaces"]
    seals = table["seal_comparison"]
    for material, seal in NEW_MATERIALS.items():
        seals["catalogue"][material] = dict(zip(FORMATS, ("甲", "乙"), strict=True))
        seals["verify"][material] = {}
        for fmt in FORMATS:
            first, second = (
                rule
                for rule in table["verifiers"]
                if rule["material"] == material and rule["input"] == fmt
            )
            second["output"] = next(
                goal for goal in STANDARDS if goal != first["output"]
            )
            for rule in (first, second):
                seals["verify"][material][rule["type"]] = seal


def new_commissions():
    survey = read_frozen(SURVEY_SOURCE, SURVEY_SHA256)
    templates = {}
    for task in survey["tasks"].values():
        for stage in task["stages"]:
            current = item(stage)
            scope = current.input_format if current.mode == "verify" else current.goal
            templates[current.material, current.mode, scope, stage["target"]] = stage

    ordinary = []
    for index, fmt in enumerate(FORMATS):
        for offset, goal in enumerate((None, *STANDARDS)):
            mode = "verify" if goal else "catalogue"
            stages = [
                dict(templates[material, mode, fmt, target])
                for material, target in zip(
                    NEW_MATERIALS, ORDINARY_TARGETS[index * 3 + offset], strict=True
                )
            ]
            if goal:
                for stage in stages:
                    stage["goal"] = goal
            ordinary.append(stages)

    combined = []
    for index, goal in enumerate(STANDARDS):
        for relation_index in range(len(SEAL_RELATIONS)):
            combined.append(
                [
                    {
                        **templates[material, "combined", goal, target],
                        "delivery_condition": SEAL_RELATIONS[
                            (relation_index + position * index) % len(SEAL_RELATIONS)
                        ],
                    }
                    for position, (material, target) in enumerate(
                        zip(NEW_MATERIALS, COMBINED_TARGETS[index], strict=True)
                    )
                ]
            )
    return {
        f"T{number}": {
            "name": f"全域测绘委托 {number:02d}",
            "start": "C",
            "submit_at": "C",
            "max_steps": 352,
            **stages[0],
            "stages": stages,
        }
        for number, stages in enumerate(ordinary + combined, 21)
    }


def build():
    design = read_frozen(SOURCE, SOURCE_SHA256)
    add_seal_facts(design)
    new = new_commissions()
    original = list(design["tasks"].items())
    design["tasks"] = dict(
        commission
        for index, (left, right) in enumerate(
            zip(original[::2], original[1::2], strict=True), 21
        )
        for commission in (left, right, (f"T{index}", new[f"T{index}"]))
    )
    design.update(
        design_id=DESIGN_ID,
        status="capacity_spacing_candidate_pending_native_calibration",
        fixed_world=f"{design['fixed_world']}-capacity-spacing",
        provenance={
            "source_design": design["design_id"],
            "source_design_sha256": SOURCE_SHA256,
            "survey_source_sha256": SURVEY_SHA256,
            "added_materials": list(NEW_MATERIALS),
        },
    )
    design["public"]["version"] = DESIGN_ID
    return design


def ordinary_effect(key):
    material, operation, *_ = key
    if operation == "catalogue":
        return material, operation
    return material, operation, key[3]


def exposure_gaps(design):
    engine = world(design)
    exact, ordinary, raw_seal = {}, {}, {}
    gaps = defaultdict(Counter)
    for ordinal, task in enumerate(design["tasks"].values(), 1):
        stages = [(item(s), experience_keys(item(s), engine)) for s in task["stages"]]
        for current, keys in stages:
            if current.mode == "combined":
                gaps["nearest_exact"][min(ordinal - exact[k] for k in keys)] += 1
                gaps["nearest_ordinary"][min(ordinal - ordinary[k] for k in keys)] += 1
                gaps["nearest_raw_seal"][
                    min(ordinal - raw_seal[ordinary_effect(k)] for k in keys)
                ] += 1
        for current, keys in stages:
            for key in keys:
                exact[key] = ordinal
                raw_seal[ordinary_effect(key)] = ordinal
                if current.mode != "combined":
                    ordinary[key] = ordinal
    return gaps


def assess(design):
    source = read_frozen(SOURCE, SOURCE_SHA256)
    if design["public"] != dict(source["public"], version=DESIGN_ID):
        raise ValueError("Keep the frozen v4.7 map, routes and public rules")
    retained = {
        key: task for key, task in design["tasks"].items() if key in source["tasks"]
    }
    if retained != source["tasks"] or tuple(retained) != tuple(source["tasks"]):
        raise ValueError("Keep all original task/stage bytes and their relative order")

    engine = world(design)
    pairs = defaultdict(list)
    format_counts, relation_counts, raw_counts = Counter(), Counter(), Counter()
    matching_relations = 0
    rejected = 0
    for task in design["tasks"].values():
        stages = task["stages"]
        if len({stage["required_kind"] for stage in stages}) != 2:
            raise ValueError("Both stages must use independent material")
        if all("delivery_condition" in stage for stage in stages):
            matching_relations += (
                stages[0]["delivery_condition"] == stages[1]["delivery_condition"]
            )
        for position, stage in enumerate(stages):
            current = item(stage)
            if current.mode != "combined":
                if current.delivery_condition is not None:
                    raise ValueError(
                        "Standalone work teaches its seal through actual processing"
                    )
                continue
            fmt = input_for_stage(engine, current)
            relation = current.delivery_condition
            raw_seal = engine.required_verifier_seal(current)
            key = (current.material, current.goal, stage["target"], position)
            pairs[key].append(relation)
            format_counts[current.goal, relation, fmt] += 1
            relation_counts[position, relation] += 1
            raw_counts[current.goal, relation, raw_seal] += 1
            other = next(label for label in SEAL_RELATIONS if label != relation)
            for route in plans(engine, replace(current, delivery_condition=other)):
                completed, results = execute(engine, current, route)
                if (
                    completed
                    or any(effect.result != "processed" for effect in results)
                    or results[-1].output_format != current.goal
                    or score(engine, current, results)["whole_stage_first_correct"]
                ):
                    raise ValueError(
                        "Wrong seal relation must reject eligible standard routes"
                    )
                rejected += 1

    if len(pairs) != 12 or any(
        Counter(p) != Counter(SEAL_RELATIONS) for p in pairs.values()
    ):
        raise ValueError(
            "Require 12 pairs holding material, standard and stage/target fixed"
        )
    if matching_relations != 6 or set(relation_counts.values()) != {6}:
        raise ValueError(
            "Keep both relation labels balanced by position and commission"
        )
    dimensions = [(goal, relation) for goal in STANDARDS for relation in SEAL_RELATIONS]
    if format_counts != {(*key, fmt): 3 for key in dimensions for fmt in FORMATS}:
        raise ValueError("Neither input format can dominate a standard and relation")
    if raw_counts != {(*key, seal): 3 for key in dimensions for seal in ("甲", "乙")}:
        raise ValueError(
            "The raw verification seal must balance within each tested condition"
        )
    signatures = Counter(
        tuple(
            next(
                engine.verifier_seal(material, station)
                for (seen_material, station), (_, seen_goal) in engine.verifiers.items()
                if (seen_material, seen_goal) == (material, goal)
            )
            for goal in STANDARDS
        )
        for material in design["private_interfaces"]["seal_comparison"]["verify"]
    )
    if signatures != {
        ("甲", "甲"): 2,
        ("甲", "乙"): 1,
        ("乙", "甲"): 1,
        ("乙", "乙"): 2,
    }:
        raise ValueError("Keep all four cross-standard signatures")

    before, after = inspect_routes(source), inspect_routes(design)
    distances = {r["task"]: r["fully_informed_distance"] for r in after["tasks"]}
    before_distances = {
        r["task"]: r["fully_informed_distance"] for r in before["tasks"]
    }
    if {task: distances[task] for task in before_distances} != before_distances:
        raise ValueError("Keep the shortest distance of each retained commission")
    source_distance, candidate_distance = sum(before_distances.values()), sum(
        distances.values()
    )
    if (
        after["maximum_fully_informed_actions"]
        != before["maximum_fully_informed_actions"]
        or abs(source_distance / 20 - candidate_distance / 30) > 0.1
    ):
        raise ValueError("Keep route effort matched")
    proof = validate(design, feedback_only_repeats=True)
    if (
        proof["successes"] != 30
        or not proof["actual_prior_feedback_for_every_combined_operation"]
        or proof["required_operations"] != 84
        or proof["feedback_only_repeat_operations_by_encounter"] != {"2": 36, "3": 12}
    ):
        raise ValueError(
            "All 48 repeat operations require observed prior game feedback"
        )
    return {
        "design_id": DESIGN_ID,
        "candidate_only": True,
        "retained_task_definitions": len(retained),
        "added_materials": list(NEW_MATERIALS),
        "linked_source_sha256": SOURCE_SHA256,
        "matched_pairs": len(pairs),
        "valid_standard_wrong_relation_routes": rejected,
        "raw_seal_signature_counts": {
            "".join(key): value for key, value in signatures.items()
        },
        "source_planned_exposure_gaps": exposure_gaps(source),
        "candidate_planned_exposure_gaps": exposure_gaps(design),
        "source_mean_fully_informed_distance": source_distance / 20,
        "candidate_mean_fully_informed_distance": candidate_distance / 30,
        "maximum_fully_informed_actions": after["maximum_fully_informed_actions"],
        "task_order": list(design["tasks"]),
        **proof,
    }


def save_as_new(path, value):
    serialized = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    with path.open("xb") as stream:
        stream.write(serialized)
    return sha256(serialized).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = build()
    assessment = assess(candidate)
    target = args.output
    assessment["design_sha256"] = save_as_new(target, candidate)
    save_as_new(target.with_suffix(".assessment.json"), assessment)
    print(json.dumps(assessment, ensure_ascii=True))


if __name__ == "__main__":
    main()
