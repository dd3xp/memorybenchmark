"""Isolated native GA pilot for the station mechanism, separate from live game.

Each current-task clear probe starts at the retained branch's actual checkpoint.
New pilots run both conditions for every task, including the no-history first
task. Frozen legacy pilots retain their original schedule on resume. The clear
condition is not an independently evolving stream. No reference planner controls GA.
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
from ..decision_gate import ACTION_POLICIES, SINGLE_ACTION_GUIDE
from ..ga_runtime import WSLJail, changed_files, copy_memory, extract_native, make_support, memory_manifest
from ..mcp_game import MCPGameClient
from ..model_gateway import GatewayModel
from ..watch import atomic_json as save_json
from .station_capability import StationGame, compatible_worlds, load_design
from .station_session import DEFAULT_DESIGN, FEEDBACK_PROTOCOLS, StationSession
from scripts.check_station_capability import trace_graph, render_svg


PROMPT_PROTOCOL = "station-native-memory-3"
MOVEMENT_MODES = ("step", "route")
ROUTE_GUIDE = """
move 可用 path 一次提供 1–32 个依次相邻的地点 ID（不含当前位置），与单步 target 二选一；其他动作不传 path。
环境仅按给定顺序移动，不自动寻路。每步正常计操作、路程和图边，并在 responses 中返回逐步反馈；遇错误或 done=true 停止。
可自主选择单步或连续移动；需要根据新反馈决策时结束本次路径，再调用工具。
"""
STATION_TOOL = {
    "name": "game_action",
    "description": "操作当前测绘委托。move 到相邻地点，到目标自动采集本次资料；inspect 查询当前站能力；process 在当前站尝试处理本次资料；submit 回指定营地提交；read 查询完整公开地图和当前状态，不消耗游戏操作。结束后用原生工具自主整理经验。",
    "parameters": {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["move", "inspect", "process", "submit", "abandon", "read"]},
        "target": {"type": "string", "description": "仅 move 传相邻地点 ID；其他动作不传。"}},
        "required": ["action"], "additionalProperties": False},
}
GUIDE = """
你正在完成测绘游戏的一项委托。游戏只通过 game_action 访问，没有网页、人工或真实桌面。
只操作当前委托；未来委托不提前提供。按当前委托的公开行程逐段完成：到目标自动采集当前段资料，在支持该种资料的站处理；全部行程完成后回指定营地提交。处理一段成功不一定代表整项委托结束，以最新公开进度为准。
inspect 是在站查询能力；process 是处理当前原始资料。两者都会给出实际反馈，不支持的处理保留资料。
每项委托开始新的会话；历史对话、工作记忆和临时文件不保留。只有你自主保存到 ../memory/ 的经验跨会话传递。
公开地理图不会保存历史能力分配或处理反馈。地点能力在同一世界跨委托保持不变。
开始前请检查自己已有的相关经验，再结合当前公开状态判断是否适用。
结束后复盘实际经历；有可迁移经验时使用原生工具保存、更新或纠正，内容与组织方式由你决定。
普通回复不会持久保存；不必强行新增无价值条目。done=true 后停止游戏操作，整理后结束。
当前任务要求会在每次反馈和每次模型请求中出现；状态以最新反馈为准，不确定时 read。
开局提供完整公开地图；需要再次查看地图与规则时可用 read，不消耗游戏操作。
"""


def movement_tool(mode):
    if mode not in MOVEMENT_MODES:
        raise ValueError("Unknown movement mode")
    definition = deepcopy(STATION_TOOL)
    if mode == "route":
        definition["parameters"]["properties"]["path"] = {
            "type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 32,
            "description": "仅 move：依次相邻的地点 ID 列表，不含当前位置，与 target 二选一；每步正常计费并返回反馈，错误或任务结束时停止。"}
        definition["description"] += "move 也可传 path 连续移动，由你指定每一个相邻地点；每一步分别计操作和路程，不自动规划。"
    return definition


def access_guide(agent, game_access):
    """Change only public interface instructions, never supply experience."""
    if game_access == "bridge":
        return GUIDE
    if game_access != "native":
        raise ValueError("Unknown game access mode")
    if agent == "ga":
        access = ("游戏通过你原生的 code_run 工具调用预置客户端访问：执行 "
                  "python -m game_client move J 可移动到 J；inspect、process、submit、read 等不带地点参数。"
                  "也可在 Python 中 from game_client import action; print(action('move', target='J'))。"
                  "客户端只执行指定操作并返回公开反馈，不会规划路线、查询记忆或自动补充动作。")
    else:
        access = "游戏通过你原生 MCP 客户端发现的游戏工具访问（服务 cartography，服务端工具 game_action）；以客户端发现后的工具名称为准。"
    return GUIDE.replace("游戏只通过 game_action 访问，", access + "游戏中")


class StationNativeSessions(WorkerSessions):
    def __init__(self, *args, agent="ga", feedback_mode="compact", game_access="bridge", action_policy="single", movement_mode="step", **kwargs):
        if feedback_mode not in FEEDBACK_PROTOCOLS:
            raise ValueError("Unknown station feedback mode")
        self.agent = agent
        self.feedback_mode = feedback_mode
        if game_access not in ("bridge", "native"):
            raise ValueError("Unknown game access mode")
        self.game_access = game_access
        if action_policy not in ACTION_POLICIES:
            raise ValueError("Unknown game action policy")
        self.action_policy = action_policy
        if movement_mode not in MOVEMENT_MODES or (movement_mode == "route" and (agent != "hermes" or game_access != "native")):
            raise ValueError("Route movement requires native Hermes")
        self.movement_mode = movement_mode
        super().__init__(*args, worker_protocol=("ga-session-1" if agent == "ga" else "hermes-session-1"),
                         worker_filename=("ga_worker.py" if agent == "ga" else "hermes_worker.py"),
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
        deliveries_path = output / "game-deliveries.jsonl"
        with deliveries_path.open("w", encoding="utf-8") as deliveries:
            def record_delivery(request, response):
                deliveries.write(json.dumps({"request": request, "response": response}, ensure_ascii=False) + "\n")
                deliveries.flush()
            adapter = StationSession(game, task_id, feedback_mode=self.feedback_mode, on_delivery=record_delivery)
            initial = adapter.initial
            save_json(output / "initial-public.json", initial)
            config = self.task_config(initial)
            config.update(task_reminder=initial["text"].splitlines()[0], game_guide=access_guide(self.agent, self.game_access),
                          game_access=self.game_access,
                          game_tool=movement_tool(self.movement_mode), game_target_actions=["move"], prompt_protocol=PROMPT_PROTOCOL,
                          movement_mode=self.movement_mode)
            if self.movement_mode == "route":
                config["game_guide"] += ROUTE_GUIDE
            if self.action_policy == "single":
                config.update(action_policy="single", game_guide=config["game_guide"] + SINGLE_ACTION_GUIDE)
            config["initial_text"] += "\n公开地图与规则：" + json.dumps(initial["observation"]["environment"], ensure_ascii=False)
            with MCPGameClient(adapter.dispatch, definition=STATION_TOOL, target_actions=("move",)) as client:
                report = self._worker(state, output, config, adapter, model, game_client=client)
                report.update(client.identity)
        report.update(feedback_mode=self.feedback_mode, feedback_protocol=FEEDBACK_PROTOCOLS[self.feedback_mode],
                      game_deliveries_sha256=sha256(deliveries_path.read_bytes()).hexdigest())
        if report["infrastructure_ok"]:
            after = copy_memory(state, output / "memory-after")
            report.update(input_memory=before, output_memory=after,
                          memory_changed=changed_files(before, after),
                          content_changed=[p for p in changed_files(before, after) if p != "file_access_stats.json"])
        report.update(task_id=task_id, condition=condition, prompt_protocol=PROMPT_PROTOCOL,
                      movement_mode=self.movement_mode,
                      game_access=self.game_access,
                      success=game.state.success if report["infrastructure_ok"] else None,
                      done=game.done, game_actions=game.steps, distance=game.distance,
                      prior_compatible_worlds=list(compatible_worlds(game.design, before_history)),
                      after_compatible_worlds=list(compatible_worlds(game.design, game.events)))
        if game.design.get("evaluation", {}).get("experience_protocol") == "station-experience-opportunity-1":
            from .station_experience import experience_opportunities
            report["experience_opportunities"] = experience_opportunities(game.design, game.events, game.task_run_id)
        graph = trace_graph(game)
        save_json(output / "graph.json", graph)
        (output / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n"
            for e in game.events), encoding="utf-8")
        label = {"ga": "GA", "hermes": "Hermes"}[self.agent]
        (output / "graph.svg").write_text(render_svg(game.design, graph, f"Native {label} / {task_id} / {condition}"), encoding="utf-8")
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
          max_turns=None, final_turns=6, wall_seconds=None, resume=False, world=None, design_path=None, agent="ga", feedback_mode=None,
          game_access=None, action_policy=None, clear_first_task=None, movement_mode=None):
    if agent not in ("ga", "hermes"):
        raise ValueError("unsupported native agent")
    if feedback_mode is not None and feedback_mode not in FEEDBACK_PROTOCOLS:
        raise ValueError("Unknown station feedback mode")
    if game_access is not None and game_access not in ("bridge", "native"):
        raise ValueError("Unknown game access mode")
    if action_policy is not None and action_policy not in ACTION_POLICIES:
        raise ValueError("Unknown game action policy")
    if clear_first_task is not None and type(clear_first_task) is not bool:
        raise ValueError("clear_first_task must be boolean")
    if movement_mode is not None and movement_mode not in MOVEMENT_MODES:
        raise ValueError("Unknown movement mode")
    output = Path(output).resolve()
    selected_design = Path(design_path) if design_path is not None else DEFAULT_DESIGN
    if resume:
        report = json.loads((output / "pilot.json").read_text(encoding="utf-8"))
        if report.get("agent", "ga") != agent:
            raise ValueError("Cannot change native agent when resuming")
        recorded_access = report.get("game_access", "bridge")
        if game_access is not None and game_access != recorded_access:
            raise ValueError("Cannot change game access mode when resuming")
        game_access = recorded_access
        recorded_policy = report.get("action_policy", "batch")
        if action_policy is not None and action_policy != recorded_policy:
            raise ValueError("Cannot change game action policy when resuming")
        action_policy = recorded_policy
        recorded_movement = report.get("movement_mode", "step")
        if movement_mode is not None and movement_mode != recorded_movement:
            raise ValueError("Cannot change movement mode when resuming")
        movement_mode = recorded_movement
        recorded_clear_first = report.get("clear_first_task", False)
        if clear_first_task is not None and clear_first_task != recorded_clear_first:
            raise ValueError("Cannot change first-task control when resuming")
        clear_first_task = recorded_clear_first
        if world is not None and world != report["world"]:
            raise ValueError("Cannot change the private world when resuming")
        recorded_feedback = report.get("feedback_mode", "full")
        if feedback_mode is not None and feedback_mode != recorded_feedback:
            raise ValueError("Cannot change feedback mode when resuming")
        feedback_mode = recorded_feedback
        recorded_wall = report.get("wall_seconds", 900)
        if wall_seconds is not None and wall_seconds != recorded_wall:
            raise ValueError("Cannot change the wall-clock budget when resuming")
        wall_seconds = recorded_wall
        for path, digest in report["implementation_sha256"].items():
            if sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise RuntimeError("Pilot source changed; do not resume this run")
        design = json.loads((output / "design.json").read_text(encoding="utf-8"))
        tasks, seed, model_alias = report["tasks"], report["seed"], report["model_alias"]
        max_turns, final_turns = report["max_turns"], report["final_turns"]
        report["status"] = "running"
        save_json(output / "pilot.json", report)
    else:
        game_access = game_access or "native"
        action_policy = action_policy or "single"
        movement_mode = movement_mode or "step"
        if movement_mode == "route" and (agent != "hermes" or game_access != "native"):
            raise ValueError("Route movement requires native Hermes")
        clear_first_task = True if clear_first_task is None else clear_first_task
        if action_policy != "single" or movement_mode != "step":
            raise ValueError("New station pilots require single actions and step movement; batch/route are historical configurations only")
        feedback_mode = feedback_mode or "compact"
        design = load_design(selected_design)
        if max_turns is None:
            max_turns = design.get("native_session_budget", {}).get("main_model_calls", 40)
        if wall_seconds is None:
            wall_seconds = design.get("native_session_budget", {}).get("wall_seconds", 900)
        if type(max_turns) is not int or max_turns < 1 or type(final_turns) is not int or final_turns < 0:
            raise ValueError("Native call budgets must be positive main calls and nonnegative final calls")
        if type(wall_seconds) is not int or not 10 <= wall_seconds <= 3600:
            raise ValueError("Native wall-clock budget must be 10..3600 seconds")
        if world is not None and world not in design["private_worlds"]:
            raise ValueError("Unknown private world fixture")
        tasks = list(tasks or design["tasks"])
        if not tasks or len(set(tasks)) != len(tasks) or any(t not in design["tasks"] for t in tasks):
            raise ValueError("Tasks must be unique members of this design")
        output.mkdir(parents=True, exist_ok=False)
        if agent == "ga":
            source = extract_native(archive, output / "source")
            copy_memory(source / "memory", output / "baseline")
            make_support(output / "support")
        else:
            from ..agent_adapters import load_adapter
            load_adapter(agent).prepare(archive, output)
        paths = [Path(__file__), selected_design, Path(__file__).with_name("station_capability.py"),
                 Path(__file__).with_name("station_session.py")]
        if design.get("evaluation", {}).get("experience_protocol") == "station-experience-opportunity-1":
            paths += [Path(__file__).with_name(name) for name in
                      ("station_experience.py", "station_choice.py", "station_routes.py")]
        paths += [Path(__file__).parents[1] / name for name in
                  ("ga_worker.py", "agent_bridge.py", "mcp_game.py", "agent_sessions.py", "ga_runtime.py", "model_gateway.py",
                   "game_client.py", "native_game_io.py", "game_mcp_stdio.py", "decision_gate.py")]
        if agent == "hermes":
            paths += [Path(__file__).parents[1] / "hermes_worker.py", Path(__file__).parents[1] / "agents/hermes.py"]
        report = {"protocol": "station-native-pilot-1", "agent": agent, "status": "running", "seed": seed, "design_id": design["design_id"],
                  "model_alias": model_alias, "tasks": tasks, "max_turns": max_turns, "final_turns": final_turns,
                  "wall_seconds": wall_seconds, "prompt_protocol": PROMPT_PROTOCOL,
                  "feedback_mode": feedback_mode, "feedback_protocol": FEEDBACK_PROTOCOLS[feedback_mode],
                  "game_access": game_access,
                  "action_policy": action_policy,
                  "movement_mode": movement_mode,
                  "clear_first_task": clear_first_task,
                  "agent_game_interface": ("ga-code-run-client-1" if agent == "ga" else "hermes-native-mcp-1")
                                          if game_access == "native" else "native-tool-bridge-1",
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
    sessions = StationNativeSessions(output / "source" / ("GenericAgent" if agent == "ga" else "hermes-agent"), output / "support", jail,
                                     agent=agent, feedback_mode=feedback_mode, game_access=game_access, action_policy=action_policy,
                                     movement_mode=movement_mode,
                                     model_alias=model_alias, seed=seed, max_turns=max_turns, final_turns=final_turns,
                                     wall_seconds=wall_seconds)
    if not (output / "probe" / "summary.json").exists():
        sessions.probe(output / "baseline", output / "probe")
    canonical = []
    memory = output / "baseline"
    game = StationGame(report["world"], design)
    try:
        for index, task_id in enumerate(tasks):
            checkpoint = deepcopy(game)
            conditions = ("prefix", "clear") if clear_first_task else ("prefix",)
            for condition in (conditions if index == 0 else ("retain", "clear")):
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
    parser.add_argument("--agent", choices=("ga", "hermes"), default="ga")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--tasks", nargs="+")
    parser.add_argument("--max-turns", type=int, help="override map-specific main model-call budget; legacy maps default to 40")
    parser.add_argument("--final-turns", type=int, default=6)
    parser.add_argument("--wall-seconds", type=int, help="per-session wall-clock limit including native review; map-specific, legacy default 900")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--runtime")
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--world", help="private host fixture for a controlled rerun; never sent to the worker")
    parser.add_argument("--design", type=Path, help="map configuration; defaults to the original eight-task prototype")
    parser.add_argument("--feedback-mode", choices=("compact", "full"), help="new runs default to compact action results; initial/read always include the full public map; frozen on resume")
    parser.add_argument("--game-access", choices=("native", "bridge"), help="new station pilots default to native GA code_run / Hermes MCP; bridge preserves the previous custom game_action interface; frozen on resume")
    parser.add_argument("--action-policy", choices=ACTION_POLICIES, help="new GA/Hermes runs use single: one game-action attempt per model response; batch is only for resuming historical runs")
    parser.add_argument("--movement-mode", choices=MOVEMENT_MODES, help="new runs use step: move to one adjacent location; route is only for resuming historical runs")
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
    pilot(args.archive, args.output, WSLJail(args.distro, args.runtime, args.runtime_dependency), model, seed=args.seed, model_alias=args.model,
          tasks=args.tasks, max_turns=args.max_turns, final_turns=args.final_turns, resume=args.resume, world=args.world,
          design_path=args.design, agent=args.agent, wall_seconds=args.wall_seconds, feedback_mode=args.feedback_mode,
          game_access=args.game_access, action_policy=args.action_policy, movement_mode=args.movement_mode)


if __name__ == "__main__":
    main()
