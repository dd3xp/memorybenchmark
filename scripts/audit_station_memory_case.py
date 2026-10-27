"""Verify a reviewed station fact reached the model before its station choice."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import compatible_worlds
from memorybenchmark.prototypes.station_choice import station_decisions
from scripts.audit_station_decisions import align_tools


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit(root, task, memory_file, fragment, station, kind, request_number):
    root = Path(root).resolve()
    pilot, design = read(root / "pilot.json"), read(root / "design.json")
    assert pilot["status"] == "completed", "Case reports require a complete pilot"
    previous = root / "baseline"
    for session in pilot["sessions"]:
        if session["task_id"] == task and session["condition"] == "retain":
            break
        if session["condition"] != "clear":
            previous = root / "sessions" / session["name"] / "memory-after"
    else:
        raise ValueError("No retained session for this task")
    memory = previous / memory_file
    assert memory.resolve().is_relative_to(previous.resolve())
    text = memory.read_text(encoding="utf-8")
    assert fragment and fragment in text, "Reviewed fragment is absent from input memory"
    baseline = root / "baseline" / memory_file
    assert not baseline.exists() or fragment not in baseline.read_text(encoding="utf-8"), "Fragment is not newly generated"
    folder = root / "sessions" / session["name"]
    graph = read(folder / "graph.json")
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    messages = [json.loads(line) for line in (folder / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    decision = station_decisions(design, events, graph["task_run_id"])
    windows = align_tools(events, graph["task_run_id"], messages, decision)
    first = decision["first_postcollection_station"]
    assert first and first["station"] == station, "Selected fact does not concern the first station"
    start = next(e for e in events if e["task_run_id"] == graph["task_run_id"] and e["kind"] == "task_started")
    prior = [e for e in events if e["event_id"] < start["event_id"]]
    worlds = compatible_worlds(design, prior)
    assert worlds and all(design["private_worlds"][w][station] == kind for w in worlds), "Fact is not supported by prior delivered evidence"
    required = design["tasks"][task]["required_kind"]
    assert 1 <= request_number <= windows["before_first_postcollection_station"]["model_request_count"]
    request = folder / "model" / f"{request_number:03d}-request.json"
    forwarded = json.dumps(read(request), ensure_ascii=False)
    assert json.dumps(fragment, ensure_ascii=False)[1:-1] in forwarded, "Fragment was not actually forwarded"
    outcomes = [e for e in events if e["task_run_id"] == graph["task_run_id"] and e["event_id"] > first["event_id"]
                and e.get("delivered", {}).get("feedback", {}).get("station") == station]
    return {"kind": "reviewed_self_generated_fact_delivery_and_station_choice_not_internal_causality",
            "agent": pilot.get("agent", "ga"), "task": task, "session": session["name"],
            "required_kind": required, "first_postcollection_station": station,
            "reviewed_fact": {"station": station, "capability": kind, "verbatim_game_memory_fragment": fragment},
            "review_scope": "Human-selected literal game fact; support and delivery verified algorithmically. No model reasoning is published.",
            "choice_relation_to_reviewed_fact": "known_match" if kind == required else "known_nonmatch",
            "fact_entailed_by_actual_prior_delivered_history": True,
            "prior_direct_support_event_ids": [e["event_id"] for e in prior if e.get("delivered", {}).get("feedback", {}).get("station") == station
                                               and e["delivered"]["feedback"].get("capability") == kind],
            "prior_station_feedback_event_ids": [e["event_id"] for e in prior if e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"],
            "input_memory_file": memory_file, "input_memory_sha256": sha256(memory.read_bytes()).hexdigest(),
            "forwarded_request_number": request_number, "forwarded_request_sha256": sha256(request.read_bytes()).hexdigest(),
            "model_requests_before_first_postcollection_station": windows["before_first_postcollection_station"]["model_request_count"],
            "verified_delivery_before_first_postcollection_station_entry": True,
            "actual_station_feedback": [{"event_id": e["event_id"], "feedback": e["delivered"]["feedback"]} for e in outcomes],
            "source_pilot_sha256": sha256((root / "pilot.json").read_bytes()).hexdigest(),
            "source_events_sha256": sha256((folder / "events.jsonl").read_bytes()).hexdigest(),
            "source_audit_sha256": sha256((folder / "audit.jsonl").read_bytes()).hexdigest(),
            "analysis_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("task", "memory-file", "fragment", "station", "capability"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--request-number", type=int, required=True)
    args = parser.parse_args()
    result = audit(args.run, args.task, args.memory_file, args.fragment, args.station, args.capability, args.request_number)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"agent": result["agent"], "task": args.task, "verified": True}))


if __name__ == "__main__":
    main()
