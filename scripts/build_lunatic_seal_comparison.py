"""Build a Scandinavia candidate that composes two observed seals."""

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


DESIGN_ID = "lunatic-01-v4.6-seal-comparison20"
DATA = Path(__file__).resolve().parents[1] / "memorybenchmark/data/calibration"
SOURCE = DATA / "scandinavia_lunatic_delivery_conditions20.json"
REFERENCE = DATA / "scandinavia_lunatic_verifier_conditions20.json"
RELATIONS = ("封签一致", "封签不同")
SEALS = ("甲", "乙")


def build():
    source = SOURCE.read_bytes()
    design = json.loads(source)
    table = design["private_interfaces"]
    catalogue, verification = {}, {}
    for index, material in enumerate(MATERIALS):
        del table["format_conditions"][material]
        catalogue[material] = dict(
            zip(
                table["formats"][material],
                SEALS[:: 1 if index % 2 else -1],
                strict=True,
            )
        )
        seal_by_standard = dict(
            zip(STANDARDS, SEALS[:: 1 if index < 2 else -1], strict=True)
        )
        verification[material] = {
            row["type"]: seal_by_standard[row["output"]]
            for row in table["verifiers"]
            if row["material"] == material
        }
    if not table["format_conditions"]:
        del table["format_conditions"]
    table["seal_comparison"] = {"catalogue": catalogue, "verify": verification}

    # Balance the relations at each stage position without letting the first
    # stage predict whether the second requests the same relation.
    offsets = {
        goal: dict(zip(MATERIALS, values, strict=True))
        for goal, values in zip(STANDARDS, ((0, 1, 1, 0), (1, 1, 0, 0)), strict=True)
    }
    for task in design["tasks"].values():
        for stage in task["stages"]:
            current = item(stage)
            if current.mode == "combined":
                relation = (
                    CONDITIONS.index(current.delivery_condition)
                    + offsets[current.goal][current.material]
                ) % 2
                stage["delivery_condition"] = RELATIONS[relation]
        task.update(task["stages"][0])

    design.update(
        design_id=DESIGN_ID,
        status="seal_comparison_candidate_pending_native_calibration",
        fixed_world=f"{design['fixed_world'].removesuffix('-delivery-conditions')}-seal-comparison",
        provenance={
            "source_design": design["design_id"],
            "source_design_sha256": sha256(source).hexdigest(),
            "reviewed_materials": list(MATERIALS),
        },
    )
    design["public"]["version"] = DESIGN_ID
    design["public"]["rules"][-1] = (
        "有封签关系的委托要求交付标准和两张封签的关系同时符合。"
        "编目与核验各产生一张封签，两签相同为封签一致，不同为封签不同。"
        "处理反馈显示该次处理实际签发的封签。两段委托分别采集独立资料。"
    )
    return design


def assess(design):
    reference = json.loads(REFERENCE.read_bytes())
    if geography(design["public"]) != geography(reference["public"]):
        raise ValueError("The original Scandinavia geography must remain in use")

    engine = world(design)
    combined = defaultdict(list)
    ordinary = Counter()
    relations_by_stage = Counter()
    matching_stage_relations = 0
    for name, task in design["tasks"].items():
        original = reference["tasks"][name]
        if any(
            task[key] != original[key] for key in ("start", "submit_at", "max_steps")
        ):
            raise ValueError("Keep the matched commission locations and budget")
        for index, (stage, earlier) in enumerate(
            zip(task["stages"], original["stages"], strict=True)
        ):
            current = item(stage)
            if any(
                stage[key] != earlier[key]
                for key in (
                    "target",
                    "required_kind",
                    "input_state",
                    "output_state",
                    "goal",
                )
            ):
                raise ValueError("Keep the matched stage and survey point")
            if current.mode != "combined":
                if current.delivery_condition is not None:
                    raise ValueError(
                        "Standalone commissions should reveal seals by processing"
                    )
                ordinary[current.mode] += 1
                continue
            combined[current.material, current.goal].append(stage)
            relations_by_stage[index, current.delivery_condition] += 1
        relations = [stage.get("delivery_condition") for stage in task["stages"]]
        matching_stage_relations += (
            relations[0] in RELATIONS and relations[0] == relations[1]
        )

    rejected = 0
    for first, second in combined.values():
        if first["target"] != second["target"] or {
            first["delivery_condition"],
            second["delivery_condition"],
        } != set(RELATIONS):
            raise ValueError(
                "Both relations need a matched commission at the same point"
            )
        for required, alternate in (
            (item(first), item(second)),
            (item(second), item(first)),
        ):
            good, wrong = plans(engine, required), plans(engine, alternate)
            if not good or set(good) & set(wrong):
                raise ValueError("The alternative relation must change the valid route")
            for route in wrong:
                success, outcomes = execute(engine, required, route)
                if (
                    success
                    or any(outcome.result != "processed" for outcome in outcomes)
                    or outcomes[-1].output_format != required.goal
                    or score(engine, required, outcomes)["whole_stage_first_correct"]
                ):
                    raise ValueError(
                        "The wrong seal relation must reject a valid standard"
                    )
                rejected += 1

    routes = inspect_routes(design)
    proof = validate(design)
    if (
        proof["successes"] != len(design["tasks"])
        or not proof["actual_prior_feedback_for_every_combined_operation"]
    ):
        raise ValueError(
            "Compositions must be solvable from earlier delivered feedback"
        )
    return {
        "design_id": DESIGN_ID,
        "standalone_catalogue_stages": ordinary["catalogue"],
        "standalone_verification_stages": ordinary["verify"],
        "matched_relation_pairs": len(combined),
        "commissions_with_same_relation_in_both_stages": matching_stage_relations,
        "relation_count_by_stage": [
            {label: relations_by_stage[index, label] for label in RELATIONS}
            for index in range(2)
        ],
        "valid_standard_wrong_relation_routes": rejected,
        "physical_stations": routes["physical_stations"],
        "maximum_fully_informed_actions": routes["maximum_fully_informed_actions"],
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
