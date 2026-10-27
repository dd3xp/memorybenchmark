"""Descriptive graph/event measurements; never infer retrieval from a path."""
from __future__ import annotations

from math import log2

from .station_capability import ReferencePlanner, capability_groups, compatible_worlds, task_stages
from .station_choice import choice_context, station_decisions
from .station_routes import station_branches, task_group


def analyze_trace(design, events, task_run_id, *, infrastructure_ok=True, exact_references=True):
    if exact_references and design.get("world_generator") == "independent_balanced_allocations":
        raise ValueError("Multi-station maps use descriptive analysis; set exact_references=False or --skip-exact-references")
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in selected if e["kind"] == "task_started")
    task_id, task = start["task_id"], design["tasks"][start["task_id"]]
    prior = [e for e in events if e["event_id"] < start["event_id"]]
    prior_worlds = compatible_worlds(design, prior)
    kinds = task["required_kind"]
    stages = task_stages(task)
    stations = [n for n, data in design["public"]["locations"].items() if data["kind"] == "station"]
    known_match = [s for s in stations if all(design["private_worlds"][w][s] == kinds for w in prior_worlds)]
    history, within = list(prior), []
    query_events, processing = [], []
    actions = [e for e in selected if e["kind"] == "action"]
    for event in actions:
        old_all, old_current = compatible_worlds(design, history), compatible_worlds(design, within)
        new_all, new_current = compatible_worlds(design, history + [event]), compatible_worlds(design, within + [event])
        verb, feedback = event["action"]["type"], event["delivered"]["feedback"]
        if verb == "inspect":
            query_events.append({"event_id": event["event_id"], "station": event["from"],
                                 "new_historical_bits": log2(len(old_all) / len(new_all)),
                                 "new_within_session_bits": log2(len(old_current) / len(new_current))})
        if verb == "process":
            processing.append({"event_id": event["event_id"], "station": event["from"],
                               "supported": feedback.get("result") == "processed",
                               "already_excluded_by_actual_history": all(
                                   design["private_worlds"][w][event["from"]] != stages[event["state_before"].get("stage", 0)]["required_kind"] for w in old_all)})
        history.append(event)
        within.append(event)
    moves = [e for e in actions if e["moved"]]
    distance = sum(e["movement_cost"] for e in moves)
    success = selected[-1]["delivered"]["observation"]["success"] if infrastructure_ok else None
    all_worlds = tuple(design["private_worlds"])
    history_distance = nohistory_distance = physical_distance = None
    if exact_references:
        planner = ReferencePlanner(design, task_id)
        history_distance = float(planner.initial(tuple(prior_worlds)).distance)
        nohistory_distance = float(planner.initial(all_worlds).distance)
        # A known-world physical reference is not an unknown-world agent's attainable policy.
        physical = [planner.initial((w,)).distance for w in all_worlds]
        if len(set(physical)) != 1:
            raise ValueError("This diagnostic requires a common physical reference across the matched worlds")
        physical_distance = float(physical[0])
    station_excursions = []
    for incoming, outgoing in zip(moves, moves[1:]):
        station = incoming["to"]
        if (station in stations and incoming["from"] == outgoing["to"] and outgoing["from"] == station):
            operations = [e for e in actions if incoming["event_id"] < e["event_id"] < outgoing["event_id"]]
            station_excursions.append({"station": station, "enter": incoming["event_id"], "exit": outgoing["event_id"],
                "distance": incoming["movement_cost"] + outgoing["movement_cost"],
                "operations": [e["action"]["type"] for e in operations],
                "unsupported_attempts": sum(e["delivered"]["feedback"].get("result") == "unsupported" for e in operations),
                "processed": any(e["delivered"]["feedback"].get("result") == "processed" for e in operations)})
    prior_sources = [e["event_id"] for e in prior if e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"]
    relevant_stations = {s for i in range(len(stages))
                         for s in capability_groups(design)[task_group(design, task_id, i)]["stations"]}
    related_prior_sources = [e["event_id"] for e in prior if
        e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information" and
        e["delivered"]["feedback"]["station"] in relevant_stations]
    result = {
        "task_id": task_id, "task_run_id": task_run_id, "success": success,
        "distance": distance, "moves": len(moves), "operations": len(actions),
        "visited_nodes": sorted({start["position"]} | {e["to"] for e in moves}),
        "path": [start["position"]] + [e["to"] for e in moves],
        "prior_relevant_exposure": bool(known_match), "historically_determined_matching_stations": known_match,
        "prior_related_station_feedback_received": bool(related_prior_sources),
        "prior_related_station_feedback_events": related_prior_sources,
        "prior_evidence_events": prior_sources,
        "prior_compatible_world_count": len(prior_worlds),
        "after_compatible_world_count": len(compatible_worlds(design, history)),
        "historical_new_bits": log2(len(prior_worlds) / len(compatible_worlds(design, history))),
        "queries": query_events, "processing": processing, "station_excursions": station_excursions,
        "query_count": len(query_events),
        "historically_repeated_queries": sum(q["new_historical_bits"] == 0 for q in query_events),
        "within_session_repeated_queries": sum(q["new_within_session_bits"] == 0 for q in query_events),
        "unsupported_processing_count": sum(not p["supported"] for p in processing),
        "first_processing_correct": processing[0]["supported"] if processing else None,
        "history_contradicting_processing_count": sum(p["already_excluded_by_actual_history"] for p in processing),
        "physical_min_distance": physical_distance,
        "successful_distance_excess": distance - physical_distance if success and physical_distance is not None else None,
        "full_delivered_history_reference_expected_distance": history_distance,
        "nohistory_reference_expected_distance": nohistory_distance,
        "exact_references_computed": exact_references,
    }
    if any(len(group["stations"]) > 2 for group in design["public"].get("capability_groups", {}).values()):
        first = next((e["to"] for e in moves if e["to"] in stations), None)
        result["first_station_choice"] = choice_context(design, task_id, prior, first)
        result["station_decisions"] = station_decisions(design, events, task_run_id)
    if len(stages) > 1:
        result["stage_history_exposure"] = [{"stage_index": i, **stage,
            "historically_determined_matching_stations": [s for s in capability_groups(design)[task_group(design, task_id, i)]["stations"]
                if all(design["private_worlds"][w][s] == stage["required_kind"] for w in prior_worlds)]}
            for i, stage in enumerate(stages)]
        result["prior_relevant_exposure"] = any(r["historically_determined_matching_stations"] for r in result["stage_history_exposure"])
        result["historically_determined_matching_stations"] = sorted({s for r in result["stage_history_exposure"] for s in r["historically_determined_matching_stations"]})
        result["completed_stages"] = selected[-1]["delivered"]["observation"]["stages_completed"]
        result["total_stages"] = len(stages)
        excursions = []
        for station, branch in station_branches(design).items():
            for i, move in enumerate(moves):
                if (move["from"],move["to"]) != (branch["fork"],branch["path"][1]):continue
                end = next((m for m in moves[i+1:] if m["to"] == branch["fork"]), None)
                last = end["event_id"] if end else selected[-1]["event_id"]
                segment = [e for e in actions if move["event_id"] <= e["event_id"] <= last]
                walked = [e for e in segment if e["moved"]]
                excursions.append({"station":station,"fork":branch["fork"],"enter":move["event_id"],
                    "exit":end["event_id"] if end else None,"returned_to_fork":end is not None,
                    "stage_index":move["state_before"]["stage"],
                    "move_event_ids":[e["event_id"] for e in walked],
                    "distance":sum(e["movement_cost"] for e in walked),
                    "unsupported_attempts":sum(e["delivered"]["feedback"].get("result")=="unsupported" for e in segment),
                    "processed":any(e["delivered"]["feedback"].get("result")=="processed" for e in segment)})
        result["branch_excursions"] = sorted(excursions,key=lambda r:r["enter"])
    return result
