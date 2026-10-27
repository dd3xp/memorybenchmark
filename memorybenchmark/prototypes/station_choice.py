"""Evaluate route-choice evidence without equating proximity with memory use."""
from .station_capability import capability_groups, compatible_worlds, task_stages
from .station_routes import station_branches, station_options, task_group


def choice_context(design, task_id, prior_events, selected=None, *, stage_index=0, start=None):
    """Only actual prior feedback defines knowledge; partial knowledge stays partial."""
    possible = compatible_worlds(design, prior_events)
    kind = task_stages(design["tasks"][task_id])[stage_index]["required_kind"]
    options = station_options(design, task_id, stage_index=stage_index, start=start)
    for row in options:
        values = {design["private_worlds"][w][row["station"]] == kind for w in possible}
        row["historical_status"] = "known_match" if values == {True} else "known_nonmatch" if values == {False} else "unresolved"
    nearest = min(row["distance_from_target"] for row in options)
    known = [row for row in options if row["historical_status"] == "known_match"]
    best = known[0]["completion_distance"] if known else None
    provable = best is not None and all(row["completion_distance"] >= best or row["historical_status"] == "known_nonmatch" for row in options)
    chosen = next((row for row in options if row["station"] == selected), None)
    return {"selected_station": selected, "candidate_options": options,
            "nearest_candidates": [row["station"] for row in options if row["distance_from_target"] == nearest],
            "selected_is_geographically_nearest": chosen["distance_from_target"] == nearest if chosen else None,
            "selected_historical_status": chosen["historical_status"] if chosen else None,
            "lowest_cost_known_matching_stations": [row["station"] for row in known if row["completion_distance"] == best],
            "best_matching_cost_provable_from_history": provable,
            "conditional_distance_reference": best if provable else None}


def station_decisions(design, events, task_run_id):
    """Describe station entries before processing, with evidence timing intact.

    Full delivered history is an evaluator reference, not the agent's knowledge.
    In particular, a clear probe has the same canonical history but no inherited
    game memory. Current-session evidence is therefore reported separately.
    """
    current = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in current if e["kind"] == "task_started")
    task_id = start["task_id"]
    prior = [e for e in events if e["event_id"] < start["event_id"]]
    task = design["tasks"][task_id]; stages = task_stages(task)
    starts = {0: task["start"]}
    within, entries, precollection = [], [], []
    branches = station_branches(design)
    departures = {(r["fork"],r["path"][1]):s for s,r in branches.items()}
    commitments = []
    for event in current:
        index = event.get("state_before", {}).get("stage", 0)
        stations = set(capability_groups(design)[task_group(design, task_id, index)]["stations"])
        branch_station = departures.get((event.get("from"),event.get("to"))) if event.get("moved") else None
        if branch_station in stations and event["state_before"]["raw"] and not event["state_before"]["processed"]:
            commitments.append({"event_id": event["event_id"],"station":branch_station,
                "fork":event["from"],"stage_index":index,
                "pre_task_history":choice_context(design,task_id,prior,branch_station,stage_index=index,start=starts[index]),
                "current_session_only":choice_context(design,task_id,within,branch_station,stage_index=index,start=starts[index]),
                "all_delivered_before_choice":choice_context(design,task_id,prior+within,branch_station,stage_index=index,start=starts[index])})
        if (event["kind"] == "action" and event["moved"] and
                event["to"] in stations and not event["state_before"]["processed"]):
            collected = event["state_before"]["raw"]
            row = {"event_id": event["event_id"], "station": event["to"],
                   "raw_already_collected": collected,
                   "pre_task_history": choice_context(design, task_id, prior, event["to"], stage_index=index, start=starts[index]),
                   "current_session_only": choice_context(design, task_id, within, event["to"], stage_index=index, start=starts[index]),
                   "all_delivered_before_entry": choice_context(design, task_id, prior + within, event["to"], stage_index=index, start=starts[index])}
            if len(stages) > 1:
                row["stage_index"] = index
            (entries if collected else precollection).append(row)
        if event.get("state_after", {}).get("stage", 0) != index:
            starts[event["state_after"]["stage"]] = event["to"]
        within.append(event)
    first = entries[0] if entries else None
    result = {"precollection_station_entries": precollection,
            "postcollection_station_entries": entries,
            "first_postcollection_station": first,
            "postcollection_entries_known_nonmatch_by_history": sum(
                row["all_delivered_before_entry"]["selected_historical_status"] == "known_nonmatch"
                for row in entries),
            "postcollection_entries_known_nonmatch_in_current_session": sum(
                row["current_session_only"]["selected_historical_status"] == "known_nonmatch"
                for row in entries),
            "scope": "delivered game evidence only; no claim about saved, retrieved or causally used memory"}
    if len(stages) > 1:
        result["stages"] = [{"stage_index": i, **stage,
                            "first_postcollection_station": next((r for r in entries if r["stage_index"] == i), None),
                            "postcollection_station_entries": [r for r in entries if r["stage_index"] == i],
                            "first_postcollection_branch_choice": next((r for r in commitments if r["stage_index"] == i),None)}
                           for i, stage in enumerate(stages)]
        result["postcollection_branch_choices"] = commitments
        result["first_postcollection_branch_choice"] = commitments[0] if commitments else None
        result["cost_reference_scope"] = "Each stage's route from its actual start through its target/station to the next target, or final camp. No sum of local references is a globally optimal itinerary."
    return result
