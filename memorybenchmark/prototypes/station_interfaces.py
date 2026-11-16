"""Opt-in intermediate-interface processing for isolated Hard calibration."""

from copy import deepcopy
from dataclasses import replace

from .composition_lab import Outcome, Stage, World, score


PROTOCOL = "intermediate-interface-processing-1"
STAGE_FIELDS = {"input_format", "goal"}


def enabled(design):
    return design["public"].get("processing_model") == PROTOCOL


def item(stage):
    modes = {
        ("raw", "catalogued"): "catalogue",
        ("catalogued", "verified"): "verify",
        ("raw", "verified"): "combined",
    }
    return Stage(
        stage["required_kind"],
        modes[(stage["input_state"], stage["output_state"])],
        stage["goal"],
        stage["input_format"],
    )


def current_format(stage, state):
    return (
        state.material_state
        if state.material_state is not None
        else stage["input_format"]
    )


def world(design):
    table = design["private_interfaces"]
    return World(
        tuple(design["public"]["kinds"]),
        table["formats"],
        {(r["material"], r["type"]): r["output"] for r in table["cataloguers"]},
        {
            (r["material"], r["type"]): (r["input"], r["output"])
            for r in table["verifiers"]
        },
        table.get("enforce_interface", True),
    )


def load(design):
    from .station_capability import _validate_geography_tasks

    if (
        not enabled(design)
        or design["public"].get("station_query_enabled") is not False
    ):
        raise ValueError(
            "Interface processing needs its explicit outcome-only protocol"
        )
    types = design["public"]["station_types"]
    stations = {
        s for s, p in design["public"]["locations"].items() if p["kind"] == "station"
    }
    members = [s for t in types.values() for s in t["stations"]]
    if len(members) != len(set(members)) or set(members) != stations:
        raise ValueError("Station types must partition the physical stations")
    for name, data in types.items():
        if len(data["stations"]) != 2 or any(
            design["public"]["locations"][s].get("station_type") != name
            for s in data["stations"]
        ):
            raise ValueError("Interface replicas must have consistent public types")
    w = world(design)
    alternatives = design["private_interfaces"].get("alternatives_per_goal", 1)
    if type(alternatives) is not int or alternatives not in (1, 2):
        raise ValueError("Declare one or two alternatives for each interface goal")
    for material in w.materials:
        fmts = w.formats[material]
        cats = [(s, f) for (m, s), f in w.cataloguers.items() if m == material]
        vers = [(s, v) for (m, s), v in w.verifiers.items() if m == material]
        if (
            len(fmts) != 2
            or len(set(fmts)) != 2
            or len(cats) != 2 * alternatives
            or len(vers) != 2 * alternatives
        ):
            raise ValueError(
                "Each material requires two catalogue and verify interfaces"
            )
        if {f for _, f in cats} != set(fmts) or {v[0] for _, v in vers} != set(fmts):
            raise ValueError("Missing intermediate-format coverage")
        if {v[1] for _, v in vers} != {"standard-1", "standard-2"}:
            raise ValueError("Both requested standards need a feasible interface")
        for fmt in fmts:
            if sum(f == fmt for _, f in cats) != alternatives:
                raise ValueError("Catalogue goal alternatives are unbalanced")
        for goal in ("standard-1", "standard-2"):
            values = [v for _, v in vers if v[1] == goal]
            if len(values) != alternatives or len({v[0] for v in values}) != 1:
                raise ValueError(
                    "A verification goal needs balanced alternatives with one compatible format"
                )
    if any(
        s not in types or m not in w.materials
        for m, s in (*w.cataloguers, *w.verifiers)
    ):
        raise ValueError("Private interface table uses an undeclared material/type")
    if len(w.cataloguers) != len(design["private_interfaces"]["cataloguers"]) or len(
        w.verifiers
    ) != len(design["private_interfaces"]["verifiers"]):
        raise ValueError("Duplicate interface entries")
    assignment = {}
    for name, data in types.items():
        profile = {
            "catalogue": {m: f for (m, s), f in w.cataloguers.items() if s == name},
            "verify": {
                m: {"input": v[0], "output": v[1]}
                for (m, s), v in w.verifiers.items()
                if s == name
            },
            "enforce_interface": w.enforce_interface,
        }
        assignment.update({s: deepcopy(profile) for s in data["stations"]})
    expected = {design["fixed_world"]: assignment}
    if "private_worlds" in design and design["private_worlds"] != expected:
        raise ValueError("Recorded private assignment differs from interface rules")
    design["private_worlds"] = expected
    for task in design["tasks"].values():
        for stage in task["stages"]:
            from .composition_lab import plans

            if not plans(w, item(stage)):
                raise ValueError("Public interface goal is infeasible")
    return _validate_geography_tasks(design)


