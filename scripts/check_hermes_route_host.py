"""Verify native Hermes/MCP multi-move execution with synthetic responses only."""

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memorybenchmark.experiments.config import RuntimeConfig
from memorybenchmark.ga_runtime import WSLJail, make_support
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_routes import shortest_route
from scripts.check_station_native_sessions import (
    ScriptedResponses,
    response_observations,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runtime-config", required=True, type=Path)
    args = parser.parse_args()
    config = RuntimeConfig.load(args.runtime_config)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    reference = args.reference_run.resolve()
    support = make_support(output / "support")
    for name in ("hermes_worker.py", "model_context.py"):
        shutil.copyfile(config.project / "memorybenchmark" / name, support / name)
    shutil.copyfile(
        config.project / "config/model-gateways.json", support / "model-gateways.json"
    )
    design = load_design(reference / "design.json")
    task = next(iter(design["tasks"]))
    start = design["tasks"][task]["start"]
    nodes = sorted({node for edge in design["public"]["edges"] for node in edge[:2]})
    paths = [shortest_route(design, start, target)[0] for target in nodes]
    path = next(route[1:4] for route in paths if len(route) >= 4)
    game = StationGame(map_world(design), design)
    jail = WSLJail(config.distro, config.native_runtime, config.runtime_dependencies)
    sessions = StationNativeSessions(
        reference / "source/hermes-agent",
        support,
        jail,
        agent="hermes",
        game_access="native",
        movement_mode="route",
        model_alias="gpt-5.6-luna",
        max_turns=3,
        final_turns=1,
        wall_seconds=180,
    )
    model = ScriptedResponses(
        [("game_action", {"action": "move", "path": path})], "hermes", "native"
    )
    result = sessions.run(
        game,
        task,
        reference / "baseline",
        output / "session",
        model,
        condition="contract",
    )
    assert result["infrastructure_ok"], result.get("infrastructure_error")
    assert (
        result["action_policy"] == "batch" and result["action_policy_rejections"] == 0
    )
    assert game.steps == len(path) and game.state.position == path[-1]
    assert any(
        response["observation"].get("steps") == len(path)
        for response in response_observations(model.requests)
    )
    receipt = {
        "passed": True,
        "real_provider_calls": 0,
        "synthetic_responses": model.calls,
        "native_hermes_mcp": True,
        "one_response_requested_moves": len(path),
        "actual_host_moves": game.steps,
        "feedback_reached_next_request": True,
        "action_policy": result["action_policy"],
        "rejections": result["action_policy_rejections"],
    }
    (output / "validation.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
