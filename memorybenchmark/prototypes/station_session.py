"""Task-scoped prototype RPC and terminal play; not a native memory experiment.

JSON Lines exposes only read/action for a host-selected task. Human mode can
advance through the catalog. Neither mode exposes evaluator files as tools.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from secrets import choice
import sys
from uuid import uuid4

from .station_capability import StationGame, capability_groups, load_design, neighbors


DEFAULT_DESIGN = Path(__file__).resolve().parents[2] / "design" / "station_capability_v2.json"
EASY20_DESIGN = Path(__file__).resolve().parents[1] / "data" / "station_easy20.json"
EASY20_CHOICE_DESIGN = Path(__file__).resolve().parents[1] / "data" / "station_easy20_choice.json"


def render_text(response):
    observation, feedback = response["observation"], response["feedback"]
    public, task = observation["environment"], observation["task"]
    kind = public["kinds"][task["required_kind"]]
    groups = "；".join("/".join(group["stations"]) + "：" + "/".join(public["kinds"][k] for k in group["kinds"])
                       + ("各两站" if len(group["stations"]) == 4 else "各一站")
                       for group in capability_groups({"public": public}).values())
    routes = "；".join(f"{node}（距离 {distance}）" for node, distance in neighbors({"public": public}, observation["location"]))
    message = {"started": "新委托开始。", "current_observation": "当前观察。", "arrived": "已到达。",
               "not_ready": "本次原始资料尚未采集并处理，不能提交。", "submitted": "本次委托完成。",
               "abandoned": "本次委托已放弃。"}.get(feedback["kind"], "")
    if feedback["kind"] == "station_information":
        message = f'{feedback["station"]} 支持{public["kinds"][feedback["capability"]]}。'
        if "result" in feedback:
            message += "本次资料已处理。" if feedback["result"] == "processed" else "不支持本次资料，原始资料保留。"
    if feedback.get("raw_collected"):
        message += "已自动采集本次原始资料。"
    if feedback.get("termination") == "budget_exhausted":
        message += "操作预算耗尽，委托结束；本次反馈仍已交付。"
    return (f"当前委托 {task['id']}：到 {task['target']} 采集{kind}，在支持该资料的站处理，再回 {task['submit_at']} 提交。\n"
            f"当前位置：{observation['location']}；原始资料：{'已采集' if observation['raw'] else '未采集'}；"
            f"处理：{'已完成' if observation['processed'] else '未完成'}。\n"
            f"公开能力范围（不代表已知分配）：{groups}。\n通路：{routes}\n"
            f"操作 {observation['steps']}/{task['max_steps']}；距离 {observation['distance']}；版本 {observation['revision']}。\n"
            f"可用动作：{json.dumps(observation['available_actions'], ensure_ascii=False)}\n"
            f"反馈：{message}\n结束：{observation['done']}；成功：{observation['success']}")


class StationSession:
    """Thin current-task adapter, with exact request replay and no memory policy."""
    def __init__(self, game, task_id):
        self.game = game
        self.revision = 0
        self.requests = {}
        response = game.start_task(task_id)
        self._bound_run_id = game.task_run_id
        self.initial = self._public(response)

    def _public(self, response):
        response = deepcopy(response)
        response["observation"]["revision"] = self.revision
        response["text"] = render_text(response)
        return response

    def dispatch(self, request):
        if self.game.task_run_id != self._bound_run_id:
            return {"error": "session_closed", "message": "原委托已关闭，此连接不能访问下一委托。"}
        error = {"error": "invalid_request", "message": "只接受当前委托的 read 或 action 请求。"}
        if not isinstance(request, dict):
            return error
        command = request.get("command")
        if command == "read":
            if set(request) != {"command"}:
                return error
            return self._public({"observation": self.game.observation(), "feedback": {"kind": "current_observation"}})
        if command != "action" or set(request) - {"command", "action", "request_id", "expected_revision"}:
            return error
        request_id, action = request.get("request_id"), request.get("action")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            return {"error": "invalid_request", "message": "动作需要长度为 1–128 的 request_id。"}
        if not isinstance(action, dict) or set(action) - {"type", "target"}:
            return error
        if action.get("type") not in ("move", "inspect", "process", "submit", "abandon"):
            return error
        if (action["type"] == "move" and not isinstance(action.get("target"), str)) or (
                action["type"] != "move" and "target" in action):
            return error
        expected = request.get("expected_revision")
        if "expected_revision" in request and (type(expected) is not int or expected < 0):
            return {"error": "invalid_request", "message": "expected_revision 必须是非负整数。"}
        signature = json.dumps({"action": action, "expected_revision": expected}, sort_keys=True)
        if request_id in self.requests:
            previous, result = self.requests[request_id]
            return deepcopy(result) if previous == signature else {"error": "request_conflict", "message": "同一 request_id 不能用于不同动作。"}
        if expected is not None and expected != self.revision:
            return {"error": "stale_revision", "message": "状态已变化，请先 read。"}
        try:
            result = self.game.step(action)
        except ValueError:
            return {"error": "invalid_action", "message": "当前公开状态不允许该动作，或委托已结束。"}
        self.revision += 1
        result = self._public(result)
        self.requests[request_id] = (signature, deepcopy(result))
        return result


def serve_stdio(session, input_stream, output_stream):
    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except (ValueError, TypeError):
            response = {"error": "invalid_json", "message": "每行需要一个 JSON 对象。"}
        else:
            response = session.dispatch(request)
        output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
        output_stream.flush()


def play_human(game, tasks):
    print("独立机制试玩：不是正式记忆实验。输入 move J、inspect、process、submit、abandon、read 或 quit。")
    for task_id in tasks:
        session = StationSession(game, task_id)
        print("\n" + session.initial["text"])
        while not game.state.done:
            try:
                words = input("> ").strip().split()
            except EOFError:
                return
            if not words:
                continue
            verb = words[0].lower()
            if verb == "quit":
                return
            if verb == "read" and len(words) == 1:
                request = {"command": "read"}
            elif (verb == "move" and len(words) == 2) or (verb in ("inspect", "process", "submit", "abandon") and len(words) == 1):
                action = {"type": verb}
                if verb == "move":
                    action["target"] = words[1].upper()
                request = {"command": "action", "action": action, "request_id": uuid4().hex,
                           "expected_revision": session.revision}
            else:
                print("命令格式：move 地点，或 inspect/process/submit/abandon/read/quit。")
                continue
            response = session.dispatch(request)
            print(response.get("text", response.get("message", "请求失败。")))


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--world", help="private host fixture; never a tool argument")
    parser.add_argument("--task", help="host-selected task; tools cannot change it")
    parser.add_argument("--human", action="store_true")
    parser.add_argument("--all-tasks", action="store_true", help="human mode only")
    parser.add_argument("--output", type=Path, help="fresh private host log directory")
    args = parser.parse_args(argv)
    design = load_design(args.design)
    if args.all_tasks and (not args.human or args.task):
        parser.error("--all-tasks requires --human and cannot be combined with --task")
    world = args.world if args.world is not None else choice(tuple(design["private_worlds"]))
    if world not in design["private_worlds"]:
        parser.error("unknown private world fixture")
    task = args.task or next(iter(design["tasks"]))
    if task not in design["tasks"]:
        parser.error("unknown task")
    output = args.output or Path(".runs/station-play") / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    game = StationGame(world, design)
    try:
        if args.human:
            play_human(game, list(design["tasks"]) if args.all_tasks else [task])
        else:
            serve_stdio(StationSession(game, task), sys.stdin, sys.stdout)
    finally:
        (output / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
        (output / "summary.json").write_text(json.dumps({
            "kind": "local_prototype_play_not_agent_memory_evaluation", "design_id": design["design_id"],
            "private_world": world, "tasks_started": game._runs, "last_task": game.task_id,
            "done": bool(game.state and game.state.done), "success": bool(game.state and game.state.success),
            "protocol": "prototype_current_task_jsonl_1"}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
