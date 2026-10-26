"""Public-geography routing and feedback-only feasibility policies.

These scripted policies validate a map. They are not native agents, memory
systems, or an exact unknown-world optimal-policy solver.
"""
from heapq import heappop, heappush

from .station_capability import capability_groups, compatible_worlds, neighbors


def shortest_route(design, start, target):
    frontier = [(0, (start,))]
    visited = set()
    while frontier:
        cost, path = heappop(frontier)
        node = path[-1]
        if node in visited:
            continue
        if node == target:
            return list(path), cost
        visited.add(node)
        for other, weight in neighbors(design, node):
            if other not in visited:
                heappush(frontier, (cost + weight, (*path, other)))
    raise ValueError("Public target is unreachable")


def walk(game, target):
    path, _ = shortest_route(game.design, game.state.position, target)
    for node in path[1:]:
        game.step({"type": "move", "target": node})


def task_group(design, task_id):
    kind = design["tasks"][task_id]["required_kind"]
    return next(key for key, group in capability_groups(design).items() if kind in group["kinds"])


def feedback_policy(game, *, retain_history=True):
    """Collect, select using delivered evidence, try the other station if needed."""
    walk(game, game.task["target"])
    group = capability_groups(game.design)[task_group(game.design, game.task_id)]
    while not game.state.processed:
        evidence = game.events if retain_history else [e for e in game.events if e["task_run_id"] == game.task_run_id]
        possible = compatible_worlds(game.design, evidence)
        matching = [s for s in group["stations"] if all(
            game.design["private_worlds"][w][s] == game.task["required_kind"] for w in possible)]
        station = matching[0] if matching else group["stations"][0]
        walk(game, station)
        game.step({"type": "process"})
        if game.done:
            raise AssertionError("Feasibility policy ran out of operations")
    walk(game, game.task["submit_at"])
    game.step({"type": "submit"})
    if not game.state.success:
        raise AssertionError("Feasibility policy did not submit")


def schedule(design):
    previous, rows = {}, []
    for index, (task_id, task) in enumerate(design["tasks"].items(), 1):
        group = task_group(design, task_id)
        rows.append({"id": task_id, **task, "group": group,
                     "intervening_tasks_since_same_group": index - previous[group] - 1 if group in previous else None})
        previous[group] = index
    return rows
