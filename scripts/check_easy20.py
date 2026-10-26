"""Exhaustive Easy20 feasibility/evidence checks. No model or native memory score."""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import argparse
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design, neighbors
from memorybenchmark.prototypes.station_routes import feedback_policy, schedule, walk
from memorybenchmark.prototypes.station_session import EASY20_DESIGN
from scripts.check_station_capability import trace_graph, render_svg


def check(output):
    design = load_design(EASY20_DESIGN)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    rows, witnesses = [], []
    for world in design["private_worlds"]:
        game = StationGame(world, design)
        with (output / f"{world}-clear-cases.jsonl").open("w", encoding="utf-8") as clear_log:
            for task_id in design["tasks"]:
                checkpoint = deepcopy(game)
                for condition in ("retained_feedback_policy", "current_task_feedback_policy"):
                    current = deepcopy(checkpoint)
                    initial = current.start_task(task_id)
                    before = compatible_worlds(design, current.events)
                    feedback_policy(current, retain_history=condition == "retained_feedback_policy")
                    graph = trace_graph(current)
                    if not current.state.success or current.steps > 18:
                        raise AssertionError("Easy commission is not recoverable within budget")
                    for event in current.events:
                        if event["task_run_id"] == current.task_run_id and event["kind"] == "action":
                            assert event["movement_cost"] == (0 if not event["moved"] else next(
                                w for n, w in neighbors(design, event["from"]) if n == event["to"]))
                    rows.append({"world": world, "task": task_id, "condition": condition,
                                 "success": True, "distance": current.distance, "moves": len(graph["edges"]),
                                 "operations": current.steps, "prior_compatible_world_count": len(before)})
                    if condition == "retained_feedback_policy":
                        game = current
                    else:
                        assert initial["observation"] == initial_observation(checkpoint, task_id)
                        selected = [e for e in current.events if e["task_run_id"] == current.task_run_id]
                        clear_log.write(json.dumps({"task": task_id, "prior_compatible_worlds": list(before), "events": selected}, ensure_ascii=False) + "\n")
                    if world == "omega_1111" and task_id in ("T3", "T17"):
                        name = f"{task_id}-{condition}"
                        (output / f"{name}.svg").write_text(render_svg(design, graph, name), encoding="utf-8")
        (output / f"{world}-main-events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
        # A failed commission with no station feedback must not confer knowledge.
        failed = StationGame(world, design); failed.start_task("T1"); failed.step({"type": "abandon"})
        assert len(compatible_worlds(design, failed.events)) == 16
        failed.start_task("T3"); feedback_policy(failed)
        # Failure after a real query still supplies a reusable, independent fact.
        exposed = StationGame(world, design); exposed.start_task("T1"); walk(exposed, "A")
        exposed.step({"type": "inspect"}); exposed.step({"type": "abandon"})
        assert len(compatible_worlds(design, exposed.events)) == 8
        exposed.start_task("T3"); feedback_policy(exposed)
        assert exposed.distance == 10
        # The map allows visiting an unrelated station before finishing T1.
        optional = StationGame(world, design); optional.start_task("T1"); walk(optional, "D")
        optional.step({"type": "inspect"}); feedback_policy(optional)
        assert optional.state.success and optional.steps <= 18
        assert len(compatible_worlds(design, optional.events)) == 4
        witnesses.append({"world": world, "failure_without_feedback_recovers": failed.state.success,
                          "failure_with_feedback_next_distance": exposed.distance,
                          "optional_other_group_query_operations": optional.steps})
        (output / f"{world}-witnesses.json").write_text(json.dumps({
            "abandon_without_feedback": failed.events, "abandon_after_query": exposed.events,
            "optional_other_group_query": optional.events}, ensure_ascii=False), encoding="utf-8")
    means = {}
    for condition in ("retained_feedback_policy", "current_task_feedback_policy"):
        means[condition] = str(Fraction(sum(r["distance"] for r in rows if r["condition"] == condition), 16))
    assert means == {"retained_feedback_policy": "208", "current_task_feedback_policy": "240"}
    report = {"kind": "easy20_scripted_feasibility_not_native_agent_memory_results", "design_id": design["design_id"],
              "design_sha256": sha256(EASY20_DESIGN.read_bytes()).hexdigest(), "world_count": 16,
              "task_count": 20, "cases": rows, "witnesses": witnesses,
              "mean_stream_distance": means, "schedule": schedule(design),
              "limitations": ["scripted feedback policies, not native agents", "no exact unknown-world optimal-policy claim",
                              "actual delivered feedback determines later evidence; task position does not confer knowledge"]}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "worlds": 16, "tasks": 20, "matched_replays": len(rows),
                      "failure_and_free_exploration_witnesses": len(witnesses) * 3, "kind": report["kind"]}))
    return report


def initial_observation(checkpoint, task):
    game = deepcopy(checkpoint)
    return game.start_task(task)["observation"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args().output)
