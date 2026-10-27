"""Evaluate route-choice evidence without equating proximity with memory use."""
from .station_capability import compatible_worlds
from .station_routes import station_options


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
