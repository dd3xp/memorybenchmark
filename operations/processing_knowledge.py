"""Export evaluation-only processing rules and observations from audited traces."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

from memorybenchmark.event_store import decode_events
from memorybenchmark.map_catalog import MAPS, station_design
from memorybenchmark.prototypes import station_composition as composition
from memorybenchmark.prototypes import station_interfaces as interfaces
from memorybenchmark.prototypes.composition_lab import input_for_goal
from memorybenchmark.prototypes.station_capability import (
    conditional_capabilities,
    load_design,
    map_world,
    region_matches,
    task_stages,
)


TYPED_INPUT = {"catalogue": "raw", "verify": "catalogued"}
ANY_PREPARED_INPUT = "*prepared"


def _operators(design):
    operators = defaultdict(list)
    for station, location in design["public"]["locations"].items():
        if location["kind"] == "station":
            operators[location.get("station_type", station)].append(station)
    return {key: sorted(members) for key, members in sorted(operators.items())}


def _rule_keys(design, operators, world_id):
    if interfaces.enabled(design):
        world = interfaces.world(design)
        for (material, operator), output in world.cataloguers.items():
            yield operator, material, "catalogue", "raw", output
        for (material, operator), (required, output) in world.verifiers.items():
            input_spec = required if world.enforce_interface else ANY_PREPARED_INPUT
            yield operator, material, "verify", input_spec, output
        return

    assignment = design["private_worlds"][world_id]
    for operator, members in operators.items():
        capabilities = assignment[members[0]]
        if any(assignment[station] != capabilities for station in members):
            raise ValueError("Same-type stations do not share a processing rule")
        by_operation = (
            capabilities
            if conditional_capabilities(design)
            else {"process": capabilities}
        )
        for operation, supported in by_operation.items():
            typed = composition.enabled(design)
            input_spec = TYPED_INPUT[operation] if typed else "raw"
            output_spec = composition.OUTPUTS[operation] if typed else "processed"
            for material in supported if isinstance(supported, list) else [supported]:
                yield operator, material, operation, input_spec, output_spec


def processing_table(design, *, world_id=None):
    """Project positive rule rows from exactly one validated fixed design."""
    world_id = map_world(design, world_id)
    operators = _operators(design)
    rules = [
        dict(
            rule_id=f"R{index:04d}",
            operator=operator,
            material=material,
            operation=operation,
            input_spec=input_spec,
            output_spec=output_spec,
        )
        for index, (
            operator,
            material,
            operation,
            input_spec,
            output_spec,
        ) in enumerate(sorted(_rule_keys(design, operators, world_id)), 1)
    ]
    body = {
        "design_id": design["design_id"],
        "world_id": world_id,
        "difficulty": design["public"]["difficulty"],
        "processing_model": design["public"].get(
            "processing_model", "station-capability"
        ),
        "materials": design["public"]["kinds"],
        "operators": operators,
        "rules": rules,
    }
    return {
        **body,
        "processing_table_sha256": sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _required_processing(design, stage, world):
    if world is not None:
        item = interfaces.item(stage)
        if item.mode == "combined":
            intermediate = input_for_goal(world, item.material, item.goal)
            return (
                ("catalogue", "raw", intermediate),
                ("verify", intermediate, item.goal),
            )
        return ((item.mode, item.input_format or "raw", item.goal),)
    if composition.enabled(design):
        return tuple(
            (operation, TYPED_INPUT[operation], composition.OUTPUTS[operation])
            for operation in composition.requirements(stage)
        )
    return ((stage.get("requirement", "process"), "raw", "processed"),)


def _task_opportunities(design, table, candidates, disclosed, task_id):
    world = interfaces.world(design) if interfaces.enabled(design) else None
    out = {}
    for stage_index, stage in enumerate(task_stages(design["tasks"][task_id])):
        material = stage["required_kind"]
        for operation, required_input, required_output in _required_processing(
            design, stage, world
        ):
            eligible = [
                r["rule_id"]
                for r in candidates[material, operation, required_output]
                if (
                    r["input_spec"] == required_input
                    or r["input_spec"] == ANY_PREPARED_INPUT
                    and required_input != "raw"
                )
                and any(
                    region_matches(design, stage, station)
                    for station in table["operators"][r["operator"]]
                )
            ]
            out[stage_index, operation] = {
                "task_id": task_id,
                "stage_index": stage_index,
                "material": material,
                "operation": operation,
                "required_input": required_input,
                "required_output": required_output,
                "eligible_rule_ids": eligible,
                "prior_disclosure_events": {
                    rule_id: disclosed[rule_id][0]
                    for rule_id in eligible
                    if rule_id in disclosed
                },
                "first_attempt_event_id": None,
                "first_correct": False,
            }
    return out


def observed_processing(design, table, events):
    """Map delivered feedback and attempted processing to table rows."""
    by_operator = defaultdict(list)
    candidates = defaultdict(list)
    index = {}
    for row in table["rules"]:
        by_operator[row["operator"], row["operation"]].append(row)
        candidates[row["material"], row["operation"], row["output_spec"]].append(row)
        key = (row["operator"], row["operation"], row["material"], row["input_spec"])
        if key in index:
            raise ValueError("A processing input has multiple fixed outputs")
        index[key] = row

    stations = {
        station: operator
        for operator, members in table["operators"].items()
        for station in members
    }
    disclosed, exposures, attempts, opportunities = {}, [], [], []
    first_attempts = set()
    previous_id = -1
    active_task = None
    current_opportunities = {}
    typed = composition.enabled(design)
    for event in events:
        event_id = event["event_id"]
        if event_id != previous_id + 1:
            raise ValueError(
                "Expected the complete canonical cumulative event sequence"
            )
        previous_id = event_id
        if event["kind"] == "task_started":
            active_task = (event["task_id"], event["task_run_id"])
            first_attempts.clear()
            current_opportunities = _task_opportunities(
                design, table, candidates, disclosed, event["task_id"]
            )
            opportunities.extend(current_opportunities.values())
        if active_task != (event["task_id"], event["task_run_id"]):
            raise ValueError("Event is outside its canonical task boundary")
        if event["kind"] != "action":
            continue
        feedback = event["delivered"]["feedback"]
        kind = feedback["kind"]
        if kind not in (
            "station_information",
            "processing_outcome",
            "wrong_processing_region",
        ):
            continue
        task_id, task_run_id = active_task
        stage_index = event["state_before"].get("stage", 0)
        stage = task_stages(design["tasks"][task_id])[stage_index]
        material = stage["required_kind"]
        station = feedback["station"]
        operator = stations[station]
        if feedback.get("station_type", operator) != operator:
            raise ValueError("Delivered station type contradicts the design")
        operation = feedback.get("requirement") or "process"
        input_spec = TYPED_INPUT[operation] if typed else "raw"
        if kind == "processing_outcome":
            input_spec = feedback.get("input_format") or "raw"
            if feedback["required_kind"] != material:
                raise ValueError("Delivered material differs from the active stage")
        key = operator, operation, material, input_spec
        rule = index.get(key)
        if kind == "processing_outcome" and input_spec != "raw" and rule is None:
            rule = index.get((operator, operation, material, ANY_PREPARED_INPUT))
        successful = feedback.get("result") == "processed"
        if kind == "station_information":
            matching = by_operator[operator, operation]
            delivered = feedback["capability"]
            delivered = delivered if isinstance(delivered, list) else [delivered]
            if set(delivered) != {r["material"] for r in matching}:
                raise ValueError("Capability feedback contradicts the processing table")
        elif kind == "processing_outcome":
            matching = [rule] if successful and rule else []
            if successful and (
                rule is None or rule["output_spec"] != feedback["output_format"]
            ):
                raise ValueError("Successful outcome contradicts the processing table")
        else:
            matching = []

        if event["action"]["type"] == "process":
            if kind != "wrong_processing_region" and successful != bool(rule):
                raise ValueError("Processing outcome contradicts the table")
            cursor = stage_index, operation
            first = cursor not in first_attempts
            first_attempts.add(cursor)
            selected = rule["rule_id"] if successful else None
            earlier = disclosed.get(selected)
            prior_task_event = (
                earlier[0] if earlier and earlier[1] != task_run_id else None
            )
            opportunity = current_opportunities.get(cursor)
            goal_compatible = (
                opportunity is not None and selected in opportunity["eligible_rule_ids"]
            )
            if first and opportunity is not None:
                opportunity["first_attempt_event_id"] = event_id
                opportunity["first_correct"] = goal_compatible
            attempts.append(
                {
                    "event_id": event_id,
                    "task_id": task_id,
                    "stage_index": stage_index,
                    "station": station,
                    "operator": operator,
                    "material": material,
                    "operation": operation,
                    "input_spec": input_spec,
                    "goal": stage.get("goal", stage.get("output_state", "processed")),
                    "result": feedback["result"],
                    "rule_id": selected,
                    "first_attempt": first,
                    "goal_compatible": goal_compatible,
                    "same_rule_disclosed_in_earlier_task_event_id": prior_task_event,
                    "first_correct_after_prior_rule_disclosure": (
                        first and goal_compatible and prior_task_event is not None
                    ),
                }
            )
        if matching:
            rule_ids = [r["rule_id"] for r in matching]
            exposures.append(
                {"event_id": event_id, "task_id": task_id, "rule_ids": rule_ids}
            )
            for rule_id in rule_ids:
                disclosed.setdefault(rule_id, (event_id, task_run_id))
    return {
        "processing_attempts": len(attempts),
        "distinct_rules_disclosed": len(disclosed),
        "required_opportunities": len(opportunities),
        "first_correct": sum(o["first_correct"] for o in opportunities),
        "opportunities_with_prior_disclosure": sum(
            bool(o["prior_disclosure_events"]) for o in opportunities
        ),
        "first_correct_when_prior_disclosed": sum(
            o["first_correct"] and bool(o["prior_disclosure_events"])
            for o in opportunities
        ),
        "first_correct_after_prior_rule_disclosure": sum(
            a["first_correct_after_prior_rule_disclosure"] for a in attempts
        ),
        "disclosures": exposures,
        "attempts": attempts,
        "opportunities": opportunities,
    }


def audited_archive(path):
    """Read only the selected members of an already verified managed archive."""
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read("provenance/archive-content-manifest.json"))

        def checked(name):
            contents = archive.read(name)
            expected = {"bytes": len(contents), "sha256": sha256(contents).hexdigest()}
            if manifest.get(name) != expected:
                raise ValueError("Archived evidence differs from its manifest: " + name)
            return contents

        audit = json.loads(checked("provenance/audit-result.json"))
        pilot = json.loads(checked("run/pilot.json"))
        design = json.loads(checked("run/design.json"))
        sessions = pilot["sessions"]
        replay = audit["replay"]
        if (
            pilot["experiment_mode"] != "independent"
            or pilot["status"] != "completed"
            or audit["status"] != "completed_and_audited"
            or pilot["experiment_id"] != audit["experiment_id"]
            or pilot["memory_condition"] != audit["condition"]
            or pilot["design_id"] != design["design_id"]
            or [s["task_id"] for s in sessions] != pilot["tasks"]
            or len(sessions) != audit["tasks"]
            or len(sessions) != replay["canonical_tasks"]
            or not replay["memory_chains_verified"]
            or not replay["fresh_sessions_and_isolation_verified"]
            or not replay["native_archive_verified"]
            or not sessions
        ):
            raise ValueError("Expected a complete independent audited archive")
        name = sessions[-1]["name"]
        if "/" in name or "\\" in name or name in ("", ".", ".."):
            raise ValueError("Invalid archived session directory")
        events = decode_events(
            checked(f"run/sessions/{name}/events.jsonl"),
            lambda blob: checked(f"run/event-store/{blob}"),
        )
        started = [e["task_id"] for e in events if e["kind"] == "task_started"]
        if started != pilot["tasks"]:
            raise ValueError("Cumulative events differ from the canonical task order")
        table = processing_table(design, world_id=pilot["world"])
        observations = observed_processing(design, table, events)
        by_task = defaultdict(list)
        for opportunity in observations["opportunities"]:
            by_task[opportunity["task_id"]].append(opportunity)
        for row in audit["rows"]:
            if "necessary_operation_denominator" not in row:
                continue
            required = by_task[row["task_id"]]
            if (
                len(required) != row["necessary_operation_denominator"]
                or sum(o["first_correct"] for o in required)
                != row["first_operation_correct"]
            ):
                raise ValueError(
                    "Projected required operations differ from original audit"
                )
        return {
            **table,
            "experiment_id": pilot["experiment_id"],
            "condition": pilot["memory_condition"],
            "map_configuration_sha256": pilot["map_configuration_sha256"],
            "observations": observations,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--catalog", action="store_true")
    sources.add_argument("--design", type=Path, action="append")
    sources.add_argument("--archive", type=Path, action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [station_design(key) for key in MAPS] if args.catalog else args.design
    tables = (
        [audited_archive(path) for path in args.archive]
        if args.archive
        else [processing_table(load_design(path)) for path in paths]
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(
            {
                "schema": "benchmark-processing-table-1",
                "scope": "evaluator_only",
                "tables": tables,
            },
            stream,
            ensure_ascii=False,
            indent=2,
        )
        stream.write("\n")


if __name__ == "__main__":
    main()
