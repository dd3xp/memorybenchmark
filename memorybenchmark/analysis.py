"""Ordered commute multigraph and descriptive return-excursion diagnostics."""
def commute_graph(events, task_run_id):
    selected = [e for e in events if e["task_run_id"] == task_run_id]
    start = next(e for e in selected if e["kind"] == "task_started")
    nodes = {start["position"]}
    edges = []
    for event in selected:
        if event.get("moved"):
            nodes.update((event["from"], event["to"]))
            edges.append({"id": event["event_id"], "source": event["from"],
                          "target": event["to"], "weight": event["movement_cost"],
                          "order": len(edges), "time": event["time_before"]})
    return {"nodes": sorted(nodes), "edges": edges,
            "distance": sum(e["weight"] for e in edges)}


def diagnose(events, task_run_id):
    """Descriptions, not memory-use claims. Evidence always precedes the attempt."""
    evidence = set()
    first_visit = {}
    previous_visit = {}
    excursions = []
    repeated_blocks = []
    by_id = {e["event_id"]: e for e in events}
    for event in events:
        if event["kind"] == "task_started":
            first_visit.setdefault(event["position"], event["event_id"])
            if event["task_run_id"] == task_run_id:
                previous_visit = {event["position"]: event["event_id"]}
            continue
        ev = event.get("evidence_delivered")
        if ev:
            key = (tuple(ev["edge"]), tuple(sorted(ev["conditions"].items())), ev["world_version"])
            if key in evidence and event["task_run_id"] == task_run_id:
                repeated_blocks.append(event["event_id"])
            evidence.add(key)
        if not event.get("moved"):
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
    return {"task_run_id": task_run_id, "repeated_block_events": repeated_blocks, "excursions": excursions}
