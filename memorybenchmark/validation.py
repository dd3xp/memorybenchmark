"""Full-information feasibility/cost checks, never an agent's memory score."""
from heapq import heappop, heappush
from itertools import count
import json

from .worlds import load_scenario, task_goals, submission_camps


def reference_route(world, task, allow_take=True):
    """Exact Dijkstra over (location, tools, goals visited, action count).

    Conditions and dynamic blocked passages are rejected instead of silently
    treating evaluator-known future weather as an agent's knowledge.
    """
    if world.get("passages") or any(h.get("conditions") for h in world.get("hazards", {}).values()):
        raise ValueError("该验证器仅支持无动态阻断、风险代价不随时间变化的场景。")
    sequence = count()
    goals = task_goals(task)
    camps = submission_camps(world, task)
    goal_bits = {n: 1 << i for i, n in enumerate(goals)}
    completed = (1 << len(goals)) - 1
    initial = (task["start"], frozenset(task.get("initial_tools", [])), goal_bits.get(task["start"], 0), 0)
    queue = [(0, next(sequence), initial, [])]
    best = {initial: 0}
    while queue:
        cost, _, state, path = heappop(queue)
        if best[state] != cost:
            continue
        location, carried, visited, steps = state
        if visited == completed and (not camps or location in camps):
            return {"effort": cost, "actions": path + [{"type": "submit"}],
                    "information": "full_world_static_costs", "allow_take": allow_take,
                    "within_stamina": cost < task.get("stamina", 100),
                    "within_steps": len(path) + 1 <= task.get("max_steps", 40)}
        if steps >= task.get("max_steps", 40) - 1:
            continue
        candidates = []
        if allow_take:
            for tool in world.get("depots", {}).get(location, []):
                if tool not in carried:
                    candidates.append((0, (location, carried | {tool}, visited, steps + 1), {"type": "take", "target": tool}))
        for a, b, distance in world["edges"]:
            if location not in (a, b):
                continue
            target = b if a == location else a
            hazard = world.get("hazards", {}).get(target)
            extra = 0
            if hazard:
                extra = min([hazard["extra_effort"]] + [world["tools"][t]["mitigates"].get(hazard["kind"], hazard["extra_effort"]) for t in carried])
            candidates.append((distance + extra, (target, carried, visited | goal_bits.get(target, 0), steps + 1), {"type": "move", "target": target}))
        for delta, target_state, action in candidates:
            candidate = cost + delta
            if candidate < best.get(target_state, float("inf")):
                best[target_state] = candidate
                heappush(queue, (candidate, next(sequence), target_state, path + [action]))
    raise ValueError("任务目标不可达。")


def validate(world, tasks):
    locations = world["locations"]
    seen_edges = set()
    for a, b, distance in world["edges"]:
        if a not in locations or b not in locations or a == b or type(distance) is not int or distance <= 0:
            raise ValueError("通路端点或距离无效。")
        pair = tuple(sorted((a, b)))
        if pair in seen_edges:
            raise ValueError("基础地图包含重复通路。")
        seen_edges.add(pair)
    for location, tools in world.get("depots", {}).items():
        if location not in locations or any(t not in world["tools"] for t in tools):
            raise ValueError("工具点配置无效。")
    for location, hazard in world.get("hazards", {}).items():
        if location not in locations or type(hazard["extra_effort"]) is not int or hazard["extra_effort"] < 0:
            raise ValueError("风险配置无效。")
    for tool in world.get("tools", {}).values():
        if any(type(v) is not int or v < 0 for v in tool["mitigates"].values()):
            raise ValueError("工具效果配置无效。")
    times = [e[0] for e in world["weather"]]
    if not times or times[0] != 0 or times != sorted(set(times)):
        raise ValueError("天气时间表需要从零开始且严格递增。")
    report = {}
    camps = world.get("camps", [])
    if len(set(camps)) != len(camps) or any(n not in locations for n in camps):
        raise ValueError("营地配置无效。")
    for key, task in tasks.items():
        goals = task_goals(task)
        if task["start"] not in locations or not goals or len(set(goals)) != len(goals) or any(n not in locations for n in goals):
            raise ValueError("任务位置无效。")
        allowed_camps = submission_camps(world, task)
        if camps and (task["start"] not in camps or not allowed_camps or any(n not in camps for n in allowed_camps)):
            raise ValueError("任务出发和提交必须位于已配置营地。")
        prepared, no_take = reference_route(world, task), reference_route(world, task, False)
        if not prepared["within_stamina"] or not prepared["within_steps"]:
            raise ValueError(f"{key} 不满足配置的体力／步数约束。")
        report[key] = {"name": task["name"], "with_tool_options": prepared, "without_taking_tools": no_take}
    return report


if __name__ == "__main__":
    import argparse, sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="valley", choices=("valley", "loch-ness"))
    args = parser.parse_args()
    print(json.dumps(validate(*load_scenario(args.scenario)), ensure_ascii=False, indent=2))
