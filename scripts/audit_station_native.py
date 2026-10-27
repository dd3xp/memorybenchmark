"""Replay native pilot evidence and verify memory/source chains without a model."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from memorybenchmark.ga_runtime import memory_manifest
from memorybenchmark.prototypes.station_capability import StationGame
from scripts.check_station_capability import trace_graph


def read(path):
    return path.read_text(encoding="utf-8-sig")


def audit(root, *, allow_partial=False, source_commit=None, source_newlines="raw", native_archive=None):
    root=Path(root)
    pilot=json.loads(read(root/"pilot.json"));design=json.loads(read(root/"design.json"))
    if not allow_partial and pilot["status"]!="completed":
        raise ValueError("Pilot is incomplete; partial auditing must be explicit")
    archive_verified=None
    if native_archive:
        archive_verified=sha256(Path(native_archive).read_bytes()).hexdigest()==pilot["archive_sha256"]
        assert archive_verified,"Native archive differs from declared source"
    game=StationGame(pilot["world"],design)
    baseline=memory_manifest(root/"baseline");main_memory=baseline
    checked_events=checked_current_events=0;rows=[];session_ids=[]
    for recorded in pilot["sessions"]:
        folder=root/"sessions"/recorded["name"]
        summary=json.loads(read(folder/"summary.json"))
        if not summary["infrastructure_ok"]:
            continue
        if recorded["condition"]!="clear":
            checkpoint=deepcopy(game)
        before=baseline if recorded["condition"]=="clear" else main_memory
        assert json.loads(read(folder/"memory-before.json"))==before
        assert summary["input_memory"]==before
        assert memory_manifest(folder/"memory-after")==summary["output_memory"]
        assert json.loads(read(folder/"prior-events.json"))==checkpoint.events
        current=deepcopy(checkpoint);current.start_task(recorded["task_id"])
        events=[json.loads(line) for line in read(folder/"events.jsonl").splitlines()]
        current_events=[e for e in events if e["task_run_id"]==current.task_run_id]
        assert current_events[0]==current.events[-1]
        for event in current_events[1:]:
            if event["kind"]=="action":current.step(event["action"])
            elif event["kind"]=="runner_terminated":current.finish_incomplete(event["delivered"]["feedback"]["reason"])
            else:raise AssertionError("Unexpected authoritative event kind")
            assert current.events[-1]==event
        assert current.done and current.events==events
        assert trace_graph(current)==json.loads(read(folder/"graph.json"))
        assert (current.state.success,current.steps,current.distance)==(summary["success"],summary["game_actions"],summary["distance"])
        requests=list((folder/"model").glob("*-request.json"));responses=list((folder/"model").glob("*-response.json"))
        assert len(requests)==len(responses)==summary["llm_calls"]
        assert summary["main_calls"]<=pilot["max_turns"] and summary["final_calls"]<=pilot["final_turns"]
        initial=summary["initial_session"]
        assert initial["initial_history_size"]==initial["initial_backend_history_size"]==0
        assert initial["working"]=={} and all(v for k,v in initial["isolation"].items() if k!="pid")
        session_ids.append(summary["session_id"])
        checked_events+=len(events);checked_current_events+=len(current_events)
        rows.append({"name":recorded["name"],"success":current.state.success,"events":len(current_events),"calls":summary["llm_calls"]})
        if recorded["condition"]!="clear":game=current;main_memory=summary["output_memory"]
    assert len(set(session_ids))==len(session_ids)
    if pilot["status"]=="completed":
        assert len(rows)==1+2*(len(pilot["tasks"])-1)
    verified_sources={}
    if source_commit:
        for name,digest in pilot["implementation_sha256"].items():
            normalized=name.replace("\\","/")
            candidates=[marker+normalized.rsplit('/'+marker,1)[1] for marker in ('memorybenchmark/','design/','scripts/') if '/'+marker in normalized]
            if len(candidates)!=1:raise ValueError("Ambiguous frozen source path")
            relative=candidates[0]
            content=subprocess.run(['git','show',f'{source_commit}:{relative}'],check=True,capture_output=True).stdout
            if source_newlines=="crlf":content=content.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
            assert sha256(content).hexdigest()==digest,(relative,"frozen source differs from declared commit")
            frozen=root/"provenance"/"frozen-source"/relative
            if frozen.exists():assert sha256(frozen.read_bytes()).hexdigest()==digest
            verified_sources[relative]=digest
    return {"kind":"native_station_replay_and_memory_chain_audit","pilot_completed":pilot["status"]=="completed",
            "sessions":len(rows),"cumulative_event_records_replayed":checked_events,
            "current_session_event_records_replayed":checked_current_events,"canonical_tasks":game._runs,
            "memory_chains_verified":True,"fresh_sessions_and_isolation_verified":True,
            "source_commit":source_commit,"source_newlines":source_newlines,"source_files_verified":verified_sources,
            "native_archive_verified":archive_verified,"rows":rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-partial',action='store_true');parser.add_argument('--source-commit')
    parser.add_argument('--source-newlines',choices=('raw','crlf'),default='raw',help='explicit Git checkout newline conversion for frozen Windows files')
    parser.add_argument('--native-archive',type=Path)
    args=parser.parse_args();result=audit(args.run,allow_partial=args.allow_partial,source_commit=args.source_commit,source_newlines=args.source_newlines,native_archive=args.native_archive)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','source_files_verified')}))


if __name__=='__main__':main()
