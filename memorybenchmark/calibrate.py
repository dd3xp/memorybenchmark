"""Hand-authored behavior fixtures; these are not empirical agent results."""
import json
from pathlib import Path

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .game import Game


def common_history():
    game = Game(scenario="river")
    adapter = GameAdapter(game)
    adapter.dispatch({"command": "start", "task_id": "T1"})
    # Discover the mountain connection and encounter the crossing through play.
    for target in ("J", "H", "K", "H", "J", "F", "R"):
        adapter.action("move", target)
    adapter.action("submit")
    return game.snapshot()


def calibrate(output=Path(".runs/calibration")):
    snapshot = common_history()
    results = {}
    for name, route in {"new_exploration": ("J", "U", "J", "H", "K"),
                        "repeated_block": ("J", "F", "R", "J", "H", "K")}.items():
        game = Game()
        game.restore(snapshot)
        adapter = GameAdapter(game)
        adapter.dispatch({"command": "start", "task_id": "T2"})
        for target in route:
            adapter.action("move", target)
        adapter.action("submit")
        graph = commute_graph(game.events, game.task_run_id)
        results[name] = {"success": game.success, "moves": len(graph["edges"]),
                         "distance": graph["distance"], "graph": graph,
                         "diagnostics": diagnose(game.events, game.task_run_id)}
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{name}.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
    (output / "comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(calibrate(), ensure_ascii=False, indent=2))
