"""Recompute exploratory metrics from a hash-verified, sealed evidence ZIP.

python -m scripts.score_station_metrics --inputs PATH --output NEW_DIRECTORY
No model, agent worker, live game, or remote service is invoked.
"""
from __future__ import annotations

from memorybenchmark.event_store import read_archive_events
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from memorybenchmark.prototypes.station_capability import StationGame, map_world
from memorybenchmark.prototypes.station_metrics import VERSION, compare_streams, score_stream, summarize_stream
from memorybenchmark.prototypes.station_routes import feedback_policy


PLAN = {
    "protocol": VERSION,
    "status": "Exploratory post-hoc metric review, not a preregistered confirmatory analysis",
    "primary_metric": "Station submission accuracy: successful explicit process actions divided by all explicit process attempts, pooled across commissions",
    "failure_scope": "An explicit process at an incompatible station is an incorrect submission; moving, visiting, inspecting, and final camp submit are not station submission attempts",
    "attempt_counting": "Every executed process action counts once, including retries; repeated visits or inspections do not create attempts; zero attempts gives null, not a perfect score",
    "completion_companion": "Always report completed commissions / all commissioned tasks and the count of tasks with no process attempt alongside submission accuracy",
    "legacy_visit_rule": "The earlier any-wrong-entry strict task score and visit matching rates remain supplementary diagnostics, not the primary submission accuracy",
    "execution_scope": "Retrospective scoring of complete observed traces, not early termination; later feedback remains available for later sessions under the original native memory condition",
    "diagnostic_first_choice": "First actual station entry in each active requirement, including precollection; this visit-based diagnostic does not define submission correctness",
    "sensitivity_choices": ["first postcollection station entry", "first process result", "all station entries"],
    "denominator": "Primary accuracy: all actual process attempts, including wrong attempts; companion completion: all commissioned tasks; stage, historical-opportunity, and graph values are supplementary diagnostics",
    "historical_opportunity": "At least one matching station determined by actual delivered feedback before the session and public rules",
    "historical_unreacquired_first_match": "Historically determined requirement, correct first entry, and current-session feedback alone does not yet determine a matching type; divide by every historically determined requirement, including reacquired/missing choices",
    "knowledge": "Logical support over the public candidate family; no uniform-probability assumption for opportunity gates and no claim that the agent saved/read a fact",
    "retention": "Raw reuse/accuracy by sessions since last directly disclosed matching capability; exclude intervals whose intervening feedback independently rederives the answer, retain current-session reacquisition as a separate outcome in the denominator",
    "retention_limit": "Descriptive environment-unrefreshed gaps; native memory rehearsal, material/task mix, and exposure histories are not controlled",
    "correction": "Report later opportunities after actual negative station feedback for the same type/material pair; query/processing feedback sources and process-only sources are separate, and repeated station entry versus repeated failed processing are separate outcomes; no opportunity is null, never perfect correction",
    "graph_cost": "Nonoverlapping closed station spurs with no task progress, prior-session-determined incompatible capability, and no new full-history information; retain edge IDs and costs",
    "reference": "Full-information physical minimum through ordered collection/processing stages and final camp, accepting any matching station; task quality reference, not an unknown-world memory oracle",
    "negative_transfer": "Signed paired task differences with wins/ties/losses; do not infer interference or convert zero observed harm to perfect resistance",
    "uncertainty": "One independent run per condition; no task/stage bootstrap CI, p-value, or significance claim",
    "aggregation": "Pool process successes and attempts over the full20 commissions; do not average per-task percentages; followup19 is supplementary; retain stage/graph diagnostics without a four-dimension composite",
    "null_validation": "Identical trace relabelling and independent deterministic stateless scripted streams only; native stochastic null is untested",
}


def read_json(bundle, name):
    return json.loads(bundle.read(name).decode("utf-8-sig"))


