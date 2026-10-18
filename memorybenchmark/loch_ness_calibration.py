"""Replay the Easy curriculum using full-information plans, not an agent run."""
import json
from pathlib import Path

from .adapters import GameAdapter
from .analysis import commute_graph
from .game import Game
from .validation import validate
from .worlds import load_scenario


def calibrate(output=Path(".runs/loch-ness-calibration")):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    world, tasks = load_scenario("loch-ness")
    reference = validate(world, tasks)
    game = Game(scenario="loch-ness", log_path=output / "events.jsonl")
    if game.log_path.exists():
        raise ValueError("校准输出已存在，请使用新目录保留原始记录。")
    adapter, rows = GameAdapter(game), []
    for task_id, result in reference.items():
        game.start_task(task_id)
        plan = result["with_tool_options"]
        for action in plan["actions"]:
            adapter.action(action["type"], action.get("target"))
        if not game.success or game.effort != plan["effort"]:
            raise AssertionError("reference replay diverged")
        graph = commute_graph(game.events, game.task_run_id)
        rows.append({"task_id": task_id, "success": game.success, "effort": game.effort,
                     "distance": game.distance, "steps": game.steps, "remaining_stamina": game.stamina,
                     "hazard_encounters": sum(e["hazard_cost"] > 0 for e in graph["edges"]),
                     "tools": sorted(game.inventory), "submit_camp": game.position,
                     "no_tool_reference_effort": result["without_taking_tools"]["effort"],
                     "actions": plan["actions"]})
    report = {"kind": "full_information_rule_calibration_not_agent_experiment",
              "world_version": world["version"], "nodes": len(world["locations"]),
              "edges": len(world["edges"]), "cycle_rank": len(world["edges"])-len(world["locations"])+1,
              "tasks": rows, "submitted_atlas": game.observer_atlas()}
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse, sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".runs/loch-ness-calibration"))
    args = parser.parse_args()
    report = calibrate(args.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ("tasks", "submitted_atlas")}, ensure_ascii=False))
    for row in report["tasks"]:
        print(json.dumps({k:v for k,v in row.items() if k != "actions"}, ensure_ascii=False))
