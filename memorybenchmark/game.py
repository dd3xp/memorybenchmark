"""Deterministic shared rules. Only the core changes game state."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
from .worlds import load_scenario

WORLD, TASKS = load_scenario()


class ProtocolError(ValueError):
    """Malformed or stale request, distinct from a normal game failure."""


class Game:
    ACTIONS = ("move", "take", "observe", "wait", "submit", "abandon")

    def __init__(self, world=None, tasks=None, log_path: Path | None = None, scenario="valley"):
        default_world, default_tasks = load_scenario(scenario)
        self.world = deepcopy(default_world if world is None else world)
        self.tasks = deepcopy(default_tasks if tasks is None else tasks)
        self.scenario = scenario
        self.log_path = log_path
        self.events, self.evidence = [], []
        self.clock = self.revision = 0
        self.task_id = self.task_run_id = self.position = None
        self.done = self.success = False
        self.steps = self.distance = self.effort = 0
        self.max_steps = 40
        self.stamina = self.initial_stamina = 100
        self.inventory, self.surveyed, self.known_nodes, self.known_edges = set(), set(), set(), set()
        self.requests = {}

    def conditions(self, at=None):
        at = self.clock if at is None else at
        weather, period = "clear", "day"
        for timestamp, w, p in self.world["weather"]:
            if timestamp > at:
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
        self.surveyed.add(self.position)
        for edge in self.neighbors(self.position):
            self.known_nodes.add(edge["target"])
            self.known_edges.add(tuple(sorted((self.position, edge["target"]))))

    def _tool_info(self, tool):
        return {"id": tool, **deepcopy(self.world["tools"][tool])}

    def observation(self):
        if self.task_id is None:
            raise ProtocolError("请先开始任务。")
        order = list(self.tasks)
        index = order.index(self.task_id)
        return {
            "task_id": self.task_id, "task_name": self.tasks[self.task_id]["name"],
            "task_run_id": self.task_run_id,
            "next_task_id": order[index + 1] if index + 1 < len(order) else None,
            "instruction": self.tasks[self.task_id]["instruction"],
            "location": {"id": self.position, **self.world["locations"][self.position]},
            "conditions": self.conditions(), "world_time": self.clock, "revision": self.revision,
            "neighbors": [{**n, "name": self.world["locations"][n["target"]]["name"]} for n in self.neighbors(self.position)],
            "map": {"nodes": [{"id": n, **self.world["locations"][n]} for n in sorted(self.known_nodes)],
                    "edges": [list(e) for e in sorted(self.known_edges)], "surveyed": sorted(self.surveyed)},
            "inventory": [self._tool_info(t) for t in sorted(self.inventory)],
            "available_tools": [self._tool_info(t) for t in self.world["depots"].get(self.position, []) if t not in self.inventory],
            "stamina": self.stamina, "initial_stamina": self.initial_stamina, "effort": self.effort,
            "steps": self.steps, "max_steps": self.max_steps, "distance": self.distance,
            "done": self.done, "success": self.success,
        }

    def _state(self):
        return {"position": self.position, "time": self.clock, "stamina": self.stamina,
                "inventory": sorted(self.inventory), "surveyed": sorted(self.surveyed),
                "steps": self.steps, "done": self.done, "success": self.success}

    def _record(self, event):
        event = {"event_id": len(self.events), "task_id": self.task_id,
                 "task_run_id": self.task_run_id, "world_version": self.world["version"], **event}
        line = json.dumps(event, ensure_ascii=False)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        self.events.append(deepcopy(event))
        self.evidence.extend(deepcopy(event.get("evidence_delivered", [])))
        return event

    def _stock_evidence(self):
        return [{"claim": "tool_available", "location": self.position, "tool": t,
                 "tool_info": self._tool_info(t), "world_version": self.world["version"],
                 "source_event_id": len(self.events)} for t in self.world["depots"].get(self.position, []) if t not in self.inventory]

    def start_task(self, task_id):
        if not isinstance(task_id, str) or task_id not in self.tasks:
            raise ProtocolError("未知任务。")
        if self.task_id is not None and not self.done:
            raise ProtocolError("当前任务尚未结束。")
        task = self.tasks[task_id]
        self.task_id, self.task_run_id = task_id, uuid4().hex
        self.position = task["start"]
        self.done = self.success = False
        self.steps = self.distance = self.effort = 0
        self.max_steps = task.get("max_steps", 40)
        self.stamina = self.initial_stamina = task.get("stamina", 100)
        self.inventory = set(task.get("initial_tools", []))
        self.surveyed, self.known_nodes, self.known_edges = set(), set(), set()
        self.requests = {}
        self.revision += 1
        self._reveal()
        response = {"observation": self.observation(), "feedback": "任务开始，到达即自动记录地理信息。", "outcome": "started"}
        self._record({"kind": "task_started", "position": self.position, "time": self.clock,
                      "evidence_delivered": self._stock_evidence(), "state_after": self._state(), "delivered": response})
        return deepcopy(response)

    def step(self, action, *, request_id, expected_revision=None):
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise ProtocolError("动作需要长度不超过 128 的 request_id。")
        if not isinstance(action, dict) or set(action) - {"type", "target"}:
            raise ProtocolError("动作应包含 type 和可选的 target。")
        verb = action.get("type")
        if verb not in self.ACTIONS:
            raise ProtocolError("未知动作；测绘已改为到达自动完成。")
        if verb in ("move", "take"):
            if not isinstance(action.get("target"), str):
                raise ProtocolError("移动／取用需要 target 标识。")
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
        before_state = self._state()
        before, at, conditions = self.position, self.clock, self.conditions()
        self.steps += 1
        duration, movement_cost, hazard_cost, equipment_used = 1, 0, 0, None
        outcome, feedback, evidence = "ok", "", []
        if verb == "move":
            target = action["target"]
            edge = next((n for n in self.neighbors(before) if n["target"] == target), None)
            blocked = next((p for p in self.world.get("passages", []) if set(p["edge"]) == {before, target}
                            and all(conditions.get(k) == v for k, v in p["conditions"].items())), None)
            if edge is None:
                outcome, feedback = "invalid_move", "当前位置没有通往该地点的直接通路。"
            elif blocked:
                outcome, feedback = "blocked", blocked["feedback"]
                evidence.append({"claim": "crossing_blocked", "edge": sorted((before, target)), "conditions": conditions,
                                 "world_version": self.world["version"], "source_event_id": len(self.events)})
            else:
                self.position = target
                movement_cost = duration = edge["distance"]
                self.distance += movement_cost
                arrival = self.conditions(at + duration)
                hazard = self.world.get("hazards", {}).get(target)
                active = hazard and all(arrival.get(k) == v for k, v in hazard.get("conditions", {}).items())
                if active:
                    hazard_cost = hazard["extra_effort"]
                    for tool in sorted(self.inventory):
                        candidate = self.world["tools"][tool]["mitigates"].get(hazard["kind"], hazard_cost)
                        if candidate < hazard_cost:
                            hazard_cost, equipment_used = candidate, tool
                    evidence.append({"claim": "hazard_encountered", "location": target, "hazard": hazard["kind"],
                                     "conditions": arrival, "extra_effort_observed": hazard_cost, "equipment_used": equipment_used,
                                     "world_version": self.world["version"], "source_event_id": len(self.events)})
                self._reveal()
                feedback = f"已到达{self.world['locations'][target]['name']}（{target}），自动完成地理记录。"
                if active:
                    feedback += f" 遭遇{hazard['name']}，本次额外消耗 {hazard_cost} 体力。"
                    if equipment_used:
                        feedback += f" 携带的{self.world['tools'][equipment_used]['name']}自动生效。"
                feedback += f" 本次移动共需 {movement_cost + hazard_cost} 体力。"
        elif verb == "take":
            tool = action["target"]
            if tool in self.inventory:
                outcome, feedback = "already_carried", "已经携带该工具，无需重复取用。"
            elif tool not in self.world["depots"].get(before, []):
                outcome, feedback = "unavailable", "此处没有可取用的该工具。"
            else:
                self.inventory.add(tool)
                feedback = f"已取用{self.world['tools'][tool]['name']}，适用时会自动生效。"
        elif verb == "observe":
            feedback = "观察到当前地点、相邻通路和此处可取用的工具，详见公开观察。"
        elif verb == "wait":
            feedback = "等待了一个游戏时间单位。"
        elif verb == "abandon":
            self.done = True
            outcome, feedback = "abandoned", "已结束本次任务。"
        elif verb == "submit":
            self.success = self.tasks[self.task_id]["goal"] in self.surveyed
            if self.success:
                self.done = True
                outcome, feedback = "success", "地理记录符合任务要求，任务成功。"
            else:
                outcome, feedback = "incomplete", "尚未到达目标地点，可以继续探索。"
        effort_cost = movement_cost + hazard_cost
        stamina_spent = min(self.stamina, effort_cost)
        self.effort += effort_cost
        self.stamina -= stamina_spent
        self.clock += duration
        self.revision += 1
        if self.stamina <= 0 and not self.done:
            self.done, self.success = True, False
            outcome, feedback = "exhausted", feedback + " 体力耗尽，本次任务失败。"
        if self.steps >= self.max_steps and not self.done:
            self.done = True
            outcome, feedback = "budget_exhausted", feedback + " 操作预算已用完，本次任务失败。"
        evidence.extend(self._stock_evidence())
        response = {"observation": self.observation(), "feedback": feedback, "outcome": outcome}
        self._record({"kind": "action", "action": deepcopy(action), "from": before, "to": self.position,
                      "time_before": at, "time_after": self.clock, "conditions_before": conditions,
                      "arrival_conditions": self.conditions(), "movement_cost": movement_cost,
                      "hazard_cost": hazard_cost, "effort_cost": effort_cost, "stamina_spent": stamina_spent,
                      "inventory_before": before_state["inventory"], "equipment_used": equipment_used,
                      "moved": before != self.position, "outcome": outcome, "evidence_delivered": evidence,
                      "state_before": before_state, "state_after": self._state(), "delivered": response})
        self.requests[request_id] = (fingerprint, deepcopy(response))
        return deepcopy(response)

    def snapshot(self):
        return deepcopy({k: v for k, v in self.__dict__.items() if k != "log_path"})

    def restore(self, snapshot):
        if self.log_path:
            raise ProtocolError("持久日志的恢复需另开分支日志；仅允许恢复内存实例。")
        self.__dict__.update(deepcopy(snapshot))
