"""Replay published actions through both feedback modes; make no model calls."""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_session import EASY20_LINKED_DESIGN, FEEDBACK_PROTOCOLS, StationSession
from scripts.check_station_capability import trace_graph


DEFAULT_TRACES = Path(__file__).resolve().parents[1] / "docs/assets/hermes-linked-easy20/trace-projection.json.gz"


def encoded(value):
    return json.dumps(value, ensure_ascii=False)


def verify_projected_event(actual, projected):
    for key, value in projected.items():
        if key == "feedback":
            assert actual["delivered"]["feedback"] == value
        elif key == "observation":
            assert {k: actual["delivered"]["observation"][k] for k in value} == value
        else:
            assert actual[key] == value, key


def validate(traces=DEFAULT_TRACES, *, world="omega_3051"):
    traces = Path(traces)
    projection = json.loads(gzip.decompress(traces.read_bytes()))
    design = load_design(EASY20_LINKED_DESIGN)
    assert design["public"] == projection["public_map"]
    assert design["tasks"] == projection["tasks"]
    canonical = StationGame(world, design)
    checkpoint, checkpoint_task = None, None
    rows, samples = [], {}
    for recorded in projection["sessions"]:
        if recorded["task_id"] != checkpoint_task:
            checkpoint, checkpoint_task = deepcopy(canonical), recorded["task_id"]
        games = [deepcopy(checkpoint), deepcopy(checkpoint)]
        full, compact = [StationSession(game, recorded["task_id"], feedback_mode=mode)
                         for game, mode in zip(games, ("full", "compact"))]
        assert full.initial == compact.initial
        verify_projected_event(games[0].events[-1], recorded["current_events"][0])
        before = deepcopy(games[1].events), games[1].steps
        read = compact.dispatch({"command": "read"})
        assert read["observation"]["environment"] == design["public"]
        assert read["feedback"] == {"kind": "current_observation"}
        assert (games[1].events, games[1].steps) == before
        totals = {"full_chars": 0, "compact_chars": 0, "full_utf8_bytes": 0, "compact_utf8_bytes": 0}
        actions = 0
        for event in recorded["current_events"][1:]:
            assert event["kind"] == "action", "This published fixture contains game actions only"
            request = {"command": "action", "request_id": str(actions), "action": event["action"]}
            a, b = full.dispatch(request), compact.dispatch(request)
            assert "error" not in a and "error" not in b
            assert a["feedback"] == b["feedback"]
            verify_projected_event(games[0].events[-1], event)
            observation = deepcopy(b["observation"])
            assert observation.pop("environment_version") == design["public"]["version"]
            assert observation.pop("required_kind_name") == design["public"]["kinds"][observation["task"]["required_kind"]]
            assert observation.pop("neighbors")
            observation["environment"] = design["public"]
            assert observation == a["observation"]
            for mode, response in (("full", a), ("compact", b)):
                body = encoded(response)
                totals[mode + "_chars"] += len(body)
                totals[mode + "_utf8_bytes"] += len(body.encode("utf-8"))
            category = ("stage_transition" if "next_stage" in b["feedback"] else
                        b["feedback"].get("result", b["feedback"]["kind"]))
            samples.setdefault(category, {"session": recorded["name"], "request": request, "compact_response": b})
            actions += 1
        assert games[0].events == games[1].events
        graph = trace_graph(games[0])
        assert graph == trace_graph(games[1]) == recorded["graph"]
        assert games[0].done
        rows.append({"session": recorded["name"], "actions": actions, "moves": len(graph["edges"]),
                     "distance": graph["distance"], "success": games[0].state.success, **totals})
        if recorded["condition"] != "clear":
            canonical = games[0]
    actions = sum(row["actions"] for row in rows)
    totals = {key: sum(row[key] for row in rows) for key in ("full_chars", "compact_chars", "full_utf8_bytes", "compact_utf8_bytes")}
    return {
        "kind": "fixed_historical_actions_feedback_replay_not_agent_performance",
        "passed": True, "llm_calls": 0, "design_id": design["design_id"], "private_fixture": world,
        "source_traces_sha256": sha256(traces.read_bytes()).hexdigest(),
        "source_pilot_sha256": projection["source_pilot_sha256"], "feedback_protocols": FEEDBACK_PROTOCOLS,
        "sessions": len(rows), "actions": actions, "moves": sum(row["moves"] for row in rows),
        "successes": sum(row["success"] for row in rows),
        "comparison_scope": "Action response JSON only, ensure_ascii=False and default separators; excludes initial map, explicit reads, native wrappers and model tokens",
        "same_canonical_events_and_published_graphs": True, "full_map_read_is_free": True,
        "totals": totals,
        "mean_chars_per_action": {mode: totals[mode + "_chars"] / actions for mode in ("full", "compact")},
        "character_reduction_fraction": 1 - totals["compact_chars"] / totals["full_chars"],
        "utf8_byte_reduction_fraction": 1 - totals["compact_utf8_bytes"] / totals["full_utf8_bytes"],
        "per_session": rows, "samples": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", type=Path, default=DEFAULT_TRACES)
    parser.add_argument("--world", default="omega_3051", help="private host replay fixture, never delivered to the agent")
    parser.add_argument("--output", type=Path, required=True, help="new JSON file")
    args = parser.parse_args()
    report = validate(args.traces, world=args.world)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("per_session", "samples")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
