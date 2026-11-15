"""Typed processing within an independent commission stage.

Catalogue consumes raw input and yields catalogued input. Verify consumes
catalogued input and yields verified output. No dependency crosses stages.
"""

from collections import Counter
from dataclasses import replace

PROTOCOL = "typed-processing-composition-1"
STATES = {"raw": "原始资料", "catalogued": "已编目资料", "verified": "已核验资料"}
OPERATIONS = {"raw": "catalogue", "catalogued": "verify"}
OUTPUTS = {"catalogue": "catalogued", "verify": "verified"}


def enabled(design):
    return design["public"].get("processing_model") == PROTOCOL


def current_state(stage, state):
    return state.material_state or stage["input_state"]


def requirements(stage):
    state = stage["input_state"]
    result = []
    while state != stage["output_state"]:
        operation = OPERATIONS[state]
        result.append(operation)
        state = OUTPUTS[operation]
    return result


def active_requirement(stage, state):
    return OPERATIONS[current_state(stage, state)]


def validate_stage(stage):
    if (stage["input_state"], stage["output_state"]) not in {
        ("raw", "catalogued"),
        ("catalogued", "verified"),
        ("raw", "verified"),
    }:
        raise ValueError("Unsupported typed processing commission")
    if stage["requirement"] != requirements(stage)[-1]:
        raise ValueError(
            "Public requested result differs from the typed processing goal"
        )


def complete_operation(task, state, stage, feedback, supported):
    if not supported:
        return state
    operation = active_requirement(stage, state)
    output = OUTPUTS[operation]
    feedback.update(operation_completed=operation, output_state=output)
    if output != stage["output_state"]:
        feedback.update(stage_completed=False, remaining_requirement=OPERATIONS[output])
        return replace(state, material_state=output, processed=False)
    if state.stage + 1 < len(task["stages"]):
        feedback.update(stage_completed=state.stage + 1, next_stage=state.stage + 2)
        return replace(
            state,
            stage=state.stage + 1,
            raw=False,
            processed=False,
            material_state=None,
        )
    return replace(state, material_state=output, processed=True)


def validate_allocation(design):
    single, combined, first_single = Counter(), Counter(), {}
    combinations = Counter()
    for task_index, task in enumerate(design["tasks"].values()):
        if len(task["stages"]) != 2:
            raise ValueError("Hard commissions have two independent stages")
        for stage in task["stages"]:
            validate_stage(stage)
            operations = requirements(stage)
            kind = stage["required_kind"]
            if len(operations) == 1:
                key = (kind, operations[0])
                single[key] += 1
                first_single.setdefault(key, task_index)
            else:
                combinations[kind] += 1
                for operation in operations:
                    key = (kind, operation)
                    if key not in first_single or first_single[key] >= task_index:
                        raise ValueError(
                            "Both basic experiences need opportunities in earlier tasks"
                        )
                    combined[key] += 1
    expected = {
        (kind, operation) for kind in design["public"]["kinds"] for operation in OUTPUTS
    }
    if set(single) != expected or set(combined) != expected:
        raise ValueError("Every basic experience needs standalone and combined uses")
    if (
        set(single.values()) != {2}
        or set(combined.values()) != {2}
        or set(combinations.values()) != {2}
    ):
        raise ValueError(
            "Every basic experience must have 2 standalone + 2 combined planned uses"
        )
    return {
        "tasks": len(design["tasks"]),
        "stages": 72,
        "basic_experiences": 24,
        "standalone_stages": 48,
        "combined_stages": 24,
        "necessary_operations": 96,
        "per_experience_standalone": 2,
        "per_experience_combined": 2,
        "prerequisite_policy": "both basic operations first occur in earlier normal scored tasks",
    }


def analyze(design, events, task_run_id):
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    first = next(e for e in selected if e["kind"] == "task_started")
    task = design["tasks"][first["task_id"]]
    actions = [e for e in selected if e["kind"] == "action"]
    processing = [e for e in actions if e["action"]["type"] == "process"]
    prior = [e for e in events if e["event_id"] < first["event_id"]]
    rows = []
    for stage_index, stage in enumerate(task["stages"]):
        for operation in requirements(stage):
            attempts = [
                e
                for e in processing
                if e["state_before"].get("stage", 0) == stage_index
                and e["delivered"]["feedback"].get("requirement") == operation
            ]
            history = [
                e
                for e in prior
                if e.get("delivered", {}).get("feedback", {}).get("kind")
                == "station_information"
                and e["delivered"]["feedback"].get("requirement") == operation
            ]
            matches = [
                e
                for e in history
                if stage["required_kind"] in e["delivered"]["feedback"]["capability"]
            ]
            rows.append(
                {
                    "stage_index": stage_index,
                    "material": stage["required_kind"],
                    "operation": operation,
                    "composition": len(requirements(stage)) == 2,
                    "prior_matching_feedback": bool(matches),
                    "first_processing_correct": bool(
                        attempts
                        and attempts[0]["delivered"]["feedback"].get("result")
                        == "processed"
                    ),
                    "process_attempts": len(attempts),
                    "successful_processes": sum(
                        e["delivered"]["feedback"].get("result") == "processed"
                        for e in attempts
                    ),
                }
            )
    moves = [e for e in actions if e["moved"]]
    return {
        "task_id": first["task_id"],
        "task_run_id": task_run_id,
        "success": selected[-1]["delivered"]["observation"]["success"],
        "distance": sum(e["movement_cost"] for e in moves),
        "moves": len(moves),
        "operations": len(actions),
        "query_count": 0,
        "unsupported_processing_count": sum(
            e["delivered"]["feedback"].get("result") == "unsupported"
            for e in processing
        ),
        "processing_operations": rows,
        "first_processing_correct": (
            rows[0]["first_processing_correct"] if rows else None
        ),
        "first_operation_correct": sum(r["first_processing_correct"] for r in rows),
        "necessary_operation_denominator": len(rows),
        "planned_exposure_is_not_actual_learning": True,
        "exact_references_computed": False,
    }


def stage_description(public, stage):
    return (
        f"{stage['target']}采集{STATES[stage['input_state']]}（{public['kinds'][stage['required_kind']]}），"
        + "需"
        + "→".join(
            public["requirements"][operation] for operation in requirements(stage)
        )
        + f"，交付{STATES[stage['output_state']]}"
    )
