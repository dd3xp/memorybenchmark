"""Check independent persistent facts and continuing task streams; no model API.

python -m scripts.check_experience_stream --output .runs/experience-stream-new
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from html import escape
import argparse
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import (
    ReferencePlanner, StationGame, capability_groups, compatible_worlds, load_design, replay_policy,
)
from scripts.check_station_capability import export_case, move


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design" / "station_capability_v2.json"
HISTORIES = {
    "visited_without_query": (4, frozenset()),
    "AB_query_then_abandon": (2, frozenset({"AB"})),
    "DE_query_then_abandon": (2, frozenset({"DE"})),
    "both_queries_then_abandon": (1, frozenset({"AB", "DE"})),
    "completed_AB": (2, frozenset({"AB"})),
    "completed_AB_with_optional_DE_query": (1, frozenset({"AB", "DE"})),
}


def group_for_task(design, task_id):
    required = design["tasks"][task_id]["required_kind"]
    return next(name for name, group in capability_groups(design).items() if required in group["kinds"])


def delivered_facts(events, task_run_id=None):
    return [{"source_event_id": e["event_id"], "task_run_id": e["task_run_id"],
             "station": e["delivered"]["feedback"]["station"],
             "capability": e["delivered"]["feedback"]["capability"]}
            for e in events if (task_run_id is None or e["task_run_id"] == task_run_id)
            and e["delivered"]["feedback"]["kind"] == "station_information"]


def render_overview(design, catalog):
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="500" viewBox="0 0 1100 500" font-family="Segoe UI, Microsoft YaHei, sans-serif">',
             '<rect width="1100" height="500" fill="#f7faf8"/>',
             '<text x="24" y="32" font-size="21" fill="#183b30">八项普通委托：实际反馈逐步区分世界</text>',
             '<text x="24" y="59" font-size="14" fill="#52635b">参考策略与规则校验，不是真实 Agent 记忆成绩；无历史列是当前检查点的局部分支。</text>']
    headers = ((26, "委托"), (126, "当前目标与资料"), (420, "相容世界数：执行前 → 后"),
               (720, "历史参考距离"), (895, "当前无历史距离"))
    for x, label in headers:
        parts.append(f'<text x="{x}" y="96" font-size="15" fill="#243d32">{label}</text>')
    for index, row in enumerate(catalog):
        y = 109 + index * 40
        reduced = row["candidate_counts_before"] != row["candidate_counts_after"]
        fill = "#e3efe7" if reduced else ("#ffffff" if index % 2 == 0 else "#eff4f0")
        parts.append(f'<rect x="16" y="{y}" width="1068" height="38" rx="5" fill="{fill}"/>')
        task = design["tasks"][row["task"]]
        values = (row["task"], task["name"], f'{row["candidate_counts_before"][0]} → {row["candidate_counts_after"][0]}',
                  row["history_reference_mean_distance"], row["no_history_reference_mean_distance"])
        for (x, _), value in zip(headers, values):
            parts.append(f'<text x="{x}" y="{y+25}" font-size="16" fill="#19392d">{escape(str(value))}</text>')
    parts.append('<text x="24" y="457" font-size="13" fill="#52635b">浅绿色行的相容集合缩小；相容集合由已交付反馈计算，不表示 Agent 已经学会。</text>')
    parts.append('<text x="24" y="480" font-size="13" fill="#52635b">同样剩两个世界，历史可能只帮助其中一类任务：集合大小不能代替信息的行动价值。</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def make_history(design, world, name, planners):
    game = StationGame(world, design)
    worlds = tuple(design["private_worlds"])
    if name.startswith("completed_AB"):
        game.start_task("T1")
        if name.endswith("optional_DE_query"):
            move(game, "J", "D")
            game.step({"type": "inspect"})
        replay_policy(game, planners["T1"], compatible_worlds(design, game.events))
        if not game.state.success:
            raise AssertionError("The ordinary-task history did not finish")
    else:
        groups = ("AB", "DE") if name == "both_queries_then_abandon" else (
            ("DE",) if name == "DE_query_then_abandon" else ("AB",))
        for group in groups:
            game.start_task("T1" if group == "AB" else "T3")
            move(game, "J", "A" if group == "AB" else "D")
            if name != "visited_without_query":
                game.step({"type": "inspect"})
            game.step({"type": "abandon"})
        if game.state.success:
            raise AssertionError("The failed-history fixture unexpectedly succeeded")
    possible = compatible_worlds(design, game.events)
    count, _ = HISTORIES[name]
    if len(possible) != count or world not in possible or not set(possible).issubset(worlds):
        raise AssertionError("The history was assigned information it did not deliver")
    return game


def paired_task(output, prefix, checkpoint, task_id, planner):
    design = checkpoint.design
    prior = compatible_worlds(design, checkpoint.events)
    observations, rows, retained_game = [], [], None
    for condition, information in (("history_reference", prior), ("no_history_reference", tuple(design["private_worlds"]))):
        game = deepcopy(checkpoint)
        observations.append(game.start_task(task_id))
        predicted = planner.initial(information)
        after = replay_policy(game, planner, information)
        row = export_case(output, f"{prefix}-{condition}", game)
        row.update(task=task_id, capability_group=group_for_task(design, task_id), condition=condition,
                   historical_worlds=list(prior), reference_initial_worlds=list(information),
                   reference_worlds_after_current_session=list(after),
                   analyst_worlds_after_full_history=list(compatible_worlds(design, game.events)),
                   prior_delivered_facts=delivered_facts(checkpoint.events),
                   current_delivered_facts=delivered_facts(game.events, game.task_run_id),
                   predicted_distance=str(predicted.distance))
        rows.append(row)
        if condition == "history_reference":
            retained_game = game
    if observations[0] != observations[1]:
        raise AssertionError("Paired branches have different public starting input")
    if not all(row["success"] for row in rows):
        raise AssertionError("A failed earlier task made a later task unsolvable")
    return rows, retained_game


def check(output):
    design = load_design(DESIGN)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a fresh output directory to preserve prior evidence")
    output.mkdir(parents=True, exist_ok=True)
    (output / "design_snapshot.json").write_text(json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8")
    worlds = tuple(design["private_worlds"])
    planners = {task: ReferencePlanner(design, task) for task in design["tasks"]}
    # Public parity includes the candidate-family rules, never an actual assignment.
    for task in design["tasks"]:
        public = [StationGame(world, design).start_task(task) for world in worlds]
        if any(response != public[0] for response in public[1:]):
            raise AssertionError("A hidden assignment leaks into public input")
        if planners[task].initial(worlds).distance != 10:
            raise AssertionError("A free universal strategy removed the intended information value")
    matrix, rows = [], []
    for name, (candidate_count, informative_groups) in HISTORIES.items():
        for task in ("T2", "T5"):
            group = group_for_task(design, task)
            by_condition = {"history_reference": [], "no_history_reference": []}
            for world in worlds:
                checkpoint = make_history(design, world, name, planners)
                pair, _ = paired_task(output, f"matrix-{name}-{task}-{world}", checkpoint, task, planners[task])
                for row in pair:
                    row.update(history=name, private_world=world, section="history_matrix")
                    by_condition[row["condition"]].append(row["distance"])
                rows.extend(pair)
            means = {condition: Fraction(sum(values), len(values)) for condition, values in by_condition.items()}
            expected = 8 if group in informative_groups else 10
            if means != {"history_reference": expected, "no_history_reference": 10}:
                raise AssertionError("Relevant and irrelevant history were conflated")
            matrix.append({"history": name, "candidate_worlds": candidate_count, "task": task, "group": group,
                           "history_reference_distance": str(means["history_reference"]),
                           "no_history_reference_distance": str(means["no_history_reference"])})
    # Several orders demonstrate that task identities are not a required learning/test split.
    # Each cleared branch is a local counterfactual at the retained history checkpoint.
    # It is NOT a separate self-consistent eight-task cleared-agent trajectory.
    orders = {"catalog": list(design["tasks"]), "reverse": list(reversed(design["tasks"])),
              "alternate": ["T3", "T1", "T5", "T2", "T6", "T4", "T8", "T7"]}
    streams = []
    for order_name, tasks in orders.items():
        per_position = {i: [] for i in range(len(tasks))}
        for world in worlds:
            game = StationGame(world, design)
            for index, task in enumerate(tasks):
                before = compatible_worlds(design, game.events)
                pair, game = paired_task(output, f"stream-{order_name}-{index+1}-{task}-{world}", game, task, planners[task])
                after = compatible_worlds(design, game.events)
                if not set(after).issubset(before):
                    raise AssertionError("Stable-world evidence unexpectedly expanded the candidate family")
                for row in pair:
                    row.update(order=order_name, sequence_index=index+1, private_world=world, section="task_stream")
                rows.extend(pair)
                per_position[index].append({"before": len(before), "after": len(after),
                                            "history_distance": pair[0]["distance"],
                                            "no_history_distance": pair[1]["distance"]})
        for index, values in per_position.items():
            before = sorted({row["before"] for row in values})
            after = sorted({row["after"] for row in values})
            streams.append({"order": order_name, "position": index+1, "task": tasks[index],
                            "candidate_counts_before": before, "candidate_counts_after": after,
                            "history_reference_mean_distance": str(Fraction(sum(r["history_distance"] for r in values), len(values))),
                            "no_history_reference_mean_distance": str(Fraction(sum(r["no_history_distance"] for r in values), len(values)))})
    catalog = [row for row in streams if row["order"] == "catalog"]
    if [(r["candidate_counts_before"], r["candidate_counts_after"]) for r in catalog[:3]] != [([4], [2]), ([2], [2]), ([2], [1])]:
        raise AssertionError("The main order no longer interleaves reuse and acquiring a new independent fact")
    report = {"kind": "multi_experience_design_validation_not_agent_memory_evaluation", "design_id": design["design_id"],
              "design_sha256": sha256(DESIGN.read_bytes()).hexdigest(),
              "source_sha256": {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in (
                  ROOT / "memorybenchmark/prototypes/station_capability.py", ROOT / "scripts/check_station_capability.py", Path(__file__).resolve())},
              "world_count": len(worlds), "independent_capability_groups": len(capability_groups(design)),
              "history_matrix": matrix, "task_streams": streams, "orders": orders, "cases": rows,
              "reference_objective": "expected current-task distance, then operations, uniform compatible-world prior, guaranteed success within task budget",
              "comparison": "local matched counterfactuals at the same actual retained-reference history, not a full cleared-agent stream",
              "planner_states": {task: planner.solve.cache_info().currsize for task, planner in planners.items()},
              "limitations": ["Reference strategies do not implement or observe native agent memory",
                              "The candidate family is enumerable evaluator-side information, not supplied agent knowledge",
                              "This tests multiple facts of one type, not general procedural memory",
                              "Three task orders are checked, not every possible curriculum",
                              "Graph observations do not uniquely identify internal retrieval"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "overview.svg").write_text(render_overview(design, catalog), encoding="utf-8")
    lines = ["# 多经验机制校验", "", "这是参考策略与实际规则重放，不是真实 Agent 的记忆实验。", "",
             "## 历史信息与当前任务", "", "| 历史 | 相容世界数 | 当前组 | 历史参考距离 | 无历史参考距离 |", "| --- | ---: | --- | ---: | ---: |"]
    for row in matrix:
        lines.append(f'| {row["history"]} | {row["candidate_worlds"]} | {row["group"]} | {row["history_reference_distance"]} | {row["no_history_reference_distance"]} |')
    lines += ["", "## 八项普通委托中的逐步获证", "", "| 次序 | 委托 | 执行前后相容世界数 | 历史参考距离 | 当前无历史分支距离 |", "| ---: | --- | --- | ---: | ---: |"]
    for row in catalog:
        lines.append(f'| {row["position"]} | {row["task"]} | {row["candidate_counts_before"]} → {row["candidate_counts_after"]} | {row["history_reference_mean_distance"]} | {row["no_history_reference_mean_distance"]} |')
    lines += ["", "无历史列是各检查点的局部分支，不能求和冒充一个独立 Agent 的全程表现。", "", "## 执行图", ""]
    for row in rows:
        lines.append(f'- [{row["name"]}]({row["svg"]}) · distance={row["distance"]}')
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    report = check(parser.parse_args().output)
    for row in report["history_matrix"]:
        print(row["history"], row["group"], "candidates=", row["candidate_worlds"], "distance=", row["history_reference_distance"], "/", row["no_history_reference_distance"])
    print(f'PASS: {len(report["cases"])} matched reference replays, {len(report["task_streams"])} order/task summaries; no model API.')
