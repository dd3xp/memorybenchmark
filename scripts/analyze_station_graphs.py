"""Compute trace diagnostics and plot source-labelled examples, without model calls.

Reference branches are policies with supplied information, never native agents.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from math import hypot
from pathlib import Path

from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_capability import StationGame
from scripts.check_station_capability import trace_graph


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def draw_graph(ax, design, graph, row, title):
    from matplotlib.patches import Circle, FancyArrowPatch
    locations = design["public"]["locations"]
    wrong_edges = {event for x in row["station_excursions"] if x["unsupported_attempts"]
                   for event in (x["enter"], x["exit"])}
    for a, b, _ in design["public"]["edges"]:
        p, q = locations[a], locations[b]
        ax.plot([p["x"], q["x"]], [p["y"], q["y"]], color="#c8cecf", linewidth=1, zorder=0)
    groups = defaultdict(list)
    for edge in graph["edges"]:
        groups[tuple(sorted((edge["source"], edge["target"])))].append(edge)
    for (a, b), edges in groups.items():
        p, q = locations[a], locations[b]
        length = hypot(q["x"] - p["x"], q["y"] - p["y"])
        nx, ny = -(q["y"] - p["y"]) / length, (q["x"] - p["x"]) / length
        for index, edge in enumerate(edges):
            p, q = locations[edge["source"]], locations[edge["target"]]
            shift = (index - (len(edges) - 1) / 2) * 13
            offset = nx * shift, ny * shift
            colour, style = ("#a33c21", "--") if edge["id"] in wrong_edges else ("#007299", "-")
            ax.add_patch(FancyArrowPatch((p["x"] + offset[0], p["y"] + offset[1]),
                (q["x"] + offset[0], q["y"] + offset[1]), arrowstyle="-|>", mutation_scale=12,
                shrinkA=15, shrinkB=15, linewidth=1.7, color=colour, linestyle=style, zorder=1))
            ax.text((p["x"] + q["x"]) / 2 + offset[0] * 1.5,
                    (p["y"] + q["y"]) / 2 + offset[1] * 1.5, str(edge["order"] + 1),
                    fontsize=8, color=colour, bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.5}, zorder=2)
    for node, data in locations.items():
        visited = node in graph["nodes"]
        ax.add_patch(Circle((data["x"], data["y"]), 17, facecolor="#e5f0ed" if visited else "white",
                           edgecolor="#374d56" if visited else "#a2adb0", linewidth=1.2, zorder=3))
        ax.text(data["x"], data["y"], node, ha="center", va="center", fontsize=10, zorder=4)
    labels = []
    for event in graph["node_events"]:
        verb, feedback = event["action"]["type"], event["feedback"]
        if verb == "process":
            text = "OK" if feedback["result"] == "processed" else "unsupported"
            labels.append(f'{event["location"]}: process {text}')
        elif verb == "inspect":
            labels.append(f'{event["location"]}: inspect {feedback["capability"]}')
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=9)
    ax.text(0, -0.025, "Path: " + " > ".join(row["path"]), transform=ax.transAxes, fontsize=9)
    ax.text(0, -0.10, "; ".join(labels), transform=ax.transAxes, fontsize=8.5)
    ax.text(0, -0.17, f'Success={row["success"]} | distance={row["distance"]} | moves={row["moves"]} | ops={row["operations"]}',
            transform=ax.transAxes, fontsize=9, color="#263f4a")
    bounds=design["public"].get("view_box")
    ax.set(xlim=(bounds[0],bounds[0]+bounds[2]) if bounds else (20,480),
           ylim=(bounds[1]+bounds[3],bounds[1]) if bounds else (390,25), aspect="equal")
    ax.axis("off")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.reference_run.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = read_json(root / "report.json")
    design = read_json(root / "design_snapshot.json")
    rows = []
    graphs = {}
    for case in report["cases"]:
        graph = read_json(root / case["graph"])
        events = [json.loads(line) for line in (root / case["log"]).read_text(encoding="utf-8").splitlines()]
        row = {**analyze_trace(design, events, graph["task_run_id"]),
               "name": case["name"], "condition": case["condition"], "section": case["section"],
               "private_world": case["private_world"], "source_log": case["log"], "source_graph": case["graph"]}
        assert row["distance"] == graph["distance"] == case["distance"]
        assert row["moves"] == len(graph["edges"])
        rows.append(row)
        graphs[case["name"]] = graph
    public = {"kind": "reference_policy_graph_diagnostics_NOT_native_agent_results",
              "source_report_sha256": sha256((root / "report.json").read_bytes()).hexdigest(),
              "source_design_sha256": report["design_sha256"],
              "analysis_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "measurement_sha256": sha256(Path(__file__).parents[1].joinpath("memorybenchmark/prototypes/station_analysis.py").read_bytes()).hexdigest(),
              "case_count": len(rows), "rows": rows}
    (output / "measurements.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none", "font.size": 10}):
        # Fixed examples: same task/world; T2 shows equal paths, T4 shows a wrong-station excursion.
        fig, axes = plt.subplots(2, 2, figsize=(11, 9.5))
        selected = []
        for index, task in enumerate(("T2", "T4")):
            for column, condition in enumerate(("history_reference", "no_history_reference")):
                name = f"stream-catalog-{2 if task == 'T2' else 4}-{task}-omega_11-{condition}"
                row = next(r for r in rows if r["name"] == name)
                selected.append(name)
                label = "History reference" if column == 0 else "No-history reference"
                draw_graph(axes[index, column], design, graphs[name], row, f"{task} / {label}")
        fig.subplots_adjust(left=0.05, right=0.97, top=0.89, bottom=0.18, hspace=0.60, wspace=0.16)
        fig.suptitle("Executed reference traces: same success, different behaviour", fontsize=16, x=0.05, ha="left", y=0.98)
        fig.text(0.05, 0.935, "Not native-agent results. One preselected world (omega_11); each arrow is one actual move.", fontsize=10)
        fig.text(0.05, 0.025, "Blue solid: other commutes. Brown dashed: trip containing unsupported processing. Numbers: movement order.\nGrey: public roads. A wrong first attempt can reveal useful information; it is not automatically a memory error.", fontsize=9)
        for suffix in ("svg", "png", "pdf"):
            fig.savefig(output / f"trace-comparison.{suffix}", dpi=180, facecolor="white")
        plt.close(fig)

        default = [r for r in rows if r["name"].startswith("stream-catalog-")]
        fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
        for condition, label, marker in (("history_reference", "History reference", "o"),
                                         ("no_history_reference", "No-history reference", "s")):
            means, errors = [], []
            for index in range(1, 9):
                data = [r for r in default if r["task_id"] == f"T{index}" and r["condition"] == condition]
                assert len(data) == 4
                means.append(sum(r["distance"] for r in data) / 4)
                errors.append(sum(r["unsupported_processing_count"] for r in data) / 4)
            axes[0].plot(range(1, 9), means, marker=marker, linestyle="-" if marker == "o" else "--", label=label)
            axes[1].plot(range(1, 9), errors, marker=marker, linestyle="-" if marker == "o" else "--", label=label)
        for ax in axes:
            ax.set_xticks(range(1, 9), [f"T{i}" for i in range(1, 9)])
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=0.2)
        axes[0].set(ylabel="Walked distance", ylim=(0, 12))
        axes[1].set(ylabel="Unsupported processing attempts", ylim=(0, 1))
        axes[0].legend(frameon=False, fontsize=9)
        fig.suptitle("Reference policies averaged over all four generated worlds", fontsize=13)
        fig.text(0.06, 0.01, "Exact finite-world means; no sampling intervals. All cases succeed. No-history points are local probes, not a separate full stream.", fontsize=8.5)
        fig.subplots_adjust(left=0.07, right=0.98, bottom=0.20, top=0.85, wspace=0.32)
        for suffix in ("svg", "png", "pdf"):
            fig.savefig(output / f"reference-summary.{suffix}", dpi=180, facecolor="white")
        plt.close(fig)
        witnesses = []
        fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
        for column, extra in enumerate((False, True)):
            game = StationGame("omega_00", design)
            game.start_task("T1")
            for node in ("J", "P", "J", "A"):
                game.step({"type": "move", "target": node})
            if extra:
                for _ in range(2):
                    game.step({"type": "inspect"})
            game.step({"type": "process"})
            for node in ("J", "C"):
                game.step({"type": "move", "target": node})
            game.step({"type": "submit"})
            row = analyze_trace(design, game.events, game.task_run_id)
            graph = trace_graph(game)
            name = "witness-extra-queries" if extra else "witness-direct-processing"
            (output / f"{name}.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in game.events), encoding="utf-8")
            (output / f"{name}.graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
            witnesses.append({"name": name, **row})
            draw_graph(axes[column], design, graph, row, "Two inspections, then process" if extra else "Process directly")
        assert witnesses[0]["path"] == witnesses[1]["path"]
        assert witnesses[0]["distance"] == witnesses[1]["distance"]
        (output / "representation-witnesses.json").write_text(json.dumps(witnesses, ensure_ascii=False, indent=2), encoding="utf-8")
        fig.suptitle("Identical commute graphs can hide different node operations", x=0.05, ha="left", fontsize=15)
        fig.text(0.05, 0.91, "Controlled rule-executed witnesses, not agent behaviour. Both succeed with distance 8 and 6 moves.", fontsize=10)
        fig.text(0.05, 0.025, "Only the event-attributed graph reveals the two extra queries (one repeats information already delivered in this session).", fontsize=9)
        fig.subplots_adjust(left=0.05, right=0.97, top=0.83, bottom=0.27, wspace=0.16)
        for suffix in ("svg", "png", "pdf"):
            fig.savefig(output / f"node-events-matter.{suffix}", dpi=180, facecolor="white")
        plt.close(fig)
    (output / "figure-manifest.json").write_text(json.dumps({
        "source": str(root), "kind": public["kind"], "selected_cases": selected,
        "selection_rule": "Fixed catalog T2 and T4 in world omega_11, both information conditions; all-world aggregate shown separately",
        "transformations": ["one node per visited location", "one arrow per movement in original order", "station operations retained as text", "arithmetic equal-world means"],
        "uncertainty": "finite family enumeration, not statistical samples or native-agent replicates",
        "matplotlib_version": matplotlib.__version__,
        "source_measurements_sha256": sha256((output / "measurements.json").read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"cases": len(rows), "output": str(output), "kind": public["kind"]}))


if __name__ == "__main__":
    main()
