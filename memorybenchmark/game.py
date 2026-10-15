"""Deterministic game core. Clients receive observations, never world state."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4


WORLD = {
    "version": "valley-prototype-1",
    "locations": {
        "S": {"name": "起点", "x": 80, "y": 250},
        "J": {"name": "岔路口", "x": 240, "y": 250},
        "F": {"name": "渡口", "x": 410, "y": 250},
        "R": {"name": "对岸", "x": 560, "y": 250},
        "K": {"name": "测绘点", "x": 730, "y": 250},
        "H": {"name": "山路", "x": 480, "y": 410},
        "U": {"name": "支谷", "x": 240, "y": 100},
        "V": {"name": "谷地深处", "x": 450, "y": 100},
    },
    "edges": [("S", "J", 2), ("J", "F", 1), ("F", "R", 1),
              ("R", "K", 1), ("J", "H", 2), ("H", "K", 2),
              ("J", "U", 1), ("U", "V", 1)],
    # An evaluator-authored, nonperiodic timeline, not an agent-visible forecast.
    "weather": [(0, "rain", "night"), (120, "clear", "day"),
                (205, "snow", "day"), (337, "rain", "night")],
}
TASKS = {
    "T1": {"name": "渡口勘测", "goal": "F", "start": "S",
           "instruction": "寻找并测量渡口 F，然后提交测绘结果。途中可以自由探索。"},
    "T2": {"name": "对岸测绘", "goal": "K", "start": "S",
           "instruction": "寻找并测量测绘点 K，然后提交测绘结果。自行选择路线。"},
}


class ProtocolError(ValueError):
    """Malformed or stale request, not an in-game failure."""


class Game:
    def __init__(self, world=None, tasks=None, log_path: Path | None = None):
        self.world = deepcopy(world or WORLD)
        self.tasks = deepcopy(tasks or TASKS)
        self.log_path = log_path
        self.events: list[dict] = []
        self.evidence: list[dict] = []  # Evaluator only; derived from delivered feedback.
        self.clock = 0
        self.revision = 0
        self.task_id = None
        self.task_run_id = None
        self.position = None
        self.done = False
        self.success = False
        self.steps = 0
        self.distance = 0
        self.max_steps = 40
        self.surveyed: set[str] = set()
        self.known_nodes: set[str] = set()
        self.known_edges: set[tuple] = set()
        self.requests: dict[str, tuple[str, dict]] = {}

    def conditions(self):
        weather, period = "clear", "day"
        for at, w, p in self.world["weather"]:
            if at > self.clock:
                break
            weather, period = w, p
        return {"weather": weather, "period": period}

    def neighbors(self, location):
        result = []
        for a, b, distance in self.world["edges"]:
            if location in (a, b):
                result.append({"target": b if a == location else a, "distance": distance})
        return result

    def _reveal(self):
        self.known_nodes.add(self.position)
        for edge in self.neighbors(self.position):
            self.known_nodes.add(edge["target"])
            self.known_edges.add(tuple(sorted((self.position, edge["target"]))))

    def observation(self):
        if self.task_id is None:
            raise ProtocolError("请先开始任务。")
        return {
            "task_id": self.task_id, "task_run_id": self.task_run_id,
            "instruction": self.tasks[self.task_id]["instruction"],
            "location": {"id": self.position, **self.world["locations"][self.position]},
            "conditions": self.conditions(), "world_time": self.clock,
            "revision": self.revision,
            # These are geometrically attemptable moves, not a hidden safe-action filter.
            "neighbors": [{**n, "name": self.world["locations"][n["target"]]["name"]}
                          for n in self.neighbors(self.position)],
            "map": {
                "nodes": [{"id": n, **self.world["locations"][n]} for n in sorted(self.known_nodes)],
                "edges": [list(e) for e in sorted(self.known_edges)],
                "surveyed": sorted(self.surveyed),
            },
            "steps": self.steps, "max_steps": self.max_steps, "distance": self.distance,
            "done": self.done, "success": self.success,
        }

    def _record(self, event):
        event = {"event_id": len(self.events), "task_id": self.task_id,
                 "task_run_id": self.task_run_id, "world_version": self.world["version"], **event}
        # Serialize before changing either log: invalid data cannot partially write an event.
        line = json.dumps(event, ensure_ascii=False)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        self.events.append(deepcopy(event))
        return event

    def start_task(self, task_id):
        if task_id not in self.tasks:
            raise ProtocolError("未知任务。")
        if self.task_id is not None and not self.done:
            raise ProtocolError("当前任务尚未结束。")
        self.task_id = task_id
        self.task_run_id = uuid4().hex
        self.position = self.tasks[task_id]["start"]
        self.done = self.success = False
        self.steps = self.distance = 0
        self.max_steps = self.tasks[task_id].get("max_steps", 40)
        self.surveyed = set()
        self.known_nodes, self.known_edges = set(), set()
        self.requests = {}
        self.revision += 1
        self._reveal()
        response = {"observation": self.observation(), "feedback": "任务开始。", "outcome": "started"}
        self._record({"kind": "task_started", "position": self.position,
                      "time": self.clock, "delivered": response})
        return deepcopy(response)

    def step(self, action, *, request_id, expected_revision=None):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise ProtocolError("动作需要长度不超过 128 的 request_id。")
        if not isinstance(action, dict) or set(action) - {"type", "target"}:
            raise ProtocolError("动作应包含 type 和可选的 target。")
        verb = action.get("type")
        if verb not in ("move", "observe", "survey", "wait", "submit", "abandon"):
            raise ProtocolError("未知动作。")
        if verb == "move":
            if not isinstance(action.get("target"), str):
                raise ProtocolError("移动需要 target 地点标识。")
        elif "target" in action:
            raise ProtocolError("该动作不接受 target。")
        fingerprint = json.dumps({"action": action, "revision": expected_revision}, sort_keys=True)
        if request_id in self.requests:
            old, response = self.requests[request_id]
            if fingerprint != old:
                raise ProtocolError("同一 request_id 不能用于不同请求。")
            return deepcopy(response)
        if self.task_id is None or self.done:
            raise ProtocolError("没有进行中的任务。")
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision != self.revision):
            raise ProtocolError("状态版本已变化，请先读取当前观察。")

        before, at, conditions = self.position, self.clock, self.conditions()
        self.steps += 1
        duration, movement_cost = 1, 0
        outcome, feedback, evidence = "ok", "", None
        if verb == "move":
            target = action["target"]
            edge = next((n for n in self.neighbors(before) if n["target"] == target), None)
            if edge is None:
                outcome, feedback = "invalid_move", "当前位置没有通往该地点的直接通路。"
            elif set((before, target)) == {"F", "R"} and conditions == {"weather": "rain", "period": "night"}:
                outcome, feedback = "blocked", "渡河受阻：本渡口在雨夜无法通行。你仍在原地。"
                evidence = {"claim": "crossing_blocked", "edge": sorted((before, target)),
                            "conditions": conditions, "world_version": self.world["version"],
                            "source_event_id": len(self.events)}
            else:
                self.position = target
                movement_cost = duration = edge["distance"]
                self.distance += movement_cost
                self._reveal()
                feedback = f"已到达{self.world['locations'][target]['name']}（{target}）。"
        elif verb == "observe":
            feedback = "观察到当前地点及相邻通路，详见公开观察。"
        elif verb == "survey":
            self.surveyed.add(self.position)
            duration = 2
            feedback = f"已完成{self.world['locations'][self.position]['name']}的地理测量。"
        elif verb == "wait":
            feedback = "等待了一个游戏时间单位。"
        elif verb == "abandon":
            self.done = True
            outcome, feedback = "abandoned", "已结束本次任务。已获得的反馈仍保存在评测记录中。"
        elif verb == "submit":
            self.success = self.tasks[self.task_id]["goal"] in self.surveyed
            if self.success:
                self.done = True
                outcome, feedback = "success", "测绘结果符合任务要求，任务成功。"
            else:
                outcome, feedback = "incomplete", "尚未完成目标地点的测量，可以继续探索。"
        self.clock += duration
        self.revision += 1
        if self.steps >= self.max_steps and not self.done:
            self.done = True
            outcome, feedback = "budget_exhausted", feedback + " 操作预算已用完，本次任务失败。"
        response = {"observation": self.observation(), "feedback": feedback, "outcome": outcome}
        self._record({"kind": "action", "action": deepcopy(action),
                      "from": before, "to": self.position, "time_before": at,
                      "time_after": self.clock, "conditions_before": conditions,
                      "movement_cost": movement_cost, "moved": before != self.position,
                      "outcome": outcome, "evidence_delivered": evidence, "delivered": response})
        if evidence:
            self.evidence.append(deepcopy(evidence))
        self.requests[request_id] = (fingerprint, deepcopy(response))
        return deepcopy(response)

    def snapshot(self):
        """Evaluator-only snapshot, including evidence, time, requests and event history."""
        return deepcopy({k: v for k, v in self.__dict__.items() if k != "log_path"})

    def restore(self, snapshot):
        if self.log_path:
            raise ProtocolError("持久日志的恢复需另开分支日志；原型仅允许恢复内存实例。")
        self.__dict__.update(deepcopy(snapshot))
