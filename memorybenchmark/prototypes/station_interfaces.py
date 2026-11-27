"""Outcome-only processing with explicit intermediate interfaces."""

from copy import deepcopy
from dataclasses import replace

from .composition_lab import (
    SEAL_RELATIONS,
    Outcome,
    Stage,
    World,
    condition_matches,
    input_for_stage,
    plans,
    score,
)


PROTOCOL = "intermediate-interface-processing-1"
STAGE_FIELDS = ("input_state", "output_state", "input_format", "goal")
SEALS = {"甲", "乙"}


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
        stage.get("delivery_condition"),
    )


def current_format(stage, state):
    return (
        state.material_state
        if state.material_state is not None
        else stage["input_format"]
    )


def world(design):
    table = design["private_interfaces"]
    seals = table.get("seal_comparison", {})
    return World(
        tuple(design["public"]["kinds"]),
        table["formats"],
        {(r["material"], r["type"]): r["output"] for r in table["cataloguers"]},
        {
            (r["material"], r["type"]): (r["input"], r["output"])
            for r in table["verifiers"]
        },
        table.get("enforce_interface", True),
        {
            (material, fmt): condition
            for material, formats in table.get("format_conditions", {}).items()
            for fmt, condition in formats.items()
        },
        table.get("verification_conditions"),
        catalogue_seals={
            (material, fmt): seal
            for material, formats in seals.get("catalogue", {}).items()
            for fmt, seal in formats.items()
        },
        verifier_seals=seals.get("verify"),
    )


