"""Descriptive graph/event measurements; never infer retrieval from a path."""
from __future__ import annotations

from math import log2

from .station_capability import ReferencePlanner, compatible_worlds


def analyze_trace(design, events, task_run_id, *, infrastructure_ok=True, exact_references=True):
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in selected if e["kind"] == "task_started")
    task_id, task = start["task_id"], design["tasks"][start["task_id"]]
    prior = [e for e in events if e["event_id"] < start["event_id"]]
    prior_worlds = compatible_worlds(design, prior)
    kinds = task["required_kind"]
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
                                   design["private_worlds"][w][event["from"]] != kinds for w in old_all)})
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
    return {
        "task_id": task_id, "task_run_id": task_run_id, "success": success,
        "distance": distance, "moves": len(moves), "operations": len(actions),
        "visited_nodes": sorted({start["position"]} | {e["to"] for e in moves}),
        "path": [start["position"]] + [e["to"] for e in moves],
        "prior_relevant_exposure": bool(known_match), "historically_determined_matching_stations": known_match,
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
