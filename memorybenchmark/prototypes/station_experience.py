"""Evaluator-only dependencies and actual cross-session exposure evidence.

Neither a visit nor a correct choice proves memory use. These functions never
write agent memory or add facts to StationGame.observation().
"""
from .station_capability import compatible_worlds, task_stages
from .station_choice import station_decisions


def experience_schedule(design):
    """Potential source stages, conditional on actual successful processing."""
    previous, rows = {}, []
    seen_tasks = {}
    for index, (task_id, task) in enumerate(design["tasks"].items()):
        stages = task_stages(task)
        signature = tuple((s["target"], s["required_kind"]) for s in stages)
        row = {"task_id": task_id, "exact_repeat_of": seen_tasks.get(signature), "stages": []}
        # Only earlier sessions qualify, even if a design has two same-kind stages.
        for stage_index, stage in enumerate(stages):
            sources = previous.get(stage["required_kind"], [])
            row["stages"].append({"stage_index": stage_index, **stage,
                "earlier_same_kind_stages": [dict(s) for s in sources],
                "has_success_conditioned_predecessor": bool(sources),
                "intervening_tasks_since_same_kind_requirement": index - sources[-1]["task_index"] - 1 if sources else None})
        for stage_index, stage in enumerate(stages):
            previous.setdefault(stage["required_kind"], []).append({"task_id": task_id,
                "task_index": index, "stage_index": stage_index, "target": stage["target"]})
        seen_tasks.setdefault(signature, task_id)
        rows.append(row)
    return rows


def _source(event):
    feedback = event["delivered"]["feedback"]
    return {"event_id": event["event_id"], "task_id": event["task_id"],
            "task_run_id": event["task_run_id"],
            "stage_index": event.get("state_before", {}).get("stage", 0),
            "station": feedback["station"], "capability": feedback["capability"],
            "station_type": feedback.get("station_type"),
            "operation": event.get("action", {}).get("type"), "result": feedback.get("result")}


def experience_opportunities(design, events, task_run_id, *, decisions=None):
    """Link before-task feedback to observed choices, retaining unvisited stages.

    Both retained and clear probes use the same evaluator history. A clear probe
    is not treated as having received that history in its model input.
    """
    current = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in current if e["kind"] == "task_started")
    prior = [e for e in events if e["event_id"] < start["event_id"]]
    feedback = [e for e in prior if e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"]
    visited = {e.get("to", e.get("position")) for e in prior}
    worlds = compatible_worlds(design, prior)
    decisions = decisions if decisions is not None else station_decisions(design, events, task_run_id)
    planned = next(r for r in experience_schedule(design) if r["task_id"] == start["task_id"])
    stages = []
    groups = design["public"]["capability_groups"]
    for index, stage in enumerate(task_stages(design["tasks"][start["task_id"]])):
        kind = stage["required_kind"]
        group = next(g for g in groups.values() if kind in g["kinds"])
        related = [e for e in feedback if e["delivered"]["feedback"]["station"] in group["stations"]]
        matching = [_source(e) for e in related if e["delivered"]["feedback"]["capability"] == kind]
        nonmatching = [_source(e) for e in related if e["delivered"]["feedback"]["capability"] != kind]
        known = [s for s in group["stations"] if all(design["private_worlds"][w][s] == kind for w in worlds)]
        direct = sorted({s["station"] for s in matching})
        direct_types = sorted({s["station_type"] for s in matching if s["station_type"] is not None})
        type_matches = sorted(s for s in group["stations"]
            if design["public"]["locations"][s].get("station_type") in direct_types)
        decision_stage = next((s for s in decisions.get("stages", []) if s["stage_index"] == index), {})
        branch = decision_stage.get("first_postcollection_branch_choice")
        choice = None
        if branch:
            station = branch["station"]
            station_type = design["public"]["locations"][station].get("station_type")
            assignment = {design["private_worlds"][w][station] for w in worlds}
            actual_feedback = next((e["delivered"]["feedback"] for e in current
                if e["event_id"] > branch["event_id"] and e.get("from") == station
                and e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"), None)
            choice = {"event_id": branch["event_id"], "station": station,
                      "station_type": station_type,
                      "previously_visited_station": station in visited,
                      "same_type_prior_feedback": [_source(e) for e in related
                          if station_type is not None and e["delivered"]["feedback"].get("station_type") == station_type],
                      "new_station_of_previously_observed_type": station_type in direct_types and station not in visited,
                      "historical_status": branch["pre_task_history"]["selected_historical_status"],
                      "previous_direct_feedback": [_source(e) for e in related if e["delivered"]["feedback"]["station"] == station],
                      "previous_successful_same_kind_processing": [s for s in matching if s["station"] == station and s["result"] == "processed"],
                      "matching_determined_before_task": assignment == {kind},
                      "matching_if_later_observed": actual_feedback["capability"] == kind if actual_feedback else None}
        cutoff = branch["event_id"] if branch else None
        reacquired = [_source(e) for e in current if cutoff is not None and e["event_id"] < cutoff
            and e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"
            and e["delivered"]["feedback"]["station"] in group["stations"]]
        stages.append({"stage_index": index, **stage,
            "planned_predecessor_stages": planned["stages"][index]["earlier_same_kind_stages"],
            "direct_matching_feedback": matching, "direct_nonmatching_feedback": nonmatching,
            "previous_successful_same_kind_processing": [s for s in matching if s["result"] == "processed"],
            "directly_observed_matching_stations": direct,
            "directly_observed_matching_types": direct_types,
            "matching_stations_known_from_type": type_matches,
            "unvisited_matching_stations_of_observed_types": sorted(set(type_matches) - visited),
            "historically_determined_matching_stations": known,
            "matching_stations_known_only_by_inference": sorted(set(known) - set(direct) - set(type_matches)),
            "has_prior_matching_opportunity": bool(known),
            "has_prior_exclusion_opportunity": bool(nonmatching),
            "choice_observed": branch is not None, "first_branch_choice": choice,
            "current_session_feedback_before_choice": reacquired})
    return {"protocol": "station-experience-opportunity-1", "task_id": start["task_id"],
            "scope": "Evaluator exposure and observed action only; not saved, retrieved, or causally used memory. Missing choices remain null.",
            "stages": stages}
