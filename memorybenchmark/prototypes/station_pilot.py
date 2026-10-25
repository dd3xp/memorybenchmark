"""Isolated native GA pilot for the station mechanism, separate from live game.

Each current-task clear probe starts at the retained branch's actual checkpoint.
It is not an independently evolving NOMEM stream. No reference planner controls GA.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from secrets import choice

from ..agent_sessions import WorkerSessions
from ..errors import InfrastructureError
from ..ga_runtime import WSLJail, changed_files, copy_memory, extract_native, make_support, memory_manifest
from ..mcp_game import MCPGameClient
from ..model_gateway import GatewayModel
from ..watch import atomic_json as save_json
from .station_capability import StationGame, compatible_worlds, load_design
from .station_session import DEFAULT_DESIGN, StationSession
from scripts.check_station_capability import trace_graph, render_svg


PROMPT_PROTOCOL = "station-native-memory-1"
STATION_TOOL = {
    "name": "game_action",
    "description": "操作当前测绘委托。move 到相邻地点，到目标自动采集本次资料；inspect 查询当前站能力；process 在当前站尝试处理本次资料；submit 回指定营地提交；read 读取当前公开状态。结束后用原生工具自主整理经验。",
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["move", "inspect", "process", "submit", "abandon", "read"]},
        "target": {"type": "string", "description": "仅 move 传相邻地点 ID；其他动作不传。"}},
        "required": ["action"], "additionalProperties": False},
}
GUIDE = """
你正在完成测绘游戏的一项委托。游戏只通过 game_action 访问，没有网页、人工或真实桌面。
只操作当前委托；未来委托不提前提供。到目标自动采集本次原始资料，需要在支持该种资料的站处理，再回指定营地提交。
inspect 是在站查询能力；process 是处理当前原始资料。两者都会给出实际反馈，不支持的处理保留资料。
每项委托开始新的会话；历史对话、工作记忆和临时文件不保留。只有你自主保存到 ../memory/ 的经验跨会话传递。
公开地理图不会保存历史能力分配或处理反馈。地点能力在同一世界跨委托保持不变。
开始前请检查自己已有的相关经验，再结合当前公开状态判断是否适用。
结束后复盘实际经历；有可迁移经验时使用原生工具保存、更新或纠正，内容与组织方式由你决定。
普通回复不会持久保存；不必强行新增无价值条目。done=true 后停止游戏操作，整理后结束。
当前任务要求会在每次反馈和每次模型请求中出现；状态以最新反馈为准，不确定时 read。
"""


class StationNativeSessions(WorkerSessions):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, worker_protocol="ga-session-1", worker_filename="ga_worker.py",
                         prompt_protocol=PROMPT_PROTOCOL, **kwargs)

    def run(self, game, task_id, input_memory, output, model, *, condition):
        from uuid import uuid4
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        before_history = deepcopy(game.events)
        before = memory_manifest(input_memory)
        state = self.support.parent / "live-state" / uuid4().hex
        state.parent.mkdir(parents=True, exist_ok=True)
        copy_memory(input_memory, state)
        save_json(output / "memory-before.json", before)
        save_json(output / "prior-events.json", before_history)
        adapter = StationSession(game, task_id)
        initial = adapter.initial
        save_json(output / "initial-public.json", initial)
        config = self.task_config(initial)
        config.update(task_reminder=initial["text"].splitlines()[0], game_guide=GUIDE,
                      game_tool=STATION_TOOL, game_target_actions=["move"], prompt_protocol=PROMPT_PROTOCOL)
        config["initial_text"] += "\n公开地图与规则：" + json.dumps(initial["observation"]["environment"], ensure_ascii=False)
        with MCPGameClient(adapter.dispatch, definition=STATION_TOOL, target_actions=("move",)) as client:
            report = self._worker(state, output, config, adapter, model, game_client=client)
            report.update(client.identity)
        if report["infrastructure_ok"]:
            after = copy_memory(state, output / "memory-after")
            report.update(input_memory=before, output_memory=after,
                          memory_changed=changed_files(before, after),
                          content_changed=[p for p in changed_files(before, after) if p != "file_access_stats.json"])
        report.update(task_id=task_id, condition=condition, prompt_protocol=PROMPT_PROTOCOL,
                      success=game.state.success if report["infrastructure_ok"] else None,
                      done=game.done, game_actions=game.steps, distance=game.distance,
                      prior_compatible_worlds=list(compatible_worlds(game.design, before_history)),
                      after_compatible_worlds=list(compatible_worlds(game.design, game.events)))
        graph = trace_graph(game)
        save_json(output / "graph.json", graph)
        (output / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n"
            for e in game.events), encoding="utf-8")
        (output / "graph.svg").write_text(render_svg(game.design, graph, f"Native GA / {task_id} / {condition}"), encoding="utf-8")
        save_json(output / "summary.json", report)
        return report


def replay_checkpoint(design, world, sessions):
    """Rebuild only the canonical actual history, without restoring conversation."""
    game = StationGame(world, design)
    for folder in sessions:
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        game.start_task(summary["task_id"])
        events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        run_id = max((e["task_run_id"] for e in events), key=lambda value: int(value.split("-")[-1]))
        for event in events:
            if event["task_run_id"] != run_id:
                continue
            if event["kind"] == "action":
                delivered = game.step(event["action"])
                if delivered != event["delivered"]:
                    raise RuntimeError("Checkpoint replay differs from recorded feedback")
            elif event["kind"] == "runner_terminated":
                game.finish_incomplete(event["delivered"]["feedback"]["reason"])
        if not game.done:
            raise RuntimeError("Incomplete canonical checkpoint")
    return game


def pilot(archive, output, jail, model, *, seed=20261025, model_alias="gpt-5.6-luna", tasks=None,
          max_turns=40, final_turns=6, resume=False, world=None):
    output = Path(output).resolve()
    design = load_design(DEFAULT_DESIGN)
    if world is not None and world not in design["private_worlds"]:
        raise ValueError("Unknown private world fixture")
    tasks = list(tasks or design["tasks"])
    if not tasks or len(set(tasks)) != len(tasks) or any(t not in design["tasks"] for t in tasks):
        raise ValueError("Tasks must be unique members of this design")
    if resume:
        report = json.loads((output / "pilot.json").read_text(encoding="utf-8"))
        if world is not None and world != report["world"]:
            raise ValueError("Cannot change the private world when resuming")
        for path, digest in report["implementation_sha256"].items():
            if sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise RuntimeError("Pilot source changed; do not resume this run")
        design = json.loads((output / "design.json").read_text(encoding="utf-8"))
        tasks, seed, model_alias = report["tasks"], report["seed"], report["model_alias"]
        max_turns, final_turns = report["max_turns"], report["final_turns"]
    else:
        output.mkdir(parents=True, exist_ok=False)
        source = extract_native(archive, output / "source")
        copy_memory(source / "memory", output / "baseline")
        make_support(output / "support")
        paths = [Path(__file__), DEFAULT_DESIGN, Path(__file__).with_name("station_capability.py"),
                 Path(__file__).with_name("station_session.py")]
        paths += [Path(__file__).parents[1] / name for name in
                  ("ga_worker.py", "agent_bridge.py", "mcp_game.py", "agent_sessions.py", "ga_runtime.py", "model_gateway.py")]
        report = {"protocol": "station-native-pilot-1", "status": "running", "seed": seed,
                  "model_alias": model_alias, "tasks": tasks, "max_turns": max_turns, "final_turns": final_turns,
                  # The worker receives its RNG seed; hidden-world sampling must
                  # be independent so that seed cannot disclose the assignment.
                  "world": world if world is not None else choice(sorted(design["private_worlds"])),
                  "world_sampling": ("host-selected private fixture independent of worker seed" if world is not None
                                     else "host-private choice independent of worker seed"),
                  "comparison": "current-task clear probes at retained actual-history checkpoints",
                  "archive_sha256": sha256(Path(archive).read_bytes()).hexdigest(),
                  "implementation_sha256": {str(p.resolve()): sha256(p.read_bytes()).hexdigest() for p in paths},
                  "sessions": []}
        save_json(output / "design.json", design)
        save_json(output / "pilot.json", report)
    sessions = StationNativeSessions(output / "source" / "GenericAgent", output / "support", jail,
                                     model_alias=model_alias, seed=seed, max_turns=max_turns, final_turns=final_turns)
    if not (output / "probe" / "summary.json").exists():
        sessions.probe(output / "baseline", output / "probe")
    canonical = []
    memory = output / "baseline"
    game = StationGame(report["world"], design)
    try:
        for index, task_id in enumerate(tasks):
            checkpoint = deepcopy(game)
            for condition in (("prefix",) if index == 0 else ("retain", "clear")):
                name = f"{index + 1:02d}-{task_id}-{condition}"
                folder = output / "sessions" / name
                recorded = next((s for s in report["sessions"] if s["name"] == name), None)
                if recorded and not recorded["infrastructure_ok"]:
                    # Verify both absolute paths before moving a Windows directory.
                    source_path = folder.resolve(strict=True)
                    attempts = output / "failed-attempts"
                    attempts.mkdir(exist_ok=True)
                    target_path = (attempts / (name + "-" + str(len(report.get("attempt_history", [])) + 1))).resolve()
                    if not source_path.is_relative_to(output) or not target_path.is_relative_to(output):
                        raise ValueError("Attempt archive escaped the pilot directory")
                    if target_path.exists():
                        raise FileExistsError("Attempt archive already exists")
                    source_path.rename(target_path)
                    report.setdefault("attempt_history", []).append({**recorded, "archived_at": str(target_path.relative_to(output))})
                    report["sessions"].remove(recorded)
                    recorded = None
                    save_json(output / "pilot.json", report)
                if recorded:
                    result = recorded
                else:
                    current = deepcopy(checkpoint)
                    result = sessions.run(current, task_id, memory if condition != "clear" else output / "baseline",
                                          folder, model, condition=condition)
                    result = {"name": name, **result}
                    report["sessions"].append(result)
                    save_json(output / "pilot.json", report)
                if not result["infrastructure_ok"]:
                    raise InfrastructureError(result.get("infrastructure_error", "Native session failed"))
                print(json.dumps({k: result[k] for k in ("name", "success", "distance", "llm_calls", "content_changed")}, ensure_ascii=False), flush=True)
                if condition != "clear":
                    canonical.append(folder)
                    game = replay_checkpoint(design, report["world"], canonical)
                    memory = folder / "memory-after"
        report["status"] = "completed"
    except Exception:
        report["status"] = "interrupted"
        save_json(output / "pilot.json", report)
        raise
    save_json(output / "pilot.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--tasks", nargs="+")
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--final-turns", type=int, default=6)
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--world", help="private host fixture for a controlled rerun; never sent to the worker")
    args = parser.parse_args()
    key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
    if not key:
        parser.error("Set MEMORYBENCH_GATEWAY_KEY in the parent host, never the native worker")
    if args.max_output_tokens < 0:
        parser.error("max-output-tokens must be nonnegative")
    read_model = args.model
    if args.resume:
        read_model = json.loads((args.output / "pilot.json").read_text(encoding="utf-8"))["model_alias"]
    model = GatewayModel(args.base_url, key, read_model, args.max_output_tokens or None)
    pilot(args.archive, args.output, WSLJail(args.distro), model, seed=args.seed, model_alias=args.model,
          tasks=args.tasks, max_turns=args.max_turns, final_turns=args.final_turns, resume=args.resume, world=args.world)


if __name__ == "__main__":
    main()
