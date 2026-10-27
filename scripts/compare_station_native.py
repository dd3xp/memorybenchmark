"""Compare completed native pilots descriptively, retaining every failed task."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def totals(rows):
    fields = ("distance", "moves", "operations", "query_count", "unsupported_processing_count",
              "historically_repeated_queries", "llm_calls", "main_calls", "final_calls")
    return {"sessions": len(rows), "successes": sum(r["success"] for r in rows),
            **{field: sum(r[field] for r in rows) for field in fields}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, action="append", required=True,
                        help="completed analyze_station_native output; repeat per agent")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-task", help="optional explicitly selected retained cross-agent trace illustration")
    args = parser.parse_args()
    if len(args.analysis) < 2:
        parser.error("Provide at least two completed native-agent analyses")
    datasets = [read(root / "measurements.json") for root in args.analysis]
    projections = [read(root / "trace-projection.json") for root in args.analysis]
    assert len({d["agent"] for d in datasets}) == len(datasets), "Duplicate agent labels"
    for field in ("world", "model_alias"):
        assert len({d[field] for d in datasets}) == 1, f"Different {field}"
    assert all(p["public_map"] == projections[0]["public_map"] and p["tasks"] == projections[0]["tasks"]
               for p in projections), "Different map or tasks"
    tasks = [r["task_id"] for r in datasets[0]["rows"] if r["condition"] != "clear"]
    if args.trace_task and args.trace_task not in tasks:
        parser.error("Selected trace task is absent from the completed pilots")
    summaries = []
    for data in datasets:
        main_rows = [r for r in data["rows"] if r["condition"] != "clear"]
        clear_rows = [r for r in data["rows"] if r["condition"] == "clear"]
        assert [r["task_id"] for r in main_rows] == tasks
        assert [r["task_id"] for r in clear_rows] == tasks[1:]
        paired = []
        for task in tasks[1:]:
            a = next(r for r in main_rows if r["task_id"] == task)
            b = next(r for r in clear_rows if r["task_id"] == task)
            both_success = a["success"] and b["success"]
            paired.append({"task": task, "main_success": a["success"], "clear_success": b["success"],
                           "main_distance": a["distance"], "clear_distance": b["distance"],
                           "distance_difference_clear_minus_main_if_both_success": b["distance"]-a["distance"] if both_success else None})
        both = [p for p in paired if p["main_success"] and p["clear_success"]]
        first = [r["station_decisions"]["first_postcollection_station"] for r in main_rows]
        summaries.append({"agent": data["agent"], "all": totals(data["rows"]), "main": totals(main_rows),
                          "clear": totals(clear_rows), "pairs": paired,
                          "both_success_pairs": len(both),
                          "both_success_main_distance": sum(p["main_distance"] for p in both),
                          "both_success_clear_distance": sum(p["clear_distance"] for p in both),
                          "first_station_nearest_main_count": sum(bool(f and f["pre_task_history"]["selected_is_geographically_nearest"]) for f in first),
                          "first_station_known_nonmatch_from_actual_history_main_count": sum(bool(f and f["pre_task_history"]["selected_historical_status"] == "known_nonmatch") for f in first),
                          "native_memory_carrier": sorted({r["native_memory_carrier"] for r in main_rows}),
                          "input_memory_delivery_scope": "Automatic carrier body only; not relevance or causal use. SOP and skill reads are audited separately.",
                          "input_memory_body_delivered_main_count": sum(r["native_global_memory_changed_from_baseline"] and r["native_global_memory_body_in_first_input"] for r in main_rows)})
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    artifact = {"kind": "single_world_native_agent_comparison_not_population_or_causal_effect",
                "world": datasets[0]["world"], "model_alias": datasets[0]["model_alias"], "tasks": tasks,
                "agents": summaries,
                "source_measurements_sha256": {d["agent"]: sha256((p / "measurements.json").read_bytes()).hexdigest() for p, d in zip(args.analysis, datasets)},
                "analysis_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "limitations": ["one sampled world and one main history per native agent",
                                "clear runs are current-task probes, not independent complete streams",
                                "native prompts, tools, context management and acquired histories differ",
                                "shared task instructions specify bounded completion, not an explicit weighted-distance minimization objective",
                                "historical evidence is not proof of saved or delivered memory",
                                "failed low-distance tasks are not efficient successes"]}
    (output / "comparison.json").write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none"}):
        x = list(range(1, len(tasks)+1))
        for field, ylabel, filename in (("distance", "Walked distance", "native-agents-all-tasks"),
                                         ("operations", "Game operations", "native-agents-all-operations")):
            fig, axes = plt.subplots(len(datasets), 1, figsize=(12, 3*len(datasets)+1), sharex=True, sharey=True, squeeze=False)
            top = max(r[field] for data in datasets for r in data["rows"]) + 4
            for ax, data in zip(axes[:, 0], datasets):
                for condition, color, marker, style, label in (("main", "#0072B2", "o", "-", "Retained native memory (T1 prefix)"),
                                                              ("clear", "#D55E00", "s", "--", "Current-task baseline-memory probe")):
                    rows = [next((r for r in data["rows"] if r["task_id"] == task and (r["condition"] == "clear") == (condition == "clear")), None) for task in tasks]
                    ax.plot(x, [r[field] if r else float("nan") for r in rows], color=color, marker=marker, linestyle=style, label=label)
                    failures = [(i, r[field]) for i, r in zip(x, rows) if r and not r["success"]]
                    if failures:
                        ax.scatter(*zip(*failures), marker="x", color="black", s=90, linewidths=1.7, zorder=5)
                ax.set_title({"ga": "GenericAgent (updated upstream)", "hermes": "Hermes (native memory and skills)"}[data["agent"]], loc="left", fontsize=12)
                ax.set(ylabel=ylabel, ylim=(0, top))
                ax.spines[["top", "right"]].set_visible(False)
                ax.grid(axis="y", alpha=.2)
            axes[0, 0].legend(frameon=False, fontsize=9, ncol=2, loc="upper center", bbox_to_anchor=(.5, 1.28))
            axes[-1, 0].set_xticks(x, tasks)
            fig.suptitle("Native agents on the same Easy20 map and hidden world", x=.08, ha="left", fontsize=15)
            fig.text(.08, .025, "Every task is shown. One observation per condition/task; no uncertainty intervals.\nBlack crosses mark unsuccessful tasks. Native contexts and acquired histories differ; these are descriptive pilot results.", fontsize=9)
            fig.subplots_adjust(left=.08, right=.98, bottom=.16, top=.83, hspace=.5)
            for suffix in ("png", "svg", "pdf"):
                fig.savefig(output / f"{filename}.{suffix}", dpi=180, facecolor="white")
            plt.close(fig)
        if args.trace_task:
            from scripts.analyze_station_graphs import draw_graph
            fig, axes = plt.subplots(1, len(datasets), figsize=(7*len(datasets), 7), squeeze=False)
            design = {"public": projections[0]["public_map"], "tasks": projections[0]["tasks"]}
            for ax, data, projection in zip(axes[0], datasets, projections):
                row = next(r for r in data["rows"] if r["task_id"] == args.trace_task and r["condition"] != "clear")
                graph = next(p["graph"] for p in projection["sessions"] if p["name"] == row["name"])
                label = {"ga": "Updated GenericAgent", "hermes": "Hermes"}[data["agent"]]
                draw_graph(ax, design, graph, row, f"{label} / retained native memory", focus_task=True)
            fig.suptitle(f"{args.trace_task}: actual retained trajectories across native agents", x=.05, ha="left", fontsize=16)
            fig.text(.05, .91, "Post hoc illustration; every session remains in the complete tables and all-task plots.", fontsize=10)
            fig.text(.05, .025, "Arrows and numbers are actual movement order; node operations are listed below each graph.\nDistance and operation count are separate descriptions. The task brief does not explicitly minimize weighted distance.", fontsize=9)
            fig.subplots_adjust(left=.05, right=.97, top=.84, bottom=.28, wspace=.16)
            for suffix in ("png", "svg", "pdf"):
                fig.savefig(output / f"native-agents-{args.trace_task.lower()}-traces.{suffix}", dpi=180, facecolor="white")
            plt.close(fig)
    (output / "figure-manifest.json").write_text(json.dumps({
        "kind": artifact["kind"], "source_comparison_sha256": sha256((output / "comparison.json").read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__, "png_dpi": 180,
        "transforms": ["ordered task sequence", "all observed distances and operation counts", "shared axes per quantity", "no smoothing or aggregation"],
        "uncertainty": "one observation per condition/task; no uncertainty intervals",
        "missing": "no clear probe for T1", "failures": "preserved and marked with black crosses",
        "selected_trace_task": args.trace_task, "trace_selection": "post hoc illustration; no filtering of measured sessions",
        "figures_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob("native-agents-*")) if p.suffix in (".png", ".svg", ".pdf")}
    }, indent=2), encoding="utf-8")
    print(json.dumps({"agents": [d["agent"] for d in datasets], "output": str(output)}))


if __name__ == "__main__":
    main()
