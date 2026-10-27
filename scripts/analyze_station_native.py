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
    parser.add_argument("--skip-exact-references", action="store_true", help="report trace evidence without expensive unknown-world policy search")
    parser.add_argument("--trace-tasks", nargs=2, default=("T2","T4"), help="two paired trace examples, selected explicitly")
    args=parser.parse_args()
    root,output=args.run.resolve(),args.output.resolve()
    pilot=read(root/"pilot.json")
    if pilot["status"] != "completed":
        raise ValueError("Only completed pilots are reported as completed experiments")
    output.mkdir(parents=True,exist_ok=False)
    design=read(root/"design.json")
    baseline=memory_manifest(root/"baseline")
    baseline_global=(root/"baseline"/"global_mem_insight.txt").read_text(encoding="utf-8")
    main_memory=root/"baseline"
    rows=[]
    graphs={}
    projections=[]
    for session in pilot["sessions"]:
        folder=root/"sessions"/session["name"]
        summary=read(folder/"summary.json")
        input_memory=root/"baseline" if session["condition"]=="clear" else main_memory
        global_memory=(input_memory/"global_mem_insight.txt").read_text(encoding="utf-8")
        first_request=read(folder/"model"/"001-request.json")
        global_in_input=json.dumps(global_memory,ensure_ascii=False)[1:-1] in json.dumps(first_request,ensure_ascii=False)
        events=[json.loads(line) for line in (folder/"events.jsonl").read_text(encoding="utf-8").splitlines()]
        graph=read(folder/"graph.json")
        messages=[json.loads(line) for line in (folder/"audit.jsonl").read_text(encoding="utf-8").splitlines()]
        terminal=next(e for e in reversed(events) if e["task_run_id"]==graph["task_run_id"])
        final_observation=terminal["delivered"]["observation"]
        before_first_station=[]
        tools_before_first_station=[]
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
            if message.get("kind")=="tool":
                tools_before_first_station.append(message.get("name"))
        row={**analyze_trace(design,events,graph["task_run_id"],infrastructure_ok=summary["infrastructure_ok"],exact_references=not args.skip_exact_references),
             "name":session["name"],"condition":session["condition"],"llm_calls":summary["llm_calls"],
             "main_calls":summary["main_calls"],"final_calls":summary["final_calls"],
             "execution_protocol":summary["initial_session"].get("execution_protocol","native-return-terminal-legacy"),
             "continuation_count":len(summary.get("continuations",[])),
             "finalization_native_result":summary.get("worker_result",{}).get("finalization_result",{}).get("result"),
             "finalization_calls_at_limit":summary["final_calls"]==pilot["final_turns"],
             "native_global_memory_changed_from_baseline":global_memory!=baseline_global,
             "native_global_memory_verbatim_in_first_input":global_in_input,
             "self_generated_global_memory_in_first_input":global_memory!=baseline_global and global_in_input,
             "input_global_memory_sha256":sha256(global_memory.encode("utf-8")).hexdigest(),
             "memory_content_changed":summary.get("content_changed",[]),
             "tool_counts":dict(Counter(m["name"] for m in messages if m.get("kind")=="tool")),
             "input_memory_differs_from_baseline":summary["input_memory"] != baseline,
             "memory_before_sha256":sha256((folder/"memory-before.json").read_bytes()).hexdigest(),
             "source_events_sha256":sha256((folder/"events.jsonl").read_bytes()).hexdigest(),
             "end_location":final_observation["location"],"end_raw":final_observation["raw"],
             "end_processed":final_observation["processed"],
             "termination_reason":terminal["delivered"]["feedback"].get("reason",terminal["delivered"]["feedback"].get("termination",terminal["delivered"]["feedback"]["kind"])),
             "file_reads_before_first_station_move":before_first_station,
             "tool_names_before_first_station_move":tools_before_first_station,
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
        start=next(e for e in events if e["task_run_id"]==graph["task_run_id"] and e["kind"]=="task_started")
        event_fields=("event_id","task_id","task_run_id","world_version","kind","position","action","from","to",
                      "moved","movement_cost","effort_cost","time","time_before","time_after","state_before","state_after","evidence_delivered")
        projections.append({"name":row["name"],"task_id":row["task_id"],"condition":row["condition"],
            "source_events_sha256":row["source_events_sha256"],"graph":graph,
            "prior_evidence":[{"event_id":e["event_id"],"task_id":e["task_id"],"task_run_id":e["task_run_id"],
                               "feedback":e["delivered"]["feedback"]} for e in events if e["event_id"]<start["event_id"]
                              and e.get("delivered",{}).get("feedback",{}).get("kind")=="station_information"],
            "current_events":[{**{k:e[k] for k in event_fields if k in e},"feedback":e["delivered"]["feedback"],
                               "observation":{k:e["delivered"]["observation"][k] for k in
                                    ("location","raw","processed","steps","distance","time","clock","done","success") if k in e["delivered"]["observation"]}}
                              for e in events if e["task_run_id"]==graph["task_run_id"]]})
        if session["condition"]!="clear":
            main_memory=folder/"memory-after"
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
              "analysis_sources_sha256":{name:sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest() for name in
                  ("scripts/analyze_station_native.py","scripts/analyze_station_graphs.py",
                   "memorybenchmark/prototypes/station_analysis.py","memorybenchmark/prototypes/station_capability.py",
                   "memorybenchmark/ga_runtime.py")},
              "execution_protocols":sorted({r["execution_protocol"] for r in rows}),
              "infrastructure_attempts":[{"name":s["name"],"llm_call_attempts":s["llm_calls"],
                  "error":s["infrastructure_error"],"excluded_from_valid_rows":True}
                  for s in pilot.get("attempt_history",[])],
              "comparison":pilot["comparison"],"exact_references_computed":not args.skip_exact_references,
              "limitations":["one sampled world and one native history",
                 "each clear run is a current-task probe, not an independent full stream",
                 "model alias is not independently verified model identity","path matching is not retrieval proof"]}
    (output/"measurements.json").write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"trace-projection.json").write_text(json.dumps({"kind":"public_game_trace_projection_not_model_transcript",
        "design_id":design["design_id"],"public_map":design["public"],"tasks":design["tasks"],
        "source_pilot_sha256":artifact["source_pilot_sha256"],"prior_evidence_scope":"evaluator canonical actual history; not automatically supplied to the agent",
        "sessions":projections},ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Native GA station pilot", "", f'Model alias: {pilot["model_alias"]}. One sampled world, {len(rows)} fresh sessions. No statistical effect estimate.',"",
           "|Task|Condition|Success|Distance|Moves|Ops|Queries|Unsupported|Relevant prior exposure|LLM calls|Continuations|Memory changes|",
           "|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|"]
    for row in rows:
        lines.append(f'|{row["task_id"]}|{row["condition"]}|{row["success"]}|{row["distance"]}|{row["moves"]}|{row["operations"]}|{row["query_count"]}|{row["unsupported_processing_count"]}|{row["prior_relevant_exposure"]}|{row["llm_calls"]}|{row["continuation_count"]}|{", ".join(row["memory_content_changed"])}|')
    (output/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family":"DejaVu Sans","svg.fonttype":"none","font.size":10}):
        fig,axes=plt.subplots(2,2,figsize=(14,13) if design["public"].get("view_box") else (11,10))
        selected=[]
        for index,task in enumerate(args.trace_tasks):
            for column,condition in enumerate(("retain","clear")):
                row=next(r for r in rows if r["task_id"]==task and r["condition"]==condition)
                selected.append(row["name"])
                draw_graph(axes[index,column],design,graphs[row["name"]],row,
                           f'{task} / {"Retained native memory" if condition=="retain" else "Baseline native memory"}')
        fig.subplots_adjust(left=0.05,right=0.97,top=0.89,bottom=0.20,hspace=0.64,wspace=0.16)
        fig.suptitle("Native GA: executed cross-session trajectories",fontsize=16,x=0.05,ha="left",y=0.98)
        fig.text(0.05,0.935,f'One world, one pilot. Selected {" and ".join(args.trace_tasks)} examples; all {len(rows)} sessions are reported separately.',fontsize=10)
        fig.text(0.05,0.025,"Arrows are actual moves; numbers show movement order. Node operations are listed beneath each graph.\nDashed red: station trip containing unsupported processing. Blue: other moves.\nIncomplete paths end at task termination; input and retrieval audits accompany the graphs.",fontsize=9)
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/f"native-trace-comparison.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
        tasks=pilot["tasks"]
        fig,ax=plt.subplots(figsize=(max(10.5,len(tasks)*.56),4.4))
        x=list(range(1,len(tasks)+1))
        retained=[next(r for r in rows if r["task_id"]==task and r["condition"] in ("prefix","retain")) for task in tasks]
        cleared=[next((r for r in rows if r["task_id"]==task and r["condition"]=="clear"),None) for task in tasks]
        ax.plot(x,[r["distance"] for r in retained],marker="o",label="Retained history branch (T1 prefix)")
        ax.plot(x,[r["distance"] if r else float('nan') for r in cleared],marker="s",linestyle="--",label="Current-task baseline-memory probe")
        failed=[(i,row["distance"]) for branch in (retained,cleared) for i,row in zip(x,branch) if row and not row["success"]]
        if failed:
            ax.scatter([p[0] for p in failed],[p[1] for p in failed],marker="x",s=90,c="black",linewidths=1.5,zorder=5,label="Task ended before submission")
        ax.set_xticks(x,tasks);ax.set(ylabel="Actual walked distance",ylim=(0,max(r["distance"] for r in rows)+4))
        ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=0.2)
        ax.legend(frameon=False,fontsize=9,loc="upper center")
        fig.suptitle(f"Native GA pilot: all {len(tasks)} commissions",fontsize=14)
        status_note="Early failure can have low distance." if failed else f"All {len(rows)} sessions submitted successfully."
        fig.text(0.08,0.025,f"One observation per condition/task; no uncertainty intervals. {status_note} No baseline probe exists for T1.",fontsize=8.5)
        fig.subplots_adjust(left=0.09,right=0.98,bottom=0.19,top=0.88)
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/f"native-all-tasks.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
        fig,axes=plt.subplots(3,1,figsize=(max(10.5,len(tasks)*.56),7.4),sharex=True)
        for ax,(field,label) in zip(axes,(("query_count","Paid queries"),
                                         ("historically_repeated_queries","Repeated evidence\nqueries"),
                                         ("unsupported_processing_count","Unsupported\nprocessing"))):
            ax.plot(x,[r[field] for r in retained],marker="o",color="#0072B2",label="Retained native memory")
            ax.plot(x,[r[field] if r else float('nan') for r in cleared],marker="s",linestyle="--",color="#D55E00",label="Current-task baseline-memory probe")
            failed_points=[(i,row[field]) for branch in (retained,cleared) for i,row in zip(x,branch) if row and not row["success"]]
            if failed_points:
                ax.scatter([p[0] for p in failed_points],[p[1] for p in failed_points],marker="x",c="black",s=70,linewidths=1.4,zorder=5)
            ax.set_ylabel(label,fontsize=9);ax.set_ylim(-.15,max(1,max(r[field] for r in rows))+.5)
            ax.spines[["top","right"]].set_visible(False);ax.grid(axis="y",alpha=.2)
            ax.yaxis.get_major_locator().set_params(integer=True)
        axes[-1].set_xticks(x,tasks)
        handles,labels=axes[0].get_legend_handles_labels()
        fig.legend(handles,labels,frameon=False,fontsize=9,loc="upper left",bbox_to_anchor=(.10,.955),ncol=2)
        fig.suptitle("Native GA: information-seeking and processing behavior",fontsize=14)
        fig.text(.09,.025,"Repetition uses actual canonical delivered evidence, including facts unavailable in a clear probe.\nOne observation per condition/task; black crosses mark incomplete tasks; T1 has no baseline probe.",fontsize=8.5)
        fig.subplots_adjust(left=.10,right=.98,bottom=.13,top=.91,hspace=.27)
        for suffix in ("png","svg","pdf"):
            fig.savefig(output/f"native-query-behavior.{suffix}",dpi=180,facecolor="white")
        plt.close(fig)
    (output/"figure-manifest.json").write_text(json.dumps({"kind":artifact["kind"],"source":str(root),"selected_cases":selected,
        "selection_rule":f'explicit {"/".join(args.trace_tasks)} paired examples plus all-task distance plot',"transforms":["ordered multigraph projection","actual node event labels","no smoothing or aggregation"],
        "matplotlib_version":matplotlib.__version__},indent=2),encoding="utf-8")
    print(json.dumps({"cases":len(rows),"successes":sum(r["success"] for r in rows),"calls":sum(r["llm_calls"] for r in rows),"output":str(output)}))


if __name__=="__main__":
    main()