def load_inputs(path):
    loaded, graph_checks = {}, 0
    with ZipFile(path) as bundle:
        manifest = read_json(bundle, "input-manifest.json")
        if set(bundle.namelist()) != set(manifest) | {"input-manifest.json"}:
            raise ValueError("Evidence package membership differs from the manifest")
        for name, expected in manifest.items():
            body = bundle.read(name)
            if len(body) != expected["bytes"] or sha256(body).hexdigest() != expected["sha256"]:
                raise ValueError("Input checksum mismatch: " + name)
        for condition in ("retain", "clear"):
            design = read_json(bundle, f"{condition}/design.json")
            pilot = read_json(bundle, f"{condition}/pilot.json")
            analysis = read_json(bundle, f"{condition}/analysis.json")
            if (pilot["status"] != "completed" or analysis["status"] != "completed_and_audited"
                    or pilot["memory_condition"] != condition):
                raise ValueError("Expected an audited completed run")
            if len(pilot["sessions"]) != analysis["tasks"] or analysis["experiment_id"] != pilot["experiment_id"]:
                raise ValueError("Run identities or counts differ")
            events = read_archive_events(bundle, f"{condition}/events.jsonl")
            rows = {r["task_id"]: r for r in analysis["rows"]}
            for session in pilot["sessions"]:
                prefix = f'{condition}/sessions/{session["name"]}'
                graph = read_json(bundle, prefix + "/graph.json")
                summary = read_json(bundle, prefix + "/summary.json")
                current = [e for e in events if e["task_run_id"] == graph["task_run_id"]]
                moves = [e for e in current if e.get("moved")]
                if not session["infrastructure_ok"] or summary["success"] != rows[session["task_id"]]["success"]:
                    raise ValueError("Session status differs from audited analysis")
                if ([e["id"] for e in graph["edges"]] != [e["event_id"] for e in moves]
                        or graph["distance"] != sum(e["movement_cost"] for e in moves)
                        or graph["distance"] != summary["distance"]):
                    raise ValueError("Graph projection loses canonical movement evidence")
                for edge, event in zip(graph["edges"], moves):
                    if (edge["source"], edge["target"], edge["weight"]) != (event["from"], event["to"], event["movement_cost"]):
                        raise ValueError("Graph edge attributes differ from environment events")
                stationary = [e for e in current if e["kind"] == "action" and not e.get("moved")]
                if ([e["event_id"] for e in graph["node_events"]] != [e["event_id"] for e in stationary]
                        or any(n["action"] != e["action"] or n["feedback"] != e["delivered"]["feedback"]
                               for n, e in zip(graph["node_events"], stationary))):
                    raise ValueError("Graph projection loses stationary feedback")
                graph_checks += 1
            loaded[condition] = {"design": design, "pilot": pilot, "analysis": analysis, "events": events}
        a, b = (loaded[c]["pilot"] for c in ("retain", "clear"))
        for key in ("agent", "model_alias", "tasks", "seed", "world", "station_assignment_sha256", "map_configuration_sha256",
                    "archive_sha256", "prompt_protocol", "feedback_protocol", "action_policy", "movement_mode",
                    "max_turns", "final_turns", "wall_seconds", "reasoning_effort"):
            if a[key] != b[key]:
                raise ValueError("Unmatched experiment configuration: " + key)
        if a["experiment_id"] == b["experiment_id"] or loaded["retain"]["design"] != loaded["clear"]["design"]:
            raise ValueError("Runs must be separate and use an identical map")
    return loaded, {"input_zip_sha256": sha256(Path(path).read_bytes()).hexdigest(),
                    "manifest": manifest, "files_verified": len(manifest), "graph_projections_verified": graph_checks,
                    "new_model_calls": 0}


def calibration(design, scored):
    same = compare_streams(scored, scored)
    if any(v["mean_signed_physical_efficiency_lift"] != 0 or v["both_success_distance_reduction"] != 0
           or v["strict_success_rate_lift"] != 0
           or v["processing_accuracy_lift"] != 0
           for v in same["cohorts"].values()):
        raise AssertionError("Identical outcomes are not a zero contrast")
    streams = []
    for condition in ("retain", "clear"):
        game = StationGame(map_world(design), design)
        for task_id in design["tasks"]:
            game.start_task(task_id)
            feedback_policy(game, retain_history=False)
        streams.append(score_stream(design, game.events, condition=condition))
    null = compare_streams(*streams)
    for cohort in null["cohorts"].values():
        if (cohort["mean_signed_physical_efficiency_lift"] != 0 or cohort["both_success_distance_reduction"] != 0
                or cohort["strict_success_rate_lift"] != 0 or cohort["processing_accuracy_lift"] != 0):
            raise AssertionError("Independent deterministic stateless policies have a nonzero treatment contrast")
    summaries = [summarize_stream(s)["followup"]["stages"] for s in streams]
    if summaries[0]["historical_unreacquired_first_match"] != summaries[1]["historical_unreacquired_first_match"]:
        raise AssertionError("Condition labels alter descriptive metric values")
    return {"identical_trace_contrast_zero": True, "independent_deterministic_stateless_null": null["cohorts"],
            "stateless_null_historical_unreacquired_first_match": summaries[0]["historical_unreacquired_first_match"],
            "scope": "Deterministic evaluator checks, not stochastic calibration of a native agent",
            "native_stochastic_null_validated": False, "new_model_calls": 0}


