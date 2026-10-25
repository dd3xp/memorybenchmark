"""Check a candidate task design without registering it as a live scenario.

Full-information static planning and real-engine replay validate task choices.
They do not simulate memory, prescribe agent routes, or produce memory scores.
Run from the repository root: python -m scripts.check_task_dependency_design
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
from heapq import heappop, heappush
from itertools import combinations, count
import json
from pathlib import Path

from memorybenchmark.analysis import commute_graph
from memorybenchmark.game import Game
from memorybenchmark.validation import validate
from memorybenchmark.worlds import load_scenario, submission_camps, task_goals


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design" / "lake_task_dependencies_v1.json"


def plan(world, task, final_tools):
    """Minimum effort for each exact final inventory, respecting action budget.

    Costs above starting stamina describe a non-reviving reference walk, not an
    executable zero-death plan. Only feasible plans are replayed below.
    """
    required = frozenset(final_tools)
    goals = {node: 1 << i for i, node in enumerate(task_goals(task))}
    goal_mask = (1 << len(goals)) - 1
    camps = submission_camps(world, task)
    initial = (task["start"], frozenset(), goals.get(task["start"], 0), 0)
    sequence = count()
    queue = [(0, next(sequence), initial, [])]
    best = {initial: 0}
    adjacency = {node: [] for node in world["locations"]}
    for a, b, distance in world["edges"]:
        adjacency[a].append((b, distance))
        adjacency[b].append((a, distance))
    while queue:
        cost, _, state, actions = heappop(queue)
        if best[state] != cost:
            continue
        node, carried, visited, steps = state
        if visited == goal_mask and node in camps and carried == required:
            return {"effort": cost, "actions": actions + [{"type": "submit"}],
                    "zero_death_feasible": cost < task["stamina"]}
        if steps >= task["max_steps"] - 1:
            continue
        candidates = []
        for tool in world.get("depots", {}).get(node, []):
            if tool in required and tool not in carried:
                candidates.append((0, (node, carried | {tool}, visited, steps + 1),
                                   {"type": "take", "target": tool}))
        for target, distance in adjacency[node]:
            hazard = world.get("hazards", {}).get(target)
            extra = 0
            if hazard:
                extra = min([hazard["extra_effort"]] +
                            [world["tools"][t]["mitigates"].get(hazard["kind"], hazard["extra_effort"])
                             for t in carried])
            candidates.append((distance + extra,
                               (target, carried, visited | goals.get(target, 0), steps + 1),
                               {"type": "move", "target": target}))
        for delta, after, action in candidates:
            updated = cost + delta
            if updated < best.get(after, float("inf")):
                best[after] = updated
                heappush(queue, (updated, next(sequence), after, actions + [action]))
    raise ValueError("No reference walk within the action budget")


def check(output):
    design_bytes = DESIGN.read_bytes()
    design = json.loads(design_bytes)
    world, _ = load_scenario(design["base_scenario"])
    if world["version"] != design["base_world_version"]:
        raise ValueError("Candidate base world version changed")
    base_digest = sha256(json.dumps(world, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    world = deepcopy(world)
    world["edges"].extend(design["added_edges"])
    world["version"] = design["world_version"]
    tasks = {task_id: {key: value for key, value in task.items()
                       if key not in ("potential_information", "later_choices")}
             for task_id, task in design["tasks"].items()}
    validate(world, tasks)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use a fresh output directory to preserve previous checks")
    (output / "candidate_scenario.json").write_text(
        json.dumps({"world": world, "tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    tools = sorted(world["tools"])
    inventories = [list(items) for size in range(len(tools) + 1) for items in combinations(tools, size)]
    results = {}
    for task_id, task in tasks.items():
        variants = []
        for inventory in inventories:
            result = plan(world, task, inventory)
            row = {"tools": inventory, **result, "steps": len(result["actions"])}
            if result["zero_death_feasible"]:
                log = output / f"{task_id}-{'-'.join(inventory) or 'none'}.jsonl"
                game = Game(world=world, tasks=tasks, log_path=log, scenario="lake-easy")
                game.start_task(task_id)
                for i, action in enumerate(result["actions"]):
                    game.step(action, request_id=f"design-{i}", expected_revision=game.revision)
                if not game.success or game.effort != result["effort"] or game.deaths:
                    raise AssertionError(f"Replay diverged: {task_id}, {inventory}")
                graph = commute_graph(game.events, game.task_run_id)
                if graph["effort"] != game.effort:
                    raise AssertionError("Graph lost transition costs")
                row.update(distance=graph["distance"],
                           hazard_entries=sum(e["hazard_cost"] > 0 for e in graph["edges"]),
                           path=[task["start"]] + [a["target"] for a in result["actions"] if a["type"] == "move"])
            variants.append(row)
        minimum = min(r["effort"] for r in variants if r["zero_death_feasible"])
        results[task_id] = {"name": task["name"], "minimum_effort": minimum,
                            "best_tool_sets": [r["tools"] for r in variants if r["effort"] == minimum],
                            "variants": variants}
    for witness in design["design_checks"]:
        for task_id, expected in zip(witness["tasks"], witness["expected_best_tools"]):
            if results[task_id]["best_tool_sets"] != [expected]:
                raise AssertionError(f"Expected choice did not hold: {task_id}: {results[task_id]['best_tool_sets']}")
    # Identical walks can still carry different information in edge attributes.
    # Use a one-hazard task so both variants finish, without a respawn changing
    # the topology. This is a graph representation check, not a memory claim.
    same_walk = []
    prepared = next(r for r in results["T1"]["variants"] if r["tools"] == ["grip_kit"])
    for take in (True, False):
        game = Game(world=world, tasks=tasks, scenario="lake-easy",
                    log_path=output / f"same-walk-{'take' if take else 'skip'}.jsonl")
        game.start_task("T1")
        for i, action in enumerate(prepared["actions"]):
            if not take and action["type"] == "take":
                continue
            game.step(action, request_id=f"same-walk-{i}", expected_revision=game.revision)
        if not game.success or game.deaths:
            raise AssertionError("Same-walk witness did not finish")
        graph = commute_graph(game.events, game.task_run_id)
        same_walk.append({"take_tool": take, "effort": graph["effort"], "distance": graph["distance"],
                          "ordered_edges": [[e["source"], e["target"]] for e in graph["edges"]]})
    if (same_walk[0]["ordered_edges"] != same_walk[1]["ordered_edges"] or
            same_walk[0]["distance"] != same_walk[1]["distance"] or
            same_walk[0]["effort"] == same_walk[1]["effort"]):
        raise AssertionError("Same-walk witness lost the intended distinction")
    # The task-level choice changes must survive nearby road distances. This
    # checks the construction, not robustness of a proposed memory metric.
    distance_checks = []
    for north in (6, 7):
        for south in range(9, 14):
            variant = deepcopy(world)
            for edge in variant["edges"]:
                if set(edge[:2]) == {"E2", "D2"}:
                    edge[2] = north
                if set(edge[:2]) == {"W2", "B6"}:
                    edge[2] = south
            for task_id, expected in (("T2", ["grip_kit"]), ("T5", []),
                                      ("T4", ["stream_kit"]), ("T6", [])):
                choices = [(inventory, plan(variant, tasks[task_id], inventory)) for inventory in inventories]
                minimum = min(row["effort"] for _, row in choices if row["zero_death_feasible"])
                winners = [inventory for inventory, row in choices if row["effort"] == minimum]
                if winners != [expected]:
                    raise AssertionError(f"Distance variation changed {task_id}: {north}, {south}, {winners}")
            distance_checks.append({"E2_D2": north, "W2_B6": south})
    report = {"kind": "candidate_task_structure_check_not_memory_evaluation",
              "design_id": design["design_id"], "design_sha256": sha256(design_bytes).hexdigest(),
              "base_world_sha256": base_digest, "nodes": len(world["locations"]),
              "edges": len(world["edges"]), "tasks": results, "same_walk_witness": same_walk,
              "nearby_distance_checks": distance_checks,
              "checked": ["legal zero-death replay", "exact-inventory alternatives",
                          "same-target decision changes with submission camp", "graph cost preservation"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check(args.output)
    for task_id, row in report["tasks"].items():
        print(task_id, row["name"], "best tools:", row["best_tool_sets"],
              "effort:", row["minimum_effort"],
              "alternatives:", [(r["tools"], r["effort"], r["zero_death_feasible"]) for r in row["variants"]])
    print("PASS: candidate choices and legal reference replays; no agent run or memory score")
