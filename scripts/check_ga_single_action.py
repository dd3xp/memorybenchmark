"""Exercise the real native GA with scripted responses; no provider requests."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from memorybenchmark.ga_runtime import WSLJail, make_support
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_routes import shortest_route
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN
from scripts.check_station_native_sessions import ScriptedResponses, check_feedback_delivery


def check_boundaries(folder):
    counts = {}
    response = 0
    rejected = 0
    with (folder / "audit.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            prefix = line[:150]
            if '"kind": "request"' not in prefix:
                continue
            if '"method": "model"' in prefix:
                response += 1
            elif '"method": "game"' in prefix:
                message = json.loads(line)
                if message["params"].get("command") != "action":
                    continue
                if message.get("action_policy_rejected"):
                    rejected += 1
                else:
                    counts[response] = counts.get(response, 0) + 1
    assert all(number > 0 and count == 1 for number, count in counts.items())
    return {"model_responses_with_actions": len(counts), "rejected_extra_actions": rejected}


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    reference = args.reference_run.resolve()
    source, baseline = reference / "source/GenericAgent", reference / "baseline"
    support = make_support(root / "support")
    jail = WSLJail(args.distro, args.runtime)
    design = load_design(EASY20_REUSE_DESIGN)
    sessions = StationNativeSessions(source, support, jail, agent="ga", game_access="native",
        action_policy="single", feedback_mode="compact", model_alias="fixture", seed=20261029,
        max_turns=3, final_turns=1, wall_seconds=300)
    script = "from game_client import action; print([action('move', target=n) for n in ['J', 'JN']])"
    model = ScriptedResponses([("code_run", {"type": "python", "script": script}),
                              ("game_action", {"action": "move", "target": "JN"})], "ga", "native")
    game = StationGame("omega_00_00", design)
    limited = sessions.run(game, "T1", baseline, root / "boundary", model, condition="prefix")
    assert limited["infrastructure_ok"], limited.get("infrastructure_error")
    assert game.steps == 2 and game.state.position == "JN"
    assert limited["action_policy_rejections"] == 1
    # Even a script that accumulates its output before printing must deliver
    # the accepted first action's feedback when the second action is stopped.
    next_input = json.dumps(model.requests[1], ensure_ascii=False)
    assert "decision_boundary" in next_input and "last_game_response" in next_input
    boundary = check_boundaries(root / "boundary")
    sessions.max_turns = 80
    route = [("game_action", {"action": "read"})]
    position = "C"
    for destination, process in (("P", False), ("A1", True), ("R", False), ("E1", True), ("C", False)):
        route.extend(("game_action", {"action": "move", "target": node})
                     for node in shortest_route(design, position, destination)[0][1:])
        position = destination
        if process:
            route.append(("game_action", {"action": "process"}))
    route.append(("game_action", {"action": "submit"}))
    model = ScriptedResponses(route, "ga", "native")
    game = StationGame("omega_00_00", design)
    result = sessions.run(game, "T1", baseline, root / "complete", model, condition="prefix")
    assert result["infrastructure_ok"] and result["success"], result.get("infrastructure_error")
    assert result["initial_session"]["native_tool_registry_unchanged"]
    assert result["initial_session"]["initial_history_size"] == 0
    assert result["initial_session"]["working"] == {}
    assert result["action_policy_rejections"] == 0
    check_feedback_delivery(root / "complete", result, model, "compact")
    completed = check_boundaries(root / "complete")
    validation = {"passed": True, "kind": "real_native_ga_single_action_scripted_contract",
                  "real_model_calls": 0, "boundary": boundary, "complete": completed,
                  "complete_game_operations": game.steps, "native_tools_unchanged": True}
    (root / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps(validation))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime", required=True)
    run(parser.parse_args())