def write_csv(path, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False, sort_keys=True) if isinstance(v, (dict, list)) else v
                         for k, v in row.items()} for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    loaded, validation = load_inputs(args.inputs)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    save = lambda name, obj: (output / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Materialize the exploratory definition before executing the scoring pass.
    save("metric-plan.json", PLAN)
    repo = Path(__file__).resolve().parents[1]
    source_names = ("scripts/score_station_metrics.py", "memorybenchmark/prototypes/station_metrics.py",
                    "memorybenchmark/prototypes/station_capability.py", "memorybenchmark/prototypes/station_routes.py")
    source_hashes = {}
    for name in source_names:
        body = (repo / name).read_bytes()
        source_hashes[name] = sha256(body).hexdigest()
        destination = output / "scorer-source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
    scored = {c: score_stream(d["design"], d["events"], condition=c, metadata=d["analysis"]["rows"])
              for c, d in loaded.items()}
    summaries = {c: summarize_stream(s) for c, s in scored.items()}
    comparison = compare_streams(scored["retain"], scored["clear"])
    swapped = compare_streams(scored["clear"], scored["retain"])
    for cohort in comparison["cohorts"]:
        for key in ("mean_signed_physical_efficiency_lift", "mean_signed_distance_saved_per_physical_bound",
                    "strict_success_rate_lift", "processing_accuracy_lift"):
            if abs(comparison["cohorts"][cohort][key] + swapped["cohorts"][cohort][key]) > 1e-12:
                raise AssertionError("A signed contrast fails label-swap antisymmetry")
    validation["signed_contrast_label_swap_verified"] = True
    controls = calibration(loaded["retain"]["design"], scored["retain"])
    pilots = {c: {k: d["pilot"][k] for k in ("experiment_id", "agent", "model_alias", "reasoning_effort", "world", "seed",
                  "map_configuration_sha256", "station_assignment_sha256", "prompt_protocol", "feedback_protocol", "action_policy", "movement_mode")}
              for c, d in loaded.items()}
    result = {"protocol": VERSION, "plan": PLAN, "run_provenance": pilots,
              "scorer_sha256": source_hashes, "python_version": sys.version,
              "summary": summaries, "comparison": comparison, "calibration": controls,
              "source_verification": validation,
              "model_usage": {c: d["analysis"]["model_usage"] for c, d in loaded.items()},
              "infrastructure_attempts": {c: len(d["pilot"].get("attempt_history", [])) for c, d in loaded.items()},
              "attempt_cost_scope": "Audited valid session costs only; archived transport-failure attempt traffic is not included"}
    save("metrics.json", result)
    for c in scored:
        save(c + "-detail.json", scored[c])
    for key, filename in (("tasks", "tasks.csv"), ("stages", "stages.csv"), ("station_trips", "station-trips.csv"),
                          ("negative_feedback_sources", "negative-feedback.csv"),
                          ("processing_attempts", "processing-attempts.csv")):
        write_csv(output / filename, [r for c in scored for r in scored[c][key]])
    strict_rows = []
    for condition, stream in scored.items():
        for task in stream["tasks"]:
            wrong = task["first_wrong_station_entry"] or {}
            strict_rows.append({
                "condition": condition, "task_id": task["task_id"],
                "strict_success": task["strict_success"], "submitted": task["success"],
                "failure_reason": task["strict_failure_reason"],
                "wrong_station_entry_count": task["wrong_station_entry_count"],
                "first_wrong_event_id": wrong.get("event_id"),
                "first_wrong_stage": wrong["stage_index"] + 1 if wrong else None,
                "first_wrong_station": wrong.get("station"),
                "required_kind": wrong.get("required_kind"),
                "actual_capability": wrong.get("actual_capability")})
    write_csv(output / "strict-task-outcomes.csv", strict_rows)
    legacy = {"protocol": VERSION, "metric": "Legacy diagnostic: completed commission with no nonmatching station entries",
               "execution_scope": PLAN["execution_scope"],
               "all_tasks": {c: s["all_tasks"]["strict_success_rate"] for c, s in summaries.items()},
               "followup": {c: s["followup"]["strict_success_rate"] for c, s in summaries.items()},
               "all_tasks_rate_lift": comparison["cohorts"]["all_tasks"]["strict_success_rate_lift"]}
    save("strict-success.json", legacy)
    primary = {"protocol": VERSION, "metric": PLAN["primary_metric"],
               "attempt_counting": PLAN["attempt_counting"],
               "all_tasks": {c: {"submission_accuracy": s["all_tasks"]["processing_accuracy"],
                                 "incorrect_submissions": s["all_tasks"]["totals"]["unsupported_processing_count"],
                                 "completion_rate": s["all_tasks"]["completion_rate"],
                                 "tasks_without_processing_attempts": s["all_tasks"]["tasks_without_processing_attempts"]}
                             for c, s in summaries.items()},
               "followup": {c: s["followup"]["processing_accuracy"] for c, s in summaries.items()},
               "all_tasks_accuracy_lift": comparison["cohorts"]["all_tasks"]["processing_accuracy_lift"]}
    save("submission-accuracy.json", primary)
    print(json.dumps({"primary_submission_accuracy": primary}, ensure_ascii=False))
    print(json.dumps({"output": str(output), "followup": {c: {
        "tasks": s["followup"]["tasks"], "completed_submissions": s["followup"]["successes"],
        "processing_accuracy": s["followup"]["processing_accuracy"],
        "first_any_accuracy": s["followup"]["stages"]["first_any_accuracy"],
        "historical_unreacquired_first_match": s["followup"]["stages"]["historical_unreacquired_first_match"],
        "historical_opportunity_coverage": s["followup"]["stages"]["historical_opportunity_coverage"],
        "totals": s["followup"]["totals"]} for c, s in summaries.items()},
                      "comparison": comparison["cohorts"]["followup"],
                      "calibration": controls}, ensure_ascii=False))


if __name__ == "__main__":
    main()
