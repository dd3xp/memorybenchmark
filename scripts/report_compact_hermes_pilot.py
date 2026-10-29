"""Report published compact-feedback Hermes game traces; no model calls."""
from __future__ import annotations

import argparse
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path

from scripts.analyze_station_graphs import draw_graph


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def summarize(signal):
    rows = signal["rows"]
    pairs = signal["pairs"]
    assert len(rows) == 39 and len(pairs) == 19
    assert all(p["retain_success"] and p["clear_success"] for p in pairs)
    costs = {}
    for field in ("operations", "distance"):
        a, b = [sum(p[f"{condition}_{field}"] for p in pairs) for condition in ("retain", "clear")]
        costs[field] = {"retain": a, "clear": b, "reduction_fraction": (b-a)/b,
                        "fewer": sum(p[f"retain_{field}"] < p[f"clear_{field}"] for p in pairs),
                        "equal": sum(p[f"retain_{field}"] == p[f"clear_{field}"] for p in pairs),
                        "more": sum(p[f"retain_{field}"] > p[f"clear_{field}"] for p in pairs)}
    main = [row for row in rows if row["condition"] != "clear"]
    return {"kind": "descriptive_one_world_actual_history_checkpoint_comparison",
            "completed_sessions": len(rows), "paired_tasks": len(pairs), "both_success_pairs": len(pairs),
            "both_success_costs": costs, "totals": signal["totals"],
            "memory_updates": {"main_tasks_changing_MEMORY": sum("memories/MEMORY.md" in r["output_content_changes"] for r in main),
                               "main_tasks_receiving_saved_MEMORY_body_in_first_input": sum("memories/MEMORY.md" in r["self_generated_markdown_whole_body_in_first_input"] for r in main)},
            "pairs": pairs,
            "scope": "One world and one evolving history; task pairs are not independent repeated experiments. Prior evaluator evidence is not automatically agent memory. Choices compatible with memory do not prove internal causal use."}


def figures(source, output, signal, projection):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = signal["rows"]
    tasks = [f"T{i}" for i in range(1, 21)]
    outputs = []
    def save(fig, name):
        for suffix in ("png", "svg", "pdf"):
            path = output/f"{name}.{suffix}"
            fig.savefig(path, dpi=180, facecolor="white")
            outputs.append(path.name)
        plt.close(fig)

    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none", "pdf.fonttype": 42}):
        fig, axes = plt.subplots(2, 1, figsize=(12, 7.3), sharex=True)
        for ax, field, label in zip(axes, ("distance", "operations"), ("Walked distance", "Game operations")):
            for condition, colour, marker, style, label_text in (
                ("retain", "#0072B2", "o", "-", "Retained native memory (T1 prefix)"),
                ("clear", "#D55E00", "s", "--", "Current-task baseline-memory probe")):
                data = [next((r for r in rows if r["task_id"] == task and
                              (r["condition"] == condition or condition == "retain" and r["condition"] == "prefix")), None)
                        for task in tasks]
                ax.plot(range(1, 21), [r[field] if r else float("nan") for r in data],
                        color=colour, marker=marker, linestyle=style, label=label_text)
            ax.set(ylabel=label, ylim=(0, max(r[field] for r in rows)*1.18))
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.2)
        axes[-1].set_xticks(range(1, 21), tasks)
        fig.legend(*axes[0].get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(.08, .94), ncol=2, frameon=False, fontsize=9)
        fig.suptitle("Hermes with compact feedback: all 20 commissions", x=.08, ha="left", y=.98, fontsize=15)
        fig.text(.08, .025, "All 39 sessions succeeded. T1 has no clear probe. One world, one evolving history; no uncertainty intervals.\nEvery task is shown; costs are unnormalized and unsmoothed.", fontsize=9)
        fig.subplots_adjust(left=.08, right=.98, top=.85, bottom=.15, hspace=.18)
        save(fig, "all-task-costs")

        design = {"public": projection["public_map"], "tasks": projection["tasks"]}
        fig, axes = plt.subplots(2, 2, figsize=(14, 13))
        selected = []
        for index, task in enumerate(("T3", "T17")):
            for column, condition in enumerate(("retain", "clear")):
                row = next(r for r in rows if r["task_id"] == task and r["condition"] == condition)
                graph = next(s["graph"] for s in projection["sessions"] if s["name"] == row["name"])
                path = [graph["edges"][0]["source"]] + [e["target"] for e in graph["edges"]]
                display = {**row, "path": path, "station_excursions": []}
                draw_graph(axes[index, column], design, graph, display,
                           f'{task} / {"Retained memory" if condition == "retain" else "Baseline-memory probe"}', focus_task=True)
                selected.append(row["name"])
        fig.suptitle("Hermes: fixed T3 and T17 executed trajectories", x=.05, ha="left", y=.98, fontsize=15)
        fig.text(.05, .935, "Cases fixed before the rerun. T17 retains a higher-cost memory branch; every movement and station operation is shown.", fontsize=10)
        fig.text(.05, .025, "Arrow numbers: actual movement order. Brown dashed: trip with unsupported processing. Grey: public roads.\nBoth conditions succeed in all tasks. One world and one history; compatible behavior is not proof of internal memory causality.", fontsize=9)
        fig.subplots_adjust(left=.05, right=.97, top=.89, bottom=.20, hspace=.64, wspace=.16)
        save(fig, "fixed-t3-t17-traces")

    manifest = {"kind": "descriptive_real_native_agent_pilot", "matplotlib_version": matplotlib.__version__,
                "png_dpi": 180, "selected_sessions": selected, "publisher_requirements": "not specified; provisional general research figures",
                "source_sha256": {name: sha256((source/name).read_bytes()).hexdigest() for name in ("signal.json.gz", "trace-projection.json.gz")},
                "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "transformations": ["all task costs, no smoothing", "T1 clear is missing, not zero", "all actual ordered graph edges and node operations", "unsupported-trip styling from recorded branch excursions"],
                "uncertainty": "one world and one sequential history; no population effect or uncertainty interval", "outputs": outputs}
    (output/"figure-provenance.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("docs/assets/hermes-linked-compact"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    signal, projection = [read(args.source/name) for name in ("signal.json.gz", "trace-projection.json.gz")]
    assert len(projection["sessions"]) == len(signal["rows"]) == 39
    for row in signal["rows"]:
        session = next(s for s in projection["sessions"] if s["name"] == row["name"])
        assert session["source_events_sha256"] == row["source_events_sha256"]
        assert session["graph"]["distance"] == row["distance"]
        assert len(session["graph"]["edges"]) == row["moves"]
        assert len(session["current_events"])-1 == row["operations"]
    summary = summarize(signal)
    (args.output/"comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    with (args.output/"all-sessions.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ("name", "task_id", "condition", "success", "distance", "moves", "operations", "query_count", "unsupported_processing_count", "llm_calls")
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(signal["rows"])
    figures(args.source, args.output, signal, projection)
    print(json.dumps({"sessions": 39, "memory_updates": summary["memory_updates"], "costs": summary["both_success_costs"], "real_model_calls": 0}))


if __name__ == "__main__":
    main()
