"""Human-only Easy20 play/design views over the same task-scoped game engine.

The native MCP bridge binds StationSession directly, not this human service.
Only the explicit design view exposes capabilities and future commissions.
"""
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from ..analysis import commute_graph
from ..game import ProtocolError
from ..watch import atomic_json
from .station_capability import StationGame, capability_groups, load_design, map_world, task_stages
from .station_experience import experience_opportunities, experience_schedule
from .station_routes import known_world_route, schedule, station_options
from .station_session import EASY20_REUSE_DESIGN, StationSession


class FieldService:
    def __init__(self, log_root, design=None):
        self.design = deepcopy(design) if design is not None else load_design(EASY20_REUSE_DESIGN)
        self.log_root = Path(log_root) / "station-human"
        self.instances = {}
        self.lock = RLock()

    def _instance(self, token):
        if not isinstance(token, str) or token not in self.instances:
            raise ProtocolError("这次探索已不在服务中，请开始一次新探索。")
        return self.instances[token]

    def _save(self, token, item):
        folder = self.log_root / token
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "events.jsonl").open("a", encoding="utf-8") as stream:
            for event in item["game"].events[item["saved"]:]:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        item["saved"] = len(item["game"].events)
        atomic_json(folder / "summary.json", {"kind": "human_play_not_agent_memory_evaluation",
                    "design_id": self.design["design_id"], "task": item["game"].task_id,
                    "completed": item["completed"], "done": item["game"].done})

    def _response(self, token, item, response):
        game = item["game"]
        graph = commute_graph(game.events, game.task_run_id)
        current = [e for e in game.events if e["task_run_id"] == game.task_run_id and e["kind"] == "action"]
        return {**response, "instance_id": token, "task_run_id": game.task_run_id,
                "task_index": item["index"] + 1, "task_count": len(game.design["tasks"]),
                "completed": deepcopy(item["completed"]),
                "presentation": deepcopy(game.design.get("presentation", {})),
                "trace": graph, "current_actions": deepcopy(current),
                "stream_finished": game.done and item["index"] + 1 == len(game.design["tasks"])}

    def start(self, request):
        if request:
            raise ProtocolError("新探索不接受任务、能力分配或世界参数。")
        with self.lock:
            token = uuid4().hex
            game = StationGame(map_world(self.design), self.design)
            first = next(iter(self.design["tasks"]))
            session = StationSession(game, first)
            item = {"game": game, "session": session, "index": 0, "completed": [],
                    "saved": 0, "advances": {}}
            self.instances[token] = item
            self._save(token, item)
            return self._response(token, item, session.initial)

    def read(self, token):
        with self.lock:
            item = self._instance(token)
            return self._response(token, item, item["session"].dispatch({"command": "read"}))

    def action(self, request):
        if set(request) - {"instance_id", "task_run_id", "action", "request_id", "expected_revision"}:
            raise ProtocolError("游戏操作只接受当前实例、委托、动作、请求编号和版本。")
        with self.lock:
            token = request.get("instance_id")
            item = self._instance(token)
            if request.get("task_run_id") != item["game"].task_run_id:
                raise ProtocolError("委托已变化，请读取当前观察后再操作。")
            result = item["session"].dispatch({"command": "action", **{k: v for k, v in request.items() if k not in {"instance_id", "task_run_id"}}})
            if "error" in result:
                return result
            game = item["game"]
            if game.done and (not item["completed"] or item["completed"][-1]["id"] != game.task_id):
                item["completed"].append({"id": game.task_id, "name": game.task["name"],
                                           "success": game.state.success, "distance": game.distance, "operations": game.steps})
            self._save(token, item)
            return self._response(token, item, result)

    def advance(self, request):
        if set(request) != {"instance_id", "request_id", "task_run_id", "expected_revision"}:
            raise ProtocolError("切换委托需要当前会话、版本和请求编号。")
        rid = request["request_id"]
        if not isinstance(rid, str) or not 1 <= len(rid) <= 128:
            raise ProtocolError("切换请求编号无效。")
        signature = json.dumps(request, sort_keys=True)
        with self.lock:
            token = request["instance_id"]
            item = self._instance(token)
            if rid in item["advances"]:
                old_signature, response = item["advances"][rid]
                if signature != old_signature:
                    raise ProtocolError("同一请求编号不能切换不同的委托。")
                return deepcopy(response)
            game, session = item["game"], item["session"]
            if (request["task_run_id"] != game.task_run_id or type(request["expected_revision"]) is not int
                    or request["expected_revision"] != session.revision):
                raise ProtocolError("委托或状态已变化，请刷新当前观察。")
            if not game.done:
                raise ProtocolError("请先完成或放弃当前委托。")
            tasks = list(self.design["tasks"])
            if item["index"] + 1 == len(tasks):
                raise ProtocolError("二十项委托已结束。")
            item["index"] += 1
            item["session"] = StationSession(game, tasks[item["index"]])
            response = self._response(token, item, item["session"].initial)
            item["advances"][rid] = signature, deepcopy(response)
            self._save(token, item)
            return response

    def design_view(self, token):
        """Explicit human inspection only; reading it never changes game events."""
        with self.lock:
            item = self._instance(token)
            game = item["game"]
            assignment = deepcopy(game.design["private_worlds"][game._world_id])
            dependencies = {row["task_id"]: row for row in experience_schedule(game.design)}
            tasks = []
            for row in schedule(game.design):
                options = station_options(game.design, row["id"])
                matches = [r for r in options if assignment[r["station"]] == row["required_kind"]]
                reference = known_world_route(game.design, row["id"], assignment)
                record = {**row, "known_world_route": reference["path"], "known_world_distance": reference["distance"],
                              "experience_dependencies": dependencies[row["id"]],
                              "matching_stations": [r["station"] for r in matches],
                              "station_options": [{**r, "matches": assignment[r["station"]] == row["required_kind"]} for r in options]}
                if "stages" in row:
                    record["stage_options"] = []
                    for i, stage in enumerate(task_stages(row)):
                        begin = row["start"] if i == 0 else reference["stations"][i-1]
                        record["stage_options"].append({**row["stage_schedule"][i],
                            "matching_stations": [s for s in capability_groups(game.design)[row["stage_schedule"][i]["group"]]["stations"]
                                                  if assignment[s] == stage["required_kind"]],
                            "options": [{**r, "matches": assignment[r["station"]] == stage["required_kind"]}
                                        for r in station_options(game.design, row["id"], stage_index=i, start=begin)],
                            "cost_scope": "From this stage's start on the known-world design route through its target/station to the next target or final camp. Local costs are not additive."})
                tasks.append(record)
            return {"viewer": "human_design_only", "name": game.design["public"]["name"],
                    "design_id": game.design["design_id"],
                    "experience_opportunities": experience_opportunities(game.design, game.events, game.task_run_id),
                    "capabilities": assignment, "tasks": tasks,
                    "triggers": [{"station": s, "group": next(key for key, group in capability_groups(game.design).items() if s in group["stations"]),
                        "capability": kind} for s, kind in assignment.items()]}
