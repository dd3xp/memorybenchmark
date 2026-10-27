"""Evaluate route-choice evidence without equating proximity with memory use."""
from .station_capability import capability_groups, compatible_worlds
from .station_routes import station_options, task_group


def choice_context(design, task_id, prior_events, selected=None):
    """Only actual prior feedback defines knowledge; partial knowledge stays partial."""
    possible = compatible_worlds(design, prior_events)
    kind = design["tasks"][task_id]["required_kind"]
    options = station_options(design, task_id)
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
    stations = set(capability_groups(design)[task_group(design, task_id)]["stations"])
    within, entries, precollection = [], [], []
    for event in current:
        if (event["kind"] == "action" and event["moved"] and
                event["to"] in stations and not event["state_before"]["processed"]):
            collected = event["state_before"]["raw"]
            row = {"event_id": event["event_id"], "station": event["to"],
                   "raw_already_collected": collected,
                   "pre_task_history": choice_context(design, task_id, prior, event["to"]),
                   "current_session_only": choice_context(design, task_id, within, event["to"]),
                   "all_delivered_before_entry": choice_context(design, task_id, prior + within, event["to"])}
            (entries if collected else precollection).append(row)
        within.append(event)
    first = entries[0] if entries else None
    return {"precollection_station_entries": precollection,
            "postcollection_station_entries": entries,
            "first_postcollection_station": first,
            "postcollection_entries_known_nonmatch_by_history": sum(
                row["all_delivered_before_entry"]["selected_historical_status"] == "known_nonmatch"
                for row in entries),
            "postcollection_entries_known_nonmatch_in_current_session": sum(
                row["current_session_only"]["selected_historical_status"] == "known_nonmatch"
                for row in entries),
            "scope": "delivered game evidence only; no claim about saved, retrieved or causally used memory"}
