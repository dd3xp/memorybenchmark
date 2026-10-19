"""Standard stdio MCP endpoint for a single runner-selected game task."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import uuid4

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .game import Game
from .game_session import dispatch_current
from .mcp_game import create_server, require_mcp, transport_identity


async def serve(adapter):
    from mcp.server.stdio import stdio_server
    server = create_server(lambda request: dispatch_current(adapter, request))
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cartographer's Notebook: task-scoped stdio MCP service")
    parser.add_argument("--scenario", choices=("lake-easy", "valley", "river"), default="lake-easy")
    parser.add_argument("--task", default="T1", help="host-selected task; cannot be changed through tools")
    parser.add_argument("--output", type=Path, help="private host directory for this single-task play log")
    args = parser.parse_args(argv)
    try:
        require_mcp()
    except RuntimeError as error:
        parser.error(str(error))
    game = Game(scenario=args.scenario)
    if args.task not in game.tasks:
        parser.error("unknown task for this scenario")
    output = args.output or Path(".runs/mcp-play") / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    game.log_path = output / "events.jsonl"
    adapter = GameAdapter(game)
    initial = adapter.dispatch({"command": "start", "task_id": args.task})
    (output / "initial-public.json").write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
    # stdout belongs exclusively to the MCP transport, including on Windows.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        asyncio.run(serve(adapter))
    finally:
        (output / "summary.json").write_text(json.dumps({
            "kind": "mcp_single_task_play_not_memory_evaluation", **transport_identity(),
            "task_id": args.task, "done": game.done, "success": game.success,
            "game_actions": game.steps}, ensure_ascii=False), encoding="utf-8")
        (output / "graph.json").write_text(json.dumps({
            "graph": commute_graph(game.events, game.task_run_id),
            "diagnostics": diagnose(game.events, game.task_run_id)}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
