"""Hand-authored preparation fixtures, never empirical memory evaluation."""
import json
from pathlib import Path

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .game import Game
from .validation import validate


def tool_history():
    game = Game()
    adapter = GameAdapter(game)
    adapter.dispatch({"command": "start", "task_id": "T1"})
    for target in ("J", "A", "J", "D"):
        adapter.action("move", target)
    adapter.action("take", "snow_kit")
    adapter.action("move", "A")
    adapter.action("submit")
    return game.snapshot()


def calibrate_tools(output=Path(".runs/tool-calibration")):
    prefix = tool_history()
    plans = {
        "prepared": [("move", "J"), ("move", "D"), ("take", "snow_kit"), ("move", "A"), ("move", "K")],
        "unprepared": [("move", "J"), ("move", "A"), ("move", "K")],
        "avoid_hazard": [("move", "J"), ("move", "H"), ("move", "K")],
        "belated_preparation": [("move", "J"), ("move", "A"), ("move", "J"), ("move", "D"), ("take", "snow_kit"), ("move", "A"), ("move", "K")],
    }
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, plan in plans.items():
        game = Game()
        game.restore(prefix)
        adapter = GameAdapter(game)
        adapter.dispatch({"command": "start", "task_id": "T2"})
        for action, target in plan:
            adapter.action(action, target)
        adapter.action("submit")
        results[name] = {"success": game.success, "distance": game.distance, "effort": game.effort,
                         "remaining_stamina": game.stamina, "graph": commute_graph(game.events, game.task_run_id),
                         "diagnostics": diagnose(game.events, game.task_run_id)}
        (output / f"{name}.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
    (output / "comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "feasibility.json").write_text(json.dumps(validate(game.world, game.tasks), ensure_ascii=False, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    result = calibrate_tools()
    print(json.dumps({k: {field: value for field, value in row.items() if field not in ("graph", "diagnostics")}
                      for k, row in result.items()}, ensure_ascii=False, indent=2))
