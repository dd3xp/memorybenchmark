"""Audit completed native GA station sessions and plot all-task measurements."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.ga_runtime import memory_manifest
from scripts.analyze_station_graphs import draw_graph


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    root,output=args.run.resolve(),args.output.resolve()
    pilot=read(root/"pilot.json")
    if pilot["status"] != "completed":
        raise ValueError("Only completed pilots are reported as completed experiments")
    output.mkdir(parents=True,exist_ok=False)
    design=read(root/"design.json")
    baseline=memory_manifest(root/"baseline")
    rows=[]
    graphs={}
    for session in pilot["sessions"]:
        folder=root/"sessions"/session["name"]
        summary=read(folder/"summary.json")
        events=[json.loads(line) for line in (folder/"events.jsonl").read_text(encoding="utf-8").splitlines()]
        graph=read(folder/"graph.json")
        messages=[json.loads(line) for line in (folder/"audit.jsonl").read_text(encoding="utf-8").splitlines()]
        terminal=next(e for e in reversed(events) if e["task_run_id"]==graph["task_run_id"])
        final_observation=terminal["delivered"]["observation"]
        before_first_station=[]
        memory_reads_before_end=[]
        for message in messages:
            if message.get("kind")=="request" and message.get("method")=="task_end":
                break
            if message.get("kind")=="tool" and message.get("name")=="file_read":
                memory_reads_before_end.append(message.get("args",{}).get("path"))
        station_ids={n for n,d in design["public"]["locations"].items() if d["kind"]=="station"}
        for message in messages:
            if message.get("kind")=="request" and message.get("method")=="task_end":
                break
            if message.get("kind")=="request" and message.get("method")=="game":
                action=message.get("params",{}).get("action",{})
                if action.get("type")=="move" and action.get("target") in station_ids:
                    break
            if message.get("kind")=="tool" and message.get("name")=="file_read":
                before_first_station.append(message.get("args",{}).get("path"))
        row={**analyze_trace(design,events,graph["task_run_id"],infrastructure_ok=summary["infrastructure_ok"]),
             "name":session["name"],"condition":session["condition"],"llm_calls":summary["llm_calls"],
             "main_calls":summary["main_calls"],"final_calls":summary["final_calls"],
             "execution_protocol":summary["initial_session"].get("execution_protocol","native-return-terminal-legacy"),
             "continuation_count":len(summary.get("continuations",[])),
             "memory_content_changed":summary.get("content_changed",[]),
             "tool_counts":dict(Counter(m["name"] for m in messages if m.get("kind")=="tool")),
             "input_memory_differs_from_baseline":summary["input_memory"] != baseline,
             "memory_before_sha256":sha256((folder/"memory-before.json").read_bytes()).hexdigest(),
             "source_events_sha256":sha256((folder/"events.jsonl").read_bytes()).hexdigest(),
             "end_location":final_observation["location"],"end_raw":final_observation["raw"],
             "end_processed":final_observation["processed"],
             "termination_reason":terminal["delivered"]["feedback"].get("reason",terminal["delivered"]["feedback"].get("termination",terminal["delivered"]["feedback"]["kind"])),
             "file_reads_before_first_station_move":before_first_station,
             "file_reads_before_task_end":memory_reads_before_end}
        assert row["distance"]==summary["distance"]==graph["distance"]
        assert row["success"]==summary["success"]
        initial=summary["initial_session"]
        assert initial["initial_history_size"]==initial["initial_backend_history_size"]==0
        assert initial["working"]=={}
        if row["execution_protocol"]=="environment-gated-1":
            assert row["termination_reason"]!="agent_stopped"
            assert summary["worker_result"]["phase_calls"]=={"main":summary["main_calls"],"final":summary["final_calls"]}
            if row["termination_reason"]=="model_budget":
                assert row["main_calls"]==pilot["max_turns"]
        assert all(v for k,v in initial["isolation"].items() if k!="pid")
        rows.append(row)
        graphs[row["name"]]=graph
    pair_inputs=[]
    for task in pilot["tasks"][1:]:
        pair=[]
        for condition in ("retain","clear"):
            row=next(r for r in rows if r["task_id"]==task and r["condition"]==condition)
            payload=read(root/"sessions"/row["name"]/"model"/"001-request.json")
            pair.append({k:v for k,v in payload.items() if k in ("input","tools","reasoning")})
        pair_inputs.append({"task":task,"first_forwarded_input_equal":pair[0]==pair[1]})
    artifact={"kind":"native_ga_station_single_world_pilot_not_statistical_effect_estimate",
              "world":pilot["world"],"model_alias":pilot["model_alias"],"source_pilot_sha256":sha256((root/"pilot.json").read_bytes()).hexdigest(),
              "analysis_sha256":sha256(Path(__file__).read_bytes()).hexdigest(),"rows":rows,"paired_first_inputs":pair_inputs,
              "comparison":pilot["comparison"],"limitations":["one sampled world and one native history",
                 "each clear run is a current-task probe, not an independent full stream",
                 "model alias is not independently verified model identity","path matching is not retrieval proof"]}
    (output/"measurements.json").write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Native GA station pilot", "", f'Model alias: {pilot["model_alias"]}. One sampled world, 15 fresh sessions. No statistical effect estimate.',"",
           "|Task|Condition|Success|Distance|Moves|Ops|Queries|Unsupported|Relevant prior exposure|LLM calls|Continuations|Memory changes|",
           "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|"]
    for row in rows:
        lines.append(f'|{row["task_id"]}|{row["condition"]}|{row["success"]}|{row["distance"]}|{row["moves"]}|{row["operations"]}|{row["query_count"]}|{row["unsupported_processing_count"]}|{row["prior_relevant_exposure"]}|{row["llm_calls"]}|{row["continuation_count"]}|{", ".join(row["memory_content_changed"])}|')
    (output/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family":"DejaVu Sans","svg.fonttype":"none","font.size":10}):
        fig,axes=plt.subplots(2,2,figsize=(11,10))
        selected=[]
        for index,task in enumerate(("T2","T4")):
            for column,condition in enumerate(("retain","clear")):
                row=next(r for r in rows if r["task_id"]==task and r["condition"]==condition)
                selected.append(row["name"])
                draw_graph(axes[index,column],design,graphs[row["name"]],row,
                           f'{task} / {"Retained native memory" if condition=="retain" else "Baseline native memory"}')
        fig.subplots_adjust(left=0.05,right=0.97,top=0.89,bottom=0.20,hspace=0.64,wspace=0.16)
        fig.suptitle("Native GA: executed cross-session trajectories",fontsize=16,x=0.05,ha="left",y=0.98)
        fig.text(0.05,0.935,"One world, one pilot. Fixed T2 and T4 examples; all 15 sessions are reported separately.",fontsize=10)
        fig.text(0.05,0.025,"Arrows are actual moves; numbers preserve movement order. Node operations are listed beneath each graph.\nIncomplete paths end at task termination. These observations alone do not establish a memory effect.",fontsize=9)
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/f"native-trace-comparison.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
        fig,ax=plt.subplots(figsize=(10.5,4.4))
        x=list(range(1,9))
        retained=[next(r for r in rows if r["task_id"]==f"T{i}" and r["condition"] in ("prefix","retain")) for i in x]
        cleared=[next((r for r in rows if r["task_id"]==f"T{i}" and r["condition"]=="clear"),None) for i in x]
        ax.plot(x,[r["distance"] for r in retained],marker="o",label="Retained history branch (T1 prefix)")
        ax.plot(x,[r["distance"] if r else float('nan') for r in cleared],marker="s",linestyle="--",label="Current-task baseline-memory probe")
        failed=[(i,row["distance"]) for branch in (retained,cleared) for i,row in zip(x,branch) if row and not row["success"]]
        ax.scatter([p[0] for p in failed],[p[1] for p in failed],marker="x",s=90,c="black",linewidths=1.5,zorder=5,label="Task ended before submission")
        ax.set_xticks(x,[f"T{i}" for i in x]);ax.set(ylabel="Actual walked distance",ylim=(0,max(r["distance"] for r in rows)+4))
        ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=0.2)
        ax.legend(frameon=False,fontsize=9,loc="upper center")
        fig.suptitle("Native GA pilot: all eight commissions",fontsize=14)
        fig.text(0.08,0.025,"One observation per condition/task; no uncertainty intervals. Early failure can have low distance. No baseline probe exists for T1.",fontsize=8.5)
        fig.subplots_adjust(left=0.09,right=0.98,bottom=0.19,top=0.88)
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/f"native-all-tasks.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
    (output/"figure-manifest.json").write_text(json.dumps({"kind":artifact["kind"],"source":str(root),"selected_cases":selected,
        "selection_rule":"fixed T2/T4 paired examples plus all-task distance plot","transforms":["ordered multigraph projection","actual node event labels","no smoothing or aggregation"],
        "matplotlib_version":matplotlib.__version__},indent=2),encoding="utf-8")
    print(json.dumps({"cases":len(rows),"successes":sum(r["success"] for r in rows),"calls":sum(r["llm_calls"] for r in rows),"output":str(output)}))


if __name__=="__main__":
    main()
