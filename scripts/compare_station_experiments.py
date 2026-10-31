"""Compare two already audited independent runs; this never schedules an agent."""
import argparse
from pathlib import Path

from memorybenchmark.prototypes.station_independent import PROTOCOL, read
from memorybenchmark.watch import atomic_json as save_json


def compare(retain, clear):
    roots = {"retain": Path(retain).resolve(), "clear": Path(clear).resolve()}
    pilots = {c: read(p / "pilot.json") for c, p in roots.items()}
    results = {c: read(p / "analysis.json") for c, p in roots.items()}
    for condition in roots:
        p = pilots[condition]
        if p.get("protocol") != PROTOCOL or p.get("status") != "completed" or p.get("memory_condition") != condition:
            raise ValueError("Two completed independent runs with the declared conditions are required")
        if results[condition].get("experiment_id") != p["experiment_id"]:
            raise ValueError("Analysis belongs to another run")
    if roots["retain"] == roots["clear"] or pilots["retain"]["experiment_id"] == pilots["clear"]["experiment_id"]:
        raise ValueError("Runs must be separate")
    for key in ("agent", "model_alias", "tasks", "seed", "world", "station_assignment_sha256", "map_configuration_sha256",
                "archive_sha256", "prompt_protocol", "feedback_protocol", "action_policy", "movement_mode", "max_turns", "final_turns", "wall_seconds"):
        if pilots["retain"][key] != pilots["clear"][key]:
            raise ValueError("Unmatched experiment configuration: " + key)
    indexed = {c: {r["task_id"]: r for r in a["rows"]} for c, a in results.items()}
    tasks = pilots["retain"]["tasks"]
    costs = ("distance", "moves", "operations", "llm_calls", "query_count", "unsupported_processing_count")
    def totals(condition, chosen):
        return {k: sum(indexed[condition][t][k] for t in chosen) for k in costs}
    common_success = [t for t in tasks[1:] if all(indexed[c][t]["success"] for c in roots)]
    a, b = (totals(c, common_success) for c in ("retain", "clear"))
    return {"kind": "independent_longitudinal_comparison", "agent": pilots["retain"]["agent"],
        "experiment_ids": {c: p["experiment_id"] for c, p in pilots.items()},
        "all_task_totals": {c: results[c]["totals"] for c in roots},
        "successes": {c: results[c]["successes"] for c in roots},
        "both_success_followup_tasks": common_success,
        "both_success_totals": {"retain": a, "clear": b},
        "both_success_reduction_percent": {k: 100 * (1 - a[k] / b[k]) if b[k] else None for k in costs},
        "first_task_no_history_controls": {c: indexed[c][tasks[0]] for c in roots},
        "scope": "each run has its own actual history; task-level differences do not hold acquired experience constant"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retain", type=Path, required=True)
    parser.add_argument("--clear", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    save_json(args.output, compare(args.retain, args.clear))
