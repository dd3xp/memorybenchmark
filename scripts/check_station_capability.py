"""Validate a finite mechanism, export real traces, and never call a model API.

python -m scripts.check_station_capability --output .runs/station-capability-new
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from html import escape
from itertools import product
import json
from math import hypot
from pathlib import Path

from memorybenchmark.analysis import commute_graph
from memorybenchmark.prototypes.station_capability import (
    DESIGN_PATH, ReferencePlanner, StationGame, compatible_worlds, load_design, replay_policy,
)


def move(game, *nodes):
    for node in nodes:
        game.step({"type": "move", "target": node})


def history(design, world, kind, planner, task_id):
    game = StationGame(world, design)
    game.start_task(task_id)
    if kind == "completed_with_evidence":
        replay_policy(game, planner, tuple(design["private_worlds"]))
    else:
        move(game, "J", "A")
        if kind == "abandoned_with_evidence":
            game.step({"type": "inspect"})
        elif kind != "visited_without_query":
            raise ValueError("Unknown history fixture")
        game.step({"type": "abandon"})
    return game


def trace_graph(game):
    graph = commute_graph(game.events, game.task_run_id)
    events_by_id = {e["event_id"]: e for e in game.events}
    for edge in graph["edges"]:
        event = events_by_id[edge["id"]]
        edge["state_before"] = event["state_before"]
        edge["state_after"] = event["state_after"]
    graph["node_events"] = [
        {"event_id": e["event_id"], "location": e["from"], "time": e["time_before"],
         "action": e["action"], "feedback": e["delivered"]["feedback"],
         "state_before": e["state_before"], "state_after": e["state_after"]}
        for e in game.events if e["task_run_id"] == game.task_run_id and e["kind"] == "action" and not e["moved"]
    ]
    graph["task_run_id"] = game.task_run_id
    if graph["distance"] != game.distance:
        raise AssertionError("Graph projection lost walked distance")
    return graph


def render_svg(design, graph, title):
    """Draw the actual ordered multigraph; gray edges are public geography."""
    locations = design["public"]["locations"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="850" height="440" viewBox="0 0 850 440" font-family="Segoe UI, Microsoft YaHei, sans-serif">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#21628d"/></marker></defs>',
        '<rect width="850" height="440" fill="#fafbf8"/>',
        f'<text x="24" y="27" font-size="17">{escape(title)}</text>',
        f'<text x="24" y="421" font-size="13">Distance {graph["distance"]} · {len(graph["edges"])} moves · arrow numbers show movement order</text>',
    ]
    for a, b, _ in design["public"]["edges"]:
        p, q = locations[a], locations[b]
        parts.append(f'<line x1="{p["x"]}" y1="{p["y"]}" x2="{q["x"]}" y2="{q["y"]}" stroke="#c8d0cb" stroke-width="2"/>')
    groups = {}
    for edge in graph["edges"]:
        key = tuple(sorted((edge["source"], edge["target"])))
        groups.setdefault(key, []).append(edge)
    for (a, b), edges in groups.items():
        base_p, base_q = locations[a], locations[b]
        dx, dy = base_q["x"] - base_p["x"], base_q["y"] - base_p["y"]
        length = hypot(dx, dy)
        nx, ny = -dy / length, dx / length
        for i, edge in enumerate(edges):
            p, q = locations[edge["source"]], locations[edge["target"]]
            ux, uy = (q["x"] - p["x"]) / length, (q["y"] - p["y"]) / length
            offset = (i - (len(edges) - 1) / 2) * 13
            x1, y1 = p["x"] + ux * 21 + nx * offset, p["y"] + uy * 21 + ny * offset
            x2, y2 = q["x"] - ux * 23 + nx * offset, q["y"] - uy * 23 + ny * offset
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#21628d" stroke-width="2.5" marker-end="url(#arrow)"/>')
            parts.append(f'<text x="{(x1+x2)/2+nx*5:.1f}" y="{(y1+y2)/2+ny*5:.1f}" font-size="13" fill="#163b55">{edge["order"]+1}</text>')
    for node, data in locations.items():
        fill = "#e1efe6" if node in graph["nodes"] else "#ffffff"
        parts.append(f'<circle cx="{data["x"]}" cy="{data["y"]}" r="19" fill="{fill}" stroke="#455b51" stroke-width="2"/>')
        parts.append(f'<text x="{data["x"]}" y="{data["y"]+5}" text-anchor="middle" font-size="15">{escape(node)}</text>')
        parts.append(f'<text x="{data["x"]}" y="{data["y"]+39}" text-anchor="middle" font-size="12">{escape(data["name"])}</text>')
    parts.append('<text x="530" y="58" font-size="14">Recorded movement</text>')
    for i, edge in enumerate(graph["edges"]):
        parts.append(f'<text x="530" y="{83+i*21}" font-size="13">{i+1}. {edge["source"]} → {edge["target"]}  ({edge["weight"]})</text>')
    y = max(264, 95 + len(graph["edges"]) * 21)
    parts.append(f'<text x="530" y="{y}" font-size="14">Node operations</text>')
    for i, event in enumerate(graph["node_events"]):
        feedback = event["feedback"]
        description = feedback.get("result", feedback["kind"])
        text = f'{event["location"]}: {event["action"]["type"]} / {description}'
        parts.append(f'<text x="530" y="{y+23+i*19}" font-size="12">{escape(text)}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def export_case(output, name, game):
    folder = output / "cases"
    folder.mkdir(exist_ok=True)
    graph = trace_graph(game)
    (folder / f"{name}.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
    (folder / f"{name}.graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / f"{name}.svg").write_text(render_svg(game.design, graph, name), encoding="utf-8")
    return {"name": name, "success": game.state.success, "distance": graph["distance"],
            "moves": len(graph["edges"]), "operations": game.steps,
            "path": [game.task["start"]] + [e["target"] for e in graph["edges"]],
            "station_events": graph["node_events"], "log": f"cases/{name}.jsonl",
            "graph": f"cases/{name}.graph.json", "svg": f"cases/{name}.svg"}


def distance_sweep(design):
    rows = []
    worlds = tuple(design["private_worlds"])
    for camp, field, station in product((1, 3), (1, 4), (1, 2, 5)):
        variant = deepcopy(design)
        for edge in variant["public"]["edges"]:
            other = next(n for n in edge[:2] if n != "J")
            edge[2] = camp if other == "C" else station if other in ("A", "B") else field
        for task_id in variant["tasks"]:
            planner = ReferencePlanner(variant, task_id)
            known = 2 * (camp + field + station)
            uninformed = known + station
            if planner.initial(worlds).distance != uninformed:
                raise AssertionError("Unknown-world policy disagrees with the independent distance formula")
            actual = []
            for world in worlds:
                if planner.initial((world,)).distance != known:
                    raise AssertionError("Informed policy disagrees with the independent distance formula")
                game = StationGame(world, variant)
                game.start_task(task_id)
                replay_policy(game, planner, worlds)
                actual.append(game.distance)
            if Fraction(sum(actual), len(actual)) != uninformed:
                raise AssertionError("Policy replay disagrees with expected distance")
            rows.append({"camp_arm": camp, "field_arm": field, "station_arm": station,
                         "task": task_id, "informed_distance": known,
                         "uninformed_expected_distance": uninformed,
                         "actual_uninformed_distances": actual})
    return rows


def check(output):
    design = load_design()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh output directory; previous results are never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    (output / "design_snapshot.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    worlds = tuple(design["private_worlds"])
    planners = {task_id: ReferencePlanner(design, task_id) for task_id in design["tasks"]}
    public = []
    for world in worlds:
        game = StationGame(world, design)
        public.append(game.start_task("shore"))
    if public[0] != public[1]:
        raise AssertionError("The private world leaks into initial public input")
    conditions = []
    rows = []
    histories = ("completed_with_evidence", "abandoned_with_evidence", "visited_without_query")
    for previous_task, current_task in (("profile", "shore"), ("shore", "profile")):
        for history_kind in histories:
            distances = {"history_conditioned_reference": [], "no_history_reference": []}
            for world in worlds:
                checkpoint = history(design, world, history_kind, planners[previous_task], previous_task)
                prior = compatible_worlds(design, checkpoint.events)
                expected_count = 2 if history_kind == "visited_without_query" else 1
                if len(prior) != expected_count:
                    raise AssertionError("A visit, failure or success was confused with delivered evidence")
                initial_observations = []
                for condition in distances:
                    game = deepcopy(checkpoint)
                    initial_observations.append(game.start_task(current_task))
                    supplied = prior if condition == "history_conditioned_reference" else worlds
                    estimate = planners[current_task].initial(supplied)
                    replay_policy(game, planners[current_task], supplied)
                    if not game.state.success:
                        raise AssertionError("Unknown or failed history made the next task impossible")
                    row = export_case(output, f"{previous_task}-to-{current_task}-{history_kind}-{world}-{condition}", game)
                    row.update(history=history_kind, previous_task=previous_task, current_task=current_task,
                               private_world=world, condition=condition, historical_candidate_worlds=list(prior),
                               reference_initial_worlds=list(supplied), expected_distance=str(estimate.distance))
                    rows.append(row)
                    distances[condition].append(row["distance"])
                if initial_observations[0] != initial_observations[1]:
                    raise AssertionError("Matched branches start with different public inputs")
            means = {condition: Fraction(sum(values), len(values)) for condition, values in distances.items()}
            if means["no_history_reference"] != 10 or means["history_conditioned_reference"] != (10 if history_kind == "visited_without_query" else 8):
                raise AssertionError("Reference information-value check did not hold")
            conditions.append({"previous_task": previous_task, "current_task": current_task,
                               "history": history_kind, "mean_distance": {k: str(v) for k, v in means.items()}})
    # A map-only projection loses a redundant query even on an identical walk.
    representation = []
    for inspect in (False, True):
        game = StationGame("omega_0", design)
        game.start_task("shore")
        move(game, "J", "Q", "J", "B")
        if inspect:
            game.step({"type": "inspect"})
        game.step({"type": "process"})
        move(game, "J", "C")
        game.step({"type": "submit"})
        representation.append(export_case(output, f"representation-{'query' if inspect else 'direct'}", game))
    if (representation[0]["path"] != representation[1]["path"] or
            representation[0]["distance"] != representation[1]["distance"] or
            representation[0]["operations"] == representation[1]["operations"]):
        raise AssertionError("The representation fixture did not isolate a node operation")
    # Equal success, distance, operation count AND unlabelled edge multiplicity
    # can still hide different information-acquisition order. Neither is scored
    # as better or as a memory-use event.
    equal_totals = []
    for early_query in (True, False):
        game = StationGame("omega_0", design)
        game.start_task("shore")
        if early_query:
            move(game, "J", "A")
            game.step({"type": "inspect"})
            move(game, "J", "Q", "J", "B")
        else:
            move(game, "J", "Q", "J", "A")
            game.step({"type": "process"})
            move(game, "J", "B")
        game.step({"type": "process"})
        move(game, "J", "C")
        game.step({"type": "submit"})
        equal_totals.append(export_case(output, f"equal-totals-{'early-query' if early_query else 'later-trial'}", game))
    a, b = equal_totals
    if ((a["success"], a["distance"], a["moves"], a["operations"]) !=
            (b["success"], b["distance"], b["moves"], b["operations"]) or a["path"] == b["path"]):
        raise AssertionError("Equal-total fixtures lost their intended ordering distinction")
    if sorted(zip(a["path"], a["path"][1:])) != sorted(zip(b["path"], b["path"][1:])):
        raise AssertionError("Equal-total fixtures do not have the same unlabelled multigraph")
    representation += equal_totals
    sweeps = distance_sweep(design)
    report = {"kind": "finite_mechanism_validation_not_agent_memory_evaluation", "design_id": design["design_id"],
              "design_sha256": sha256(DESIGN_PATH.read_bytes()).hexdigest(),
              "source_sha256": {p: sha256(Path(p).read_bytes()).hexdigest() for p in (
                  "memorybenchmark/prototypes/station_capability.py", "scripts/check_station_capability.py")},
              "objective": "minimum expected movement, then operations, with success in every candidate world within 16 operations",
              "prior": "uniform over the two declared candidate worlds; reference analysis only",
              "cases": rows, "paired_results": conditions,
              "representation_examples": representation, "distance_sweep": sweeps,
              "planner_states": {task: planner.solve.cache_info().currsize for task, planner in planners.items()},
              "limitations": ["No real agent or native memory mechanism was run",
                              "The one-bit deterministic mechanism has only zero-information and fully discriminating evidence",
                              "History-conditioned reference knowledge is not an observation of agent learning",
                              "Both nodes and ordered attributed commutes plus node operations are needed"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 局部能力机制校验", "", "这是参考策略与规则校验，不是真实 Agent 记忆成绩。", "",
             "| 委托顺序 | 历史 | 按已暴露历史行动的平均距离 | 无历史参考的平均距离 |", "| --- | --- | ---: | ---: |"]
    for result in conditions:
        values = result["mean_distance"]
        lines.append(f'| {result["previous_task"]} → {result["current_task"]} | {result["history"]} | {values["history_conditioned_reference"]} | {values["no_history_reference"]} |')
    lines += ["", "两世界均可在无历史条件重新调查后完成。查询/处理均来自真实操作日志。", "", "## 执行图", ""]
    for row in rows + representation:
        lines.append(f'- [{row["name"]}]({row["svg"]}) · distance={row["distance"]}, moves={row["moves"]}, operations={row["operations"]}')
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    result = check(parser.parse_args().output)
    for row in result["paired_results"]:
        print(row["previous_task"], "->", row["current_task"], row["history"], row["mean_distance"])
    print(f'PASS: {len(result["cases"])} matched reference replays, {len(result["representation_examples"])} representation traces, {len(result["distance_sweep"])} task/distance checks; no model API was called.')