def _validate_seal_table(seals):
    if (
        not isinstance(seals, dict)
        or set(seals) != {"catalogue", "verify"}
        or any(
            not isinstance(records, dict)
            or not records
            or any(
                not isinstance(by_key, dict)
                or not by_key
                or any(
                    not isinstance(seal, str) or seal not in SEALS
                    for seal in by_key.values()
                )
                for by_key in records.values()
            )
            for records in seals.values()
        )
        or set(seals["catalogue"]) != set(seals["verify"])
    ):
        raise ValueError("Declare matching catalogue and verifier seal tables")


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
        if not data["stations"] or any(
            design["public"]["locations"][s].get("station_type") != name
            for s in data["stations"]
        ):
            raise ValueError("Interface replicas must have consistent public types")
    table = design["private_interfaces"]
    if "seal_comparison" in table:
        _validate_seal_table(table["seal_comparison"])
    w = world(design)
    alternatives = table.get("alternatives_per_goal", 1)
    if type(alternatives) is not int or alternatives not in (1, 2):
        raise ValueError("Declare one or two alternatives for each interface goal")
    conditions = table.get("format_conditions", {})
    verifier_conditions = w.verification_conditions or {}
    if (
        set(verifier_conditions) - set(w.materials)
        or set(verifier_conditions) & set(conditions)
        or (verifier_conditions and (alternatives != 2 or not w.enforce_interface))
    ):
        raise ValueError("Use separate format and verifier condition scopes")
    seal_verifiers = w.verifier_seals or {}
    if seal_verifiers and (
        set(seal_verifiers) - set(w.materials)
        or set(seal_verifiers) & (set(conditions) | set(verifier_conditions))
        or alternatives != 2
        or not w.enforce_interface
    ):
        raise ValueError("Seal comparisons require separate, strict interface scopes")
    for material, by_format in conditions.items():
        if (
            material not in w.materials
            or set(by_format) != set(w.formats[material])
            or any(not isinstance(name, str) or not name for name in by_format.values())
            or len(set(by_format.values())) != 2
            or alternatives != 2
            or not w.enforce_interface
        ):
            raise ValueError(
                "Conditioned interfaces need two distinct format conditions"
            )
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
        by_verifier = verifier_conditions.get(material, {})
        if material in verifier_conditions and (
            set(by_verifier) != {station for station, _ in vers}
            or any(
                not isinstance(label, str) or not label.strip()
                for label in by_verifier.values()
            )
            or len(set(by_verifier.values())) != 2
        ):
            raise ValueError("Each verifier needs one of two delivery conditions")
        sealed = material in seal_verifiers
        if sealed:
            catalogue_seals = table["seal_comparison"]["catalogue"][material]
            if (
                set(catalogue_seals) != set(fmts)
                or set(catalogue_seals.values()) != SEALS
                or set(seal_verifiers[material]) != {station for station, _ in vers}
            ):
                raise ValueError(
                    "Seal tables must cover both formats and all verifiers"
                )
        for goal in ("standard-1", "standard-2"):
            choices = [
                (station, fmt) for station, (fmt, standard) in vers if standard == goal
            ]
            input_count = 2 if material in conditions else 1
            balanced = (
                len({by_verifier[station] for station, _ in choices}) == alternatives
                if by_verifier
                else len({fmt for _, fmt in choices}) == input_count
            )
            if sealed:
                goal_seals = {
                    w.verifier_seal(material, station) for station, _ in choices
                }
                both_formats = {fmt for _, fmt in choices} == set(fmts)
                balanced = both_formats and len(goal_seals) == 1
            if len(choices) != alternatives or not balanced:
                raise ValueError(
                    "A verification goal needs balanced alternatives with the required input coverage"
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
        scoped_conditions = {
            material: by_format
            for material, by_format in conditions.items()
            if material in profile["catalogue"] or material in profile["verify"]
        }
        if scoped_conditions:
            profile["format_conditions"] = scoped_conditions
        scoped_verification = {
            material: by_verifier[name]
            for material, by_verifier in verifier_conditions.items()
            if name in by_verifier
        }
        if scoped_verification:
            profile["verification_conditions"] = scoped_verification
        catalogue_seals = {
            material: w.catalogue_seal(material, fmt)
            for material, fmt in profile["catalogue"].items()
            if material in seal_verifiers
        }
        verifier_seals = {
            material: by_verifier[name]
            for material, by_verifier in seal_verifiers.items()
            if name in by_verifier
        }
        if catalogue_seals or verifier_seals:
            profile["seal_comparison"] = {
                "catalogue": catalogue_seals,
                "verify": verifier_seals,
            }
        assignment.update({s: deepcopy(profile) for s in data["stations"]})
    expected = {design["fixed_world"]: assignment}
    if "private_worlds" in design and design["private_worlds"] != expected:
        raise ValueError("Recorded private assignment differs from interface rules")
    design["private_worlds"] = expected
    for task in design["tasks"].values():
        for stage in task["stages"]:
            current = item(stage)
            if current.material in seal_verifiers:
                labels = {
                    "catalogue": {None},
                    "verify": {None},
                    "combined": SEAL_RELATIONS,
                }
                if current.delivery_condition not in labels[current.mode]:
                    raise ValueError("Delivery condition must match the seal operation")
            elif current.delivery_condition in SEAL_RELATIONS:
                raise ValueError("Seal comparison requires a scoped material")
            needs_condition = (
                current.mode == "combined" and current.material in conditions
            ) or (
                current.mode != "catalogue" and current.material in verifier_conditions
            )
            if needs_condition and current.delivery_condition is None:
                raise ValueError(
                    "A conditioned composition needs a public delivery condition"
                )
            if (
                current.mode == "catalogue"
                and current.material in verifier_conditions
                and current.delivery_condition is not None
            ):
                raise ValueError("Verification conditions apply after catalogue")
            if not plans(w, current):
                raise ValueError("Public interface goal is infeasible")
    return _validate_geography_tasks(design)


def process(design, task, stage, state):
    kind = design["public"]["locations"][state.position]["station_type"]
    w, current = world(design), item(stage)
    result = w.process(
        kind,
        current.material,
        current_format(stage, state),
        compare_seals=w.compares_seals(current),
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
    if result.processing_seal is not None:
        feedback["processing_seal"] = result.processing_seal
    if result.delivery_condition is not None:
        feedback["delivery_condition"] = result.delivery_condition
    after = replace(state, material_state=result.output_format, processed=False)
    if result.output_format == stage["goal"]:
        if not condition_matches(current, result.delivery_condition):
            feedback["delivery_condition_failed"] = True
            return after, feedback, 0
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
    text = f"到{stage['target']}采集{public['kinds'][stage['required_kind']]}的{initial}，交付目标{stage['goal']}"
    if stage.get("delivery_condition") is not None:
        text += f"，交付条件：{stage['delivery_condition']}"
    return text


def outcome_from_feedback(feedback):
    return Outcome(
        feedback["station_type"],
        feedback["required_kind"],
        feedback["requirement"],
        feedback["input_format"],
        feedback["output_format"],
        feedback["result"],
        processing_seal=feedback.get("processing_seal"),
    ).with_condition(feedback.get("delivery_condition"))


def _supports_operation(feedback, w, current, operation, fmt, seal):
    if (
        feedback.get("kind") != "processing_outcome"
        or feedback.get("result") != "processed"
        or feedback.get("required_kind") != current.material
        or feedback.get("requirement") != operation
    ):
        return False
    condition = feedback.get("delivery_condition")
    if operation == "catalogue":
        matches_output = feedback.get("output_format") == fmt
        matches_condition = w.catalogue_condition_matches(current, condition)
    else:
        matches_output = (
            feedback.get("input_format"),
            feedback.get("output_format"),
        ) == (fmt, current.goal)
        matches_condition = condition_matches(current, condition)
    if seal is not None:
        matches_condition = feedback.get("processing_seal") == seal
    return matches_output and matches_condition


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
        current = item(stage)
        sealed = current.material in (w.verifier_seals or {})
        outcomes = [outcome_from_feedback(e["delivered"]["feedback"]) for e in attempts]
        measured = score(w, current, outcomes)
        stage_rows.append(
            {
                "stage_index": index,
                "combined": current.mode == "combined",
                **measured,
            }
        )
        for measured_operation in measured["operations"]:
            operation = measured_operation["operation"]
            actual = [o for o in outcomes if o.operation == operation]
            fmt = (
                input_for_stage(w, current)
                if current.mode == "combined"
                else (
                    stage["goal"] if operation == "catalogue" else stage["input_format"]
                )
            )
            scope_condition = None
            seal = None
            if sealed:
                if operation == "catalogue":
                    seal = w.catalogue_seal(current.material, fmt)
                else:
                    scope_condition = w.required_verifier_seal(current)
                    seal = scope_condition
            elif operation == "verify" and current.material in (
                w.verification_conditions or {}
            ):
                scope_condition = current.delivery_condition
            prior_match = any(
                _supports_operation(
                    e.get("delivered", {}).get("feedback", {}),
                    w,
                    current,
                    operation,
                    fmt,
                    seal,
                )
                for e in prior
            )
            rows.append(
                {
                    "stage_index": index,
                    "material": stage["required_kind"],
                    "operation": operation,
                    "scope_format": fmt,
                    **(
                        {"scope_condition": scope_condition}
                        if scope_condition is not None
                        else {}
                    ),
                    "goal": stage["goal"],
                    "composition": current.mode == "combined",
                    "prior_matching_feedback": prior_match,
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
