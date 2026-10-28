"""Reproduce the reviewed 2026-10-28 Hermes pilot report without model calls.

Full evidence mode accepts private native sessions and the output of
analyze_station_native. Public mode redraws the report figures from the supplied
game-only projections. Reviewed cases are post-hoc illustrations, not a sample
from which an application rate is estimated.
"""
from __future__ import annotations

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil

from scripts.analyze_station_graphs import draw_graph
from scripts.audit_station_decisions import align_tools
from memorybenchmark.prototypes.station_choice import station_decisions


def read(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def compare(rows, projection):
    pairs = []
    for number in range(2, 21):
        task = f"T{number}"
        a, b = [next(r for r in rows if r["task_id"] == task and r["condition"] == condition)
                for condition in ("retain", "clear")]
        pairs.append({"task": task, "retain_success": a["success"], "clear_success": b["success"],
                      **{f"{condition}_{field}": row[field]
                         for condition, row in (("retain", a), ("clear", b))
                         for field in ("distance", "operations")}})
    both = [p for p in pairs if p["retain_success"] and p["clear_success"]]
    costs = {}
    for field in ("distance", "operations"):
        a, b = [sum(p[f"{c}_{field}"] for p in both) for c in ("retain", "clear")]
        costs[field] = {"retain": a, "clear": b, "reduction_fraction": (b-a)/b,
                        "fewer": sum(p[f"retain_{field}"] < p[f"clear_{field}"] for p in both),
                        "equal": sum(p[f"retain_{field}"] == p[f"clear_{field}"] for p in both),
                        "more": sum(p[f"retain_{field}"] > p[f"clear_{field}"] for p in both)}
    behavior = {}
    for condition in ("retain", "clear"):
        selected = [r for r in rows if r["condition"] == condition]
        choices = [stage["first_postcollection_branch_choice"] for r in selected
                   for stage in r["station_decisions"]["stages"]
                   if stage["first_postcollection_branch_choice"]]
        behavior[condition] = {
            "paired_tasks": len(selected), "successes": sum(r["success"] for r in selected),
            "observed_first_branches": len(choices),
            "nearest_first_branches": sum(c["pre_task_history"]["selected_is_geographically_nearest"] for c in choices),
            "history_excluded_first_branches": sum(c["pre_task_history"]["selected_historical_status"] == "known_nonmatch"
                                                   for c in choices),
            "unsupported_processes": sum(r["unsupported_processing_count"] for r in selected),
        }
    # For early stages, evaluator history may not determine the true capability.
    # Use actual inspect/process feedback, including a branch inspected but not
    # processed. Later feedback can establish actual capability for scoring; it
    # is never treated as evidence available to the earlier decision.
    sessions = {s["name"]: s for s in projection["sessions"]}
    for condition in behavior:
        actual = 0
        for row in (r for r in rows if r["condition"] == condition):
            session = sessions[row["name"]]
            feedback = [e["feedback"] for e in session["current_events"] + session["prior_evidence"]]
            for stage in row["station_decisions"]["stages"]:
                branch = stage["first_postcollection_branch_choice"]
                if branch:
                    capabilities = {f["capability"] for f in feedback
                                    if f.get("station") == branch["station"] and "capability" in f}
                    assert len(capabilities) == 1, "Actual first-branch capability is not established"
                    if capabilities == {stage["required_kind"]}:
                        actual += 1
        behavior[condition]["matching_first_branches"] = actual
    return {"kind": "descriptive_one_world_actual_history_checkpoint_comparison",
            "paired_tasks": 19, "both_success_pairs": len(both),
            "both_success_costs": costs, "branch_behavior": behavior, "pairs": pairs,
            "cost_scope": "Both-success subset only; all task outcomes remain in pairs and plots. Not an unconditional memory effect.",
            "branch_scope": "History status belongs to evaluator canonical feedback, not automatically to agent memory. Matching uses actual feedback.",
            "uncertainty": "One world and one evolving history; no significance or population effect estimate."}


# Small literal game facts reviewed after the completed pilot. No model reasoning.
REVIEWED = [
    ("T16", 0, [("E1", "elevation", "E1为高程匹配站")]),
    ("T16", 1, [("H", "drainage", "H 站处理水系资料"), ("W2", "contour", "W2 处理等高线成功")]),
    ("T20", 1, [("W1", "drainage", "水系在 W1 处理"), ("W2", "contour", "W2 处理等高线成功")]),
]


def audit_cases(root):
    pilot, design = read(root/"pilot.json"), read(root/"design.json")
    result = []
    for task, stage_index, facts in REVIEWED:
        previous = root/"baseline"
        for session in pilot["sessions"]:
            if session["task_id"] == task and session["condition"] == "retain":
                break
            if session["condition"] != "clear":
                previous = root/"sessions"/session["name"]/"memory-after"
        else:
            raise ValueError(f"Missing retained task {task}")
        folder = root/"sessions"/session["name"]
        memory = previous/"memories/MEMORY.md"
        text = memory.read_text(encoding="utf-8")
        events = [json.loads(s) for s in (folder/"events.jsonl").read_text(encoding="utf-8").splitlines()]
        messages = [json.loads(s) for s in (folder/"audit.jsonl").read_text(encoding="utf-8").splitlines()]
        graph = read(folder/"graph.json")
        decisions = station_decisions(design, events, graph["task_run_id"])
        windows = align_tools(events, graph["task_run_id"], messages, decisions)
        branch = decisions["stages"][stage_index]["first_postcollection_branch_choice"]
        number = windows["stages"][stage_index]["before_first_postcollection_branch_choice"]["model_request_count"]
        request = folder/"model"/f"{number:03d}-request.json"
        payload = json.dumps(read(request), ensure_ascii=False)
        first_payload = json.dumps(read(folder/"model/001-request.json"), ensure_ascii=False)
        start = next(e for e in events if e["kind"] == "task_started" and e["task_run_id"] == graph["task_run_id"])
        checked = []
        for station, capability, fragment in facts:
            assert fragment in text
            baseline = root/"baseline/memories/MEMORY.md"
            assert not baseline.exists() or fragment not in baseline.read_text(encoding="utf-8")
            encoded = json.dumps(fragment, ensure_ascii=False)[1:-1]
            assert encoded in payload and encoded in first_payload
            support = [e["event_id"] for e in events if e["event_id"] < start["event_id"]
                       and e.get("delivered", {}).get("feedback", {}).get("station") == station
                       and e["delivered"]["feedback"].get("capability") == capability]
            assert support
            checked.append({"station": station, "capability": capability, "literal_game_memory_fragment": fragment,
                            "prior_direct_support_event_ids": support,
                            "fragment_present_in_input_memory_and_first_and_decision_requests": True})
        result.append({"task": task, "stage_index": stage_index, "session": session["name"],
                       "required_kind": design["tasks"][task]["stages"][stage_index]["required_kind"],
                       "first_branch": branch, "reviewed_facts": checked,
                       "model_request_for_branch_choice": number,
                       "input_memory_sha256": digest(memory), "decision_request_sha256": digest(request),
                       "source_events_sha256": digest(folder/"events.jsonl"),
                       "source_audit_sha256": digest(folder/"audit.jsonl")})
    return {"kind": "posthoc_literal_game_fact_delivery_and_action_compatibility_audit",
            "selection": "T16 illustrates different behavior in its two stages; T20 illustrates another mismatching choice. Not a representative sample.",
            "scope": "Verifies authored fact, prior game support, and presence in actual inputs before fork departure. Does not prove internal causal use or conscious disregard.",
            "cases": result, "analysis_sha256": digest(Path(__file__))}


def figures(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    measurements, projection = [read(output/f"{name}.json.gz") for name in ("measurements", "trace-projection")]
    rows = measurements["rows"]
    tasks = [f"T{i}" for i in range(1, 21)]
    colors = ("#0072B2", "#D55E00")
    def save(fig, name):
        for suffix in ("png", "svg", "pdf"):
            fig.savefig(output/f"{name}.{suffix}", dpi=180, facecolor="white")
        plt.close(fig)
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none", "pdf.fonttype": 42}):
        fig, axes = plt.subplots(2, 1, figsize=(12, 7.8), sharex=True)
        for ax, field, label in zip(axes, ("distance", "operations"), ("Actual walked distance", "Game operations")):
            for index, condition in enumerate(("retain", "clear")):
                series = [next((r for r in rows if r["task_id"] == task and
                                (r["condition"] == condition or condition == "retain" and r["condition"] == "prefix")), None)
                          for task in tasks]
                ax.plot(range(1, 21), [r[field] if r else float("nan") for r in series],
                        color=colors[index], marker=("o", "s")[index], linestyle=("-", "--")[index],
                        label=("Retained native memory (T1 prefix)", "Current-task baseline-memory probe")[index])
                failed = [(i, r[field]) for i, r in enumerate(series, 1) if r and not r["success"]]
                ax.scatter([x for x,y in failed], [y for x,y in failed], color="black", marker="x", s=100, zorder=5)
            ax.set(ylabel=label, ylim=(0, 78))
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
        axes[-1].set_xticks(range(1, 21), tasks)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(.08,.95), frameon=False, ncol=2, fontsize=9)
        fig.suptitle("Native Hermes: all 20 commissions, both outcomes and costs", x=.08, ha="left", y=.98, fontsize=14)
        fig.text(.08,.02,"Black crosses: explicit abandon (four sessions). Low cost does not imply success. T1 has no clear probe.\nOne world, one history, one observation per condition/task; no uncertainty intervals.",fontsize=9)
        fig.subplots_adjust(left=.08, right=.98, top=.86, bottom=.14, hspace=.18)
        save(fig,"all-task-costs")
        # A post-hoc example with verified inputs for both stages; retain every move.
        design = {"public": projection["public_map"], "tasks": projection["tasks"]}
        fig, axes = plt.subplots(1,2,figsize=(14,8.5))
        for index, condition in enumerate(("retain", "clear")):
            row = next(r for r in rows if r["task_id"] == "T16" and r["condition"] == condition)
            graph = next(s["graph"] for s in projection["sessions"] if s["name"] == row["name"])
            draw_graph(axes[index],design,graph,row,f'T16 / {("Retained native memory", "Baseline native memory")[index]}',focus_task=True)
        fig.suptitle("T16: matching first choice in stage 1, mismatching first choice in stage 2", x=.05, ha="left", y=.98, fontsize=14)
        fig.text(.05,.92,"Post-hoc illustration; corresponding literal facts are verified in the actual decision inputs. All tasks are reported separately.",fontsize=9)
        fig.text(.05,.025,"Arrows and numbers: all actual moves in order. Dashed red: trip containing unsupported processing.\nGrey: public roads. Text lists station operations. Fact delivery and action compatibility do not prove internal memory causality.",fontsize=9)
        fig.subplots_adjust(left=.05,right=.98,top=.85,bottom=.32,wspace=.20)
        save(fig,"t16-reviewed-traces")
    write(output/"figure-provenance.json", {"kind": "descriptive_real_native_agent_pilot",
        "matplotlib_version": matplotlib.__version__, "png_dpi": 180,
        "selection": "All 20 tasks and all failures; T16 is an explicitly post-hoc paired trace illustration.",
        "transformations": ["No smoothing", "T1 clear is missing, not zero", "Actual ordered edges, node events, and raw task costs"],
        "source_measurements_gzip_sha256": digest(output/"measurements.json.gz"),
        "source_trace_projection_gzip_sha256": digest(output/"trace-projection.json.gz"),
        "analysis_sha256": digest(Path(__file__)), "uncertainty": "No population estimate; one sampled world and evolving history."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, help="Private completed native run; omit to redraw public data")
    parser.add_argument("--analysis", type=Path, help="Output of analyze_station_native, required with --run")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.run:
        if not args.analysis:
            parser.error("--analysis is required with --run")
        measurements = read(args.analysis/"measurements.json")
        assert measurements["world"] == "omega_3051" and len(measurements["rows"]) == 39
        for name in ("measurements", "trace-projection"):
            raw = (args.analysis/f"{name}.json").read_bytes()
            (args.output/f"{name}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
        write(args.output/"comparison.json", compare(measurements["rows"], read(args.analysis/"trace-projection.json")))
        write(args.output/"reviewed-cases.json", audit_cases(args.run))
        for suffix in ("png", "svg", "pdf"):
            shutil.copyfile(args.analysis/f"native-trace-comparison.{suffix}", args.output/f"fixed-t3-t17-traces.{suffix}")
    figures(args.output)
    print(json.dumps({"output": str(args.output), "model_calls": 0}))


if __name__ == "__main__":
    main()