def process(design, task, stage, state):
    kind = design["public"]["locations"][state.position]["station_type"]
    result = world(design).process(
        kind, stage["required_kind"], current_format(stage, state)
    )
    feedback = {
        "kind": "processing_outcome",
        "station": state.position,
        "station_type": kind,
        "required_kind": stage["required_kind"],
        "requirement": result.operation,
        "input_format": result.input_format,
        "output_format": result.output_format,
        "result": result.result,
    }
    if result.result != "processed":
        return state, feedback, 0
    after = replace(state, material_state=result.output_format, processed=False)
    if result.output_format == stage["goal"]:
        feedback["stage_completed"] = state.stage + 1
        if state.stage + 1 < len(task["stages"]):
            after = replace(
                state, stage=state.stage + 1, raw=False, material_state=None
            )
            feedback["next_stage"] = after.stage + 1
        else:
            after = replace(after, processed=True)
    return after, feedback, 0


def description(public, stage):
    initial = (
        "原始资料"
        if stage["input_format"] is None
        else f"{stage['input_format']}已编目资料"
    )
    return f"到{stage['target']}采集{public['kinds'][stage['required_kind']]}的{initial}，交付目标{stage['goal']}"


def analyze(design, events, task_run_id):
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    started = next(e for e in selected if e["kind"] == "task_started")
    task = design["tasks"][started["task_id"]]
    actions = [e for e in selected if e["kind"] == "action"]
    prior = [e for e in events if e["event_id"] < started["event_id"]]
    w = world(design)
    rows, stage_rows = [], []
    for index, stage in enumerate(task["stages"]):
        attempts = [
            e
            for e in actions
            if e["state_before"].get("stage", 0) == index
            and e["action"]["type"] == "process"
        ]
        outcomes = [
            Outcome(
                e["delivered"]["feedback"]["station_type"],
                stage["required_kind"],
                e["delivered"]["feedback"]["requirement"],
                e["delivered"]["feedback"]["input_format"],
                e["delivered"]["feedback"]["output_format"],
                e["delivered"]["feedback"]["result"],
            )
            for e in attempts
        ]
        measured = score(w, item(stage), outcomes)
        stage_rows.append(
            {
                "stage_index": index,
                "combined": item(stage).mode == "combined",
                **measured,
            }
        )
        for measured_operation in measured["operations"]:
            operation = measured_operation["operation"]
            actual = [o for o in outcomes if o.operation == operation]
            from .composition_lab import input_for_goal

            fmt = (
                input_for_goal(w, stage["required_kind"], stage["goal"])
                if item(stage).mode == "combined"
                else (
                    stage["goal"] if operation == "catalogue" else stage["input_format"]
                )
            )
            prior_matches = [
                e
                for e in prior
                if e.get("delivered", {}).get("feedback", {}).get("kind")
                == "processing_outcome"
                and e["delivered"]["feedback"].get("result") == "processed"
                and e["delivered"]["feedback"].get("required_kind")
                == stage["required_kind"]
                and e["delivered"]["feedback"].get("requirement") == operation
                and (
                    e["delivered"]["feedback"].get("output_format") == fmt
                    if operation == "catalogue"
                    else (
                        e["delivered"]["feedback"].get("input_format"),
                        e["delivered"]["feedback"].get("output_format"),
                    )
                    == (fmt, stage["goal"])
                )
            ]
            rows.append(
                {
                    "stage_index": index,
                    "material": stage["required_kind"],
                    "operation": operation,
                    "scope_format": fmt,
                    "goal": stage["goal"],
                    "composition": item(stage).mode == "combined",
                    "prior_matching_feedback": bool(prior_matches),
                    "first_processing_correct": measured_operation[
                        "goal_compatible_first_success"
                    ],
                    "local_first_success": measured_operation["local_first_success"],
                    "process_attempts": len(actual),
                    "successful_processes": sum(
                        o.result == "processed" for o in actual
                    ),
                }
            )
    moves = [e for e in actions if e["moved"]]
    return {
        "task_id": started["task_id"],
        "task_run_id": task_run_id,
        "success": selected[-1]["delivered"]["observation"]["success"],
        "distance": sum(e["movement_cost"] for e in moves),
        "moves": len(moves),
        "operations": len(actions),
        "query_count": 0,
        "unsupported_processing_count": sum(
            e["delivered"]["feedback"].get("result") == "unsupported" for e in actions
        ),
        "recollections": sum(
            e["action"]["type"] == "survey" and e["state_before"]["raw"]
            for e in actions
        ),
        "processing_operations": rows,
        "stage_outcomes": stage_rows,
        "first_processing_correct": rows[0]["first_processing_correct"],
        "first_operation_correct": sum(r["first_processing_correct"] for r in rows),
        "necessary_operation_denominator": len(rows),
        "planned_exposure_is_not_actual_learning": True,
        "exact_references_computed": False,
    }
