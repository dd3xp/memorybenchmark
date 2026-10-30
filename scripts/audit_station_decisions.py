"""Align station-entry events with native tools; never publish model prose."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_choice import station_decisions


def tool_window(messages):
    tools = [m for m in messages if m.get("kind") == "tool"]
    return {
        "model_request_count": sum(m.get("kind") == "request" and m.get("method") == "model" for m in messages),
        "tool_counts": dict(Counter(m["name"] for m in tools)),
        "file_read_basenames": [Path(m["args"].get("path", "")).name for m in tools if m["name"] in ("file_read", "read_file")],
        "native_skill_view_requests": [{k: m.get("args", {}).get(k) for k in ("name", "file_path")
                                        if k in m.get("args", {})}
                                       for m in tools if m["name"] == "skill_view"],
        "code_run_argument_sha256": [sha256(json.dumps(m["args"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                                     for m in tools if m["name"] == "code_run"],
        "native_retrieval_tool_names": [m["name"] for m in tools if m["name"] in
            ("file_read", "read_file", "code_run", "terminal", "skill_view", "session_search")],
        "scope": "tool invocations only; file reads and scripts require content review to establish relevant evidence delivery",
    }


def align_tools(events, task_run_id, messages, decision):
    current = [e for e in events if e["task_run_id"] == task_run_id and e["kind"] == "action"]
    requests = [(i, m) for i, m in enumerate(messages) if m.get("kind") == "request" and
                m.get("method") == "game" and m.get("params", {}).get("command") == "action"
                and not m.get("action_policy_rejected")]
    initial = next(e for e in events if e["task_run_id"] == task_run_id and e["kind"] == "task_started")
    available = initial["delivered"]["observation"]["available_actions"]
    end = next(i for i, m in enumerate(messages) if m.get("kind") == "request" and m.get("method") == "task_end")
    offsets, rejected, cursor = {}, [], 0
    for i, message in requests:
        action = message["params"]["action"]
        if i > end or action not in available:
            rejected.append(action)
            continue
        if cursor >= len(current) or current[cursor]["action"] != action:
            raise ValueError("Legal game request/event mismatch; refusing an approximate tool window")
        event = current[cursor]
        offsets[event["event_id"]] = i
        available = event["delivered"]["observation"]["available_actions"]
        cursor += 1
    if cursor != len(current):
        raise ValueError("Actual event without aligned native request")
    terminal_action = next((e for e in current if e["delivered"]["observation"]["done"]), None)
    game_end = offsets[terminal_action["event_id"]] + 1 if terminal_action else end
    result = {"before_task_end": tool_window(messages[:end]),
              "before_game_terminal_event": tool_window(messages[:game_end]),
              "after_game_done_before_task_end": tool_window(messages[game_end:end]),
              "rejected_native_game_requests": rejected}
    first = decision["first_postcollection_station"]
    result["before_first_postcollection_station"] = tool_window(messages[:offsets[first["event_id"]]]) if first else None
    if "stages" in decision:
        result["stages"] = [{"stage_index":s["stage_index"],
            **{name: tool_window(messages[:offsets[s[key]["event_id"]]]) if s[key] else None
               for name,key in (("before_first_postcollection_station","first_postcollection_station"),
                                ("before_first_postcollection_branch_choice","first_postcollection_branch_choice"))}}
            for s in decision["stages"]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = args.run.resolve()
    pilot = json.loads((root / "pilot.json").read_text(encoding="utf-8"))
    if pilot["status"] != "completed":
        raise ValueError("Only completed pilots are reported")
    design = json.loads((root / "design.json").read_text(encoding="utf-8"))
    rows = []
    for session in pilot["sessions"]:
        folder = root / "sessions" / session["name"]
        graph = json.loads((folder / "graph.json").read_text(encoding="utf-8"))
        events = [json.loads(s) for s in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        messages = [json.loads(s) for s in (folder / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        decisions = station_decisions(design, events, graph["task_run_id"])
        rows.append({"name": session["name"], "task_id": session["task_id"], "condition": session["condition"],
                     "success": session["success"], "station_decisions": decisions,
                     "native_tool_windows": align_tools(events, graph["task_run_id"], messages, decisions),
                     "source_audit_sha256": sha256((folder / "audit.jsonl").read_bytes()).hexdigest(),
                     "source_events_sha256": sha256((folder / "events.jsonl").read_bytes()).hexdigest()})
    artifact = {"kind": "native_tool_timing_and_game_evidence_audit_not_causal_memory_attribution", "rows": rows,
                "source_pilot_sha256": sha256((root / "pilot.json").read_bytes()).hexdigest(),
                "source_design_sha256": sha256((root / "design.json").read_bytes()).hexdigest(),
                "analysis_sources_sha256": {str(p.relative_to(Path(__file__).resolve().parents[1])).replace("\\", "/"):
                    sha256(p.read_bytes()).hexdigest() for p in
                    (Path(__file__).resolve(), *(Path(__file__).resolve().parents[1] / ("memorybenchmark/prototypes/" + name)
                        for name in ("station_choice.py", "station_routes.py", "station_capability.py")))}}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(artifact, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"sessions": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
