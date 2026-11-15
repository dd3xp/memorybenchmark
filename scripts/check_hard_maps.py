"""Strict, zero-model feasibility replay for all three authored Hard maps."""
import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_knowledge import supports
from memorybenchmark.prototypes.station_routes import feedback_policy, known_world_route
from memorybenchmark.prototypes.station_metrics import score_stream, summarize_stream
from scripts.build_hard_maps import REGIONS, diagnostics
from scripts.build_difficulty_maps import geometry
from scripts.check_station_capability import trace_graph

ROOT=Path(__file__).resolve().parents[1]


def check(theme, output):
    path=ROOT/'memorybenchmark/data'/(theme+'_hard48.json');design=load_design(path);world=map_world(design)
    assignment=design['private_worlds'][world];folder=output/theme;folder.mkdir(parents=True,exist_ok=False)
    (folder/'design.json').write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    distances=geometry(design);stats=diagnostics(design,design['private_station_capabilities'],distances)
    assert not stats['unused_strict_replicas'],stats
    assert .04<=stats['nearest_match_rate']<=.14,stats
    runs={}
    for condition in ('retain','clear'):
        game=StationGame(world,design);rows=[]
        for task_id,task in design['tasks'].items():
            offset=len(game.events)
            initial=StationSession(game,task_id,feedback_mode='compact').initial
            encoded=json.dumps(initial,ensure_ascii=False).lower()
            assert not any(s in encoded for s in ('private_world','provenance','https://','orcia','hampi','angkor','奥尔恰','亨比','吴哥'))
            feedback_policy(game,retain_history=condition=='retain')
            assert game.done and game.state.success,(theme,condition,task_id)
            current=game.events[offset:];replay=StationGame(world,design);replay.start_task(task_id)
            assert replay.events[0]['delivered']==current[0]['delivered']
            for event in current[1:]:
                assert event['kind']=='action'
                assert replay.step(event['action'])==event['delivered'],(theme,condition,task_id,event['event_id'])
            assert replay.state.success
            graph=trace_graph(game)
            assert graph['distance']==sum(e['weight'] for e in graph['edges'])
            assert len(graph['edges'])+len(graph['node_events'])==game.steps
            processes=[e for e in graph['node_events'] if e['action']['type']=='process']
            for event in processes:
                stage=task['stages'][event['state_before']['stage']];feedback=event['feedback']
                assert feedback['requirement']==stage['requirement']
                assert (feedback['result']=='processed')==supports(assignment[event['location']],stage['required_kind'],stage['requirement'])
                assert feedback['capability']==assignment[event['location']][stage['requirement']]
            graph_bytes=json.dumps(graph,ensure_ascii=False,separators=(',',':')).encode()
            graph_path=folder/f'{condition}-{task_id}.graph.json.gz';graph_path.write_bytes(gzip.compress(graph_bytes,mtime=0))
            raw=''.join(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n' for e in current).encode()
            events_path=folder/f'{condition}-{task_id}.events.jsonl.gz';events_path.write_bytes(gzip.compress(raw,mtime=0))
            rows.append({'task':task_id,'success':True,'distance':game.distance,'operations':game.steps,
                'processes':len(processes),'wrong_processes':sum(e['feedback']['result']=='unsupported' for e in processes),
                'physical_min_distance':known_world_route(design,task_id,assignment)['distance'],
                'graph_sha256':sha256(graph_bytes).hexdigest(),'event_sha256':sha256(raw).hexdigest(),
                'compressed_graph_sha256':sha256(graph_path.read_bytes()).hexdigest(),
                'compressed_events_sha256':sha256(events_path.read_bytes()).hexdigest()})
            # Full authoritative deliveries were written and strictly replayed
            # above. Evict only their repeated constant map from the in-memory
            # evaluator projection, keeping every feedback, action and state.
            for event in current:event['delivered']['observation'].pop('environment',None)
            if len(rows)%16==0:print(json.dumps({'map':theme,'condition':condition,'scripted_tasks':len(rows),'new_model_calls':0}),flush=True)
        scored=score_stream(design,game.events,condition=condition)
        summary=summarize_stream(scored)
        assert summary['all_tasks']['successes']==len(design['tasks'])
        (folder/f'{condition}-metrics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        runs[condition]={'rows':rows,'totals':{k:sum(r[k] for r in rows) for k in ('distance','operations','processes','wrong_processes')},
                         'max_operations':max(r['operations'] for r in rows)}
    assert runs['retain']['rows'][0]==runs['clear']['rows'][0]
    report={'kind':'scripted_real_engine_feasibility_not_native_agent_results','new_model_calls':0,
        'design_id':design['design_id'],'configuration_sha256':sha256(path.read_bytes()).hexdigest(),
        'nodes':len(design['public']['locations']),'roads':len(design['public']['edges']),
        'weighted_diameter':max(max(v.values()) for v in distances.values()),
        'reference_window':design['provenance']['reference_window'],'geometry':stats,'runs':runs,
        'scope':'Same public graph and fixed fixture in both policies. Retain uses actual earlier feedback; clear uses only current-task feedback. No model, native memory or historical-road reconstruction claim.'}
    (folder/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--map',choices=tuple(REGIONS),help='Validate a single individually authored landscape')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    themes=[args.map] if args.map else list(REGIONS)
    reports=[check(theme,args.output) for theme in themes]
    (args.output/'summary.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'maps':len(themes),'scripted_tasks':96*len(themes),'new_model_calls':0,'output':str(args.output)},ensure_ascii=False))


if __name__=='__main__':main()
