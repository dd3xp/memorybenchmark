"""Public-geography routing and feedback-only feasibility policies.

These scripted policies validate a map. They are not native agents, memory
systems, or an exact unknown-world optimal-policy solver.
"""
from heapq import heappop, heappush
from itertools import product

from .station_capability import active_stage, capability_groups, compatible_worlds, neighbors, task_stages


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


def task_group(design, task_id, stage_index=0):
    kind = task_stages(design["tasks"][task_id])[stage_index]["required_kind"]
    return next(key for key, group in capability_groups(design).items() if kind in group["kinds"])


def station_branches(design):
    """Public dead-end station paths, stopping at the first non-transit fork."""
    locations = design["public"]["locations"]; result = {}
    for station, data in locations.items():
        if data["kind"] != "station":continue
        links = neighbors(design, station)
        if len(links) != 1:continue
        previous, current = station, links[0][0]; path = [station,current]
        while locations[current].get("transit"):
            onward = [n for n,_ in neighbors(design,current) if n != previous]
            if len(onward) != 1:raise ValueError("Transit nodes must form simple station branches")
            previous,current = current,onward[0];path.append(current)
        if len(path)>2:result[station] = {"fork":current,"path":list(reversed(path))}
    return result


def station_options(design, task_id, *, stage_index=0, start=None):
    """Public weighted route costs; no station capability or world ID is read."""
    task = design["tasks"][task_id]
    stages = task_stages(task); stage = stages[stage_index]
    destination = stages[stage_index+1]["target"] if stage_index+1 < len(stages) else task["submit_at"]
    prefix = shortest_route(design, start or task["start"], stage["target"])[1]
    result = []
    group_stations = capability_groups(design)[task_group(design, task_id, stage_index)]["stations"]
    typed = design.get("world_generator") == "station_type_permutations"
    candidates = [s for s, p in design["public"]["locations"].items() if p["kind"] == "station"] if typed else group_stations
    for station in candidates:
        outward = shortest_route(design, stage["target"], station)[1]
        home = shortest_route(design, station, destination)[1]
        result.append({"station": station, "distance_from_target": outward,
                       "completion_distance": prefix + outward + home,
                       **({"publicly_possible": station in group_stations} if typed else {})})
    return sorted(result, key=lambda row: (row["completion_distance"], row["station"]))


def feedback_policy(game, *, retain_history=True):
    """Collect and choose using delivered evidence, never the hidden world ID."""
    while not game.state.processed:
        index = game.state.stage; stage = active_stage(game.task, game.state)
        walk(game, stage["target"])
        group = capability_groups(game.design)[task_group(game.design, game.task_id, index)]
        stages = task_stages(game.task)
        destination = stages[index+1]["target"] if index+1 < len(stages) else game.task["submit_at"]
        while game.state.stage == index and not game.state.processed:
            evidence = game.events if retain_history else [e for e in game.events if e["task_run_id"] == game.task_run_id]
            possible = compatible_worlds(game.design, evidence)
            matching = [s for s in group["stations"] if all(
                game.design["private_worlds"][w][s] == stage["required_kind"] for w in possible)]
            if len(group["stations"]) == 2:
                station = matching[0] if matching else group["stations"][0]
            else:
                candidates = matching or [s for s in group["stations"] if any(
                    game.design["private_worlds"][w][s] == stage["required_kind"] for w in possible)]
                station = min(candidates, key=lambda s: (
                    shortest_route(game.design, game.state.position, s)[1]
                    + shortest_route(game.design, s, destination)[1], s))
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
        row = {"id": task_id, **task, "group": group,
                     "intervening_tasks_since_same_group": index - previous[group] - 1 if group in previous else None}
        if "stages" in task:
            row["stage_schedule"] = [{**stage, "group": task_group(design, task_id, i),
                "intervening_tasks_since_same_group": index - previous[task_group(design, task_id, i)] - 1
                if task_group(design, task_id, i) in previous else None}
                for i, stage in enumerate(task_stages(task))]
            for stage in row["stage_schedule"]:
                previous[stage["group"]] = index
        rows.append(row)
        previous[group] = index
    return rows


def known_world_route(design, task_id, assignment):
    """Human design/analysis only: jointly enumerate matching stage endpoints."""
    task = design["tasks"][task_id]; stages = task_stages(task)
    matches = [[s for s in capability_groups(design)[task_group(design, task_id, i)]["stations"]
                if assignment[s] == stage["required_kind"]] for i, stage in enumerate(stages)]
    options = []
    for stations in product(*matches):
        path, distance = [task["start"]], 0
        destinations = [node for stage, station in zip(stages, stations) for node in (stage["target"], station)]
        for target in [*destinations, task["submit_at"]]:
            leg, cost = shortest_route(design, path[-1], target)
            path.extend(leg[1:]); distance += cost
        options.append((distance, len(path), stations, path))
    distance, _, stations, path = min(options)
    return {"path": path, "distance": distance, "stations": list(stations)}
