"""Ordered commute multigraph and descriptive return-excursion diagnostics."""
def commute_graph(events, task_run_id):
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in selected if e["kind"] == "task_started")
    nodes = {start["position"]}
    edges = []
    for event in selected:
        if event.get("moved"):
            nodes.update((event["from"], event["to"]))
            edges.append({"id": event["event_id"], "kind": "commute", "source": event["from"],
                          "target": event["to"], "weight": event["movement_cost"],
                          "effort": event.get("effort_cost", event["movement_cost"]),
                          "stamina_spent": event.get("stamina_spent"),
                          "hazard_cost": event.get("hazard_cost", 0),
                          "inventory_before": event.get("inventory_before", []),
                          "equipment_used": event.get("equipment_used"),
                          "order": len(edges), "time": event["time_before"],
                          "life": event.get("state_before", {}).get("deaths", 0)})
        if event.get("respawn"):
            r = event["respawn"]
            nodes.update((r["source"], r["target"]))
            edges.append({"id": f"{event['event_id']}:respawn", "kind": "respawn",
                          "source": r["source"], "target": r["target"], "weight": r["weight"],
                          "effort": 0, "stamina_spent": 0, "hazard_cost": 0,
                          "inventory_before": [t["id"] for t in r["death_observation"]["inventory"]],
                          "equipment_used": None, "order": len(edges), "time": r["time_before"],
                          "life": event.get("state_before", {}).get("deaths", 0) + 1})
    commutes = [e for e in edges if e["kind"] == "commute"]
    respawns = [e for e in edges if e["kind"] == "respawn"]
    return {"nodes": sorted(nodes), "edges": edges,
            "distance": sum(e["weight"] for e in commutes), "effort": sum(e["effort"] for e in commutes),
            "deaths": len(respawns), "respawn_penalty": sum(e["weight"] for e in respawns),
            "total_weight": sum(e["weight"] for e in edges),
            "stamina_spent": sum(e["stamina_spent"] for e in commutes) if all(e["stamina_spent"] is not None for e in commutes) else None}


def diagnose(events, task_run_id):
    """Descriptions, not memory-use claims. Evidence always precedes the attempt."""
    evidence = set()
    first_visit = {}
    previous_visit = {}
    excursions = []
    repeated_blocks = []
    hazards, known_hazards, known_tools, takes, respawns = [], {}, {}, [], []
    by_id = {e["event_id"]: e for e in events}
    for event in events:
        if event["kind"] == "task_started":
            for ev in event.get("evidence_delivered", []):
                if ev["claim"] == "tool_available":
                    known_tools[(ev["tool"], ev["location"], ev["world_version"])] = ev
            first_visit.setdefault(event["position"], event["event_id"])
            if event["task_run_id"] == task_run_id:
                previous_visit = {event["position"]: event["event_id"]}
            continue
        exposed = event.get("evidence_delivered") or []
        reset = event.get("respawn") if event["task_run_id"] == task_run_id else None
        if reset:
            respawns.append({k: reset[k] for k in ("source", "target", "weight", "event_id", "step")})
        if isinstance(exposed, dict):
            exposed = [exposed]  # Read v1 logs as well as current logs.
        if event.get("action", {}).get("type") == "take" and event.get("outcome") == "ok" and event["task_run_id"] == task_run_id:
            takes.append({"event_id": event["event_id"], "location": event["from"], "tool": event["action"]["target"]})
        for ev in exposed:
            if ev["claim"] == "tool_available":
                known_tools[(ev["tool"], ev["location"], ev["world_version"])] = ev
                continue
            if ev["claim"] == "hazard_encountered":
                key = (ev["location"], ev["hazard"], tuple(sorted(ev["conditions"].items())), ev["world_version"])
                if event["task_run_id"] == task_run_id:
                    tools = [v for (_, _, version), v in known_tools.items() if version == ev["world_version"]
                             and ev["hazard"] in v["tool_info"]["mitigates"]]
                    hazards.append({"event_id": event["event_id"], "location": ev["location"],
                                    "prior_same_condition_evidence": list(known_hazards.get(key, [])),
                                    "prior_relevant_tool_sources": sorted({v["source_event_id"] for v in tools}),
                                    "protected": ev["equipment_used"] is not None,
                                    "equipment_used": ev["equipment_used"], "observed_extra_effort": ev["extra_effort_observed"]})
                known_hazards.setdefault(key, []).append(ev["source_event_id"])
                continue
            if ev["claim"] != "crossing_blocked":
                continue
            key = (tuple(ev["edge"]), tuple(sorted(ev["conditions"].items())), ev["world_version"])
            if key in evidence and event["task_run_id"] == task_run_id:
                repeated_blocks.append(event["event_id"])
            evidence.add(key)
        if not event.get("moved"):
            if reset:
                previous_visit = {reset["target"]: event["event_id"]}
            continue
        target = event["to"]
        first_visit.setdefault(target, event["event_id"])
        if event["task_run_id"] != task_run_id:
            continue
        if target in previous_visit:
            lower, upper = previous_visit[target], event["event_id"]
            segment = [e for i, e in by_id.items() if lower < i <= upper and e["task_run_id"] == task_run_id]
            moves = [e for e in segment if e.get("moved")]
            repeats = [e["event_id"] for e in segment if e["event_id"] in repeated_blocks]
            new = sorted({e["to"] for e in moves if first_visit[e["to"]] > lower} - {target})
            kind = "return_with_repeated_block" if repeats else ("return_with_new_location" if new else "other_return")
            excursions.append({"anchor": target, "start_event": lower, "end_event": upper,
                               "kind": kind, "movement_cost": sum(e["movement_cost"] for e in moves),
                               "new_locations": new, "repeated_block_events": repeats})
        previous_visit[target] = event["event_id"]
        if reset:
            # A teleport must not manufacture a walked return excursion.
            previous_visit = {reset["target"]: event["event_id"]}
    return {"task_run_id": task_run_id, "repeated_block_events": repeated_blocks,
            "excursions": excursions, "hazard_decisions": hazards, "tool_takes": takes,
            "respawns": respawns}
