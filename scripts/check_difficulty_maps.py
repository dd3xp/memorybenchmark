"""Replay authored maps in the real engine with delivered-feedback policies."""
import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_routes import feedback_policy, known_world_route
from memorybenchmark.prototypes.station_knowledge import supports
from memorybenchmark.prototypes.station_session import StationSession
from scripts.build_difficulty_maps import fixture_diagnostics
from scripts.check_station_capability import trace_graph, render_svg
from scripts.check_easy_maps import topology
from scripts.field_geography import geography

ROOT=Path(__file__).resolve().parents[1]
FILES=['capulin_easy16','forest_geo_easy16','cascade_easy16','nessie_normal24','dingo_normal24','boar_normal24']


def check(key, output):
    path=ROOT/f'memorybenchmark/data/{key}.json';design=load_design(path);world=map_world(design)
    assignment=design['private_worlds'][world]
    points=[(n['x'],n['y']) for n in design['public']['locations'].values()]
    assert len(points)==len(set(points)),(key,'overlapping nodes')
    fixture={t:assignment[data['stations'][0]] for t,data in design['public']['station_types'].items()}
    stats=fixture_diagnostics(design,fixture)
    assert .075 <= stats['nearest_match_rate'] <= .175,(key,stats)
    assert not stats['unused_strict_replicas'],(key,stats)
    theme=dict(zip(FILES,('capulin','forest','cascade','nessie','dingo','boar')))[key]
    authored=geography(theme);geometric=authored['geometry_review']
    assert not geometric['unconnected_visual_crossings'],(key,geometric)
    assert not geometric['unapproved_barrier_crossings'],(key,geometric)
    assert geometric['minimum_point_separation']>=85,(key,geometric)
    assert geometric['minimum_station_separation']>=85,(key,geometric)
    for field in ('locations','edges','view_box'):assert authored[field]==design['public'][field]
    folder=output/key;folder.mkdir(parents=True,exist_ok=False)
    runs={}
    for condition in ('retain','clear'):
        game=StationGame(world,design);rows=[]
        for task_id,task in design['tasks'].items():
            offset=len(game.events)
            session=StationSession(game,task_id,feedback_mode='compact')
            encoded=json.dumps(session.initial,ensure_ascii=False).lower()
            assert not any(s in encoded for s in ('private_world','fixed_world','provenance','https://','张掖','迪恩','尼斯湖','kgari','k’gari'))
            feedback_policy(game,retain_history=condition=='retain')
            current=game.events[offset:];replay=StationGame(world,design);replay.start_task(task_id)
            assert replay.events[0]['delivered']==current[0]['delivered']
            for event in current[1:]:
                assert event['kind']=='action'
                assert replay.step(event['action'])==event['delivered'],(key,condition,task_id,event['event_id'])
            assert replay.state.success,(key,condition,task_id,'strict replay')
            graph=trace_graph(game)
            assert game.state.success,(key,condition,task_id)
            assert graph['distance']==sum(e['weight'] for e in graph['edges'])
            assert len(graph['edges'])+len(graph['node_events'])==game.steps
            assert sum(e['action']['type']=='survey' for e in graph['node_events'])==2
            assert graph['node_events'][-1]['action']['type']=='submit'
            processes=[e for e in graph['node_events'] if e['action']['type']=='process']
            assert all((e['feedback']['result']=='processed')==supports(assignment[e['location']],task['stages'][e['state_before']['stage']]['required_kind']) for e in processes)
            payload=json.dumps(graph,ensure_ascii=False,separators=(',',':')).encode()
            (folder/f'{condition}-{task_id}.json.gz').write_bytes(gzip.compress(payload,mtime=0))
            rows.append({'task':task_id,'success':True,'distance':game.distance,'operations':game.steps,
                'processes':len(processes),'wrong_processes':sum(e['feedback']['result']=='unsupported' for e in processes),
                'physical_distance':known_world_route(design,task_id,assignment)['distance'],
                'graph_sha256':sha256(payload).hexdigest()})
            if task_id in ('T2','T12'):
                (folder/f'{condition}-{task_id}.svg').write_text(render_svg(design,graph,f'{design["public"]["name"]} {task_id} / scripted {condition}'),encoding='utf-8')
        runs[condition]={'rows':rows,'totals':{k:sum(r[k] for r in rows) for k in ('distance','operations','processes','wrong_processes')},
            'max_operations':max(r['operations'] for r in rows)}
        # Retain the actual authoritative cumulative events privately and losslessly.
        raw=''.join(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n' for e in game.events).encode()
        (folder/f'{condition}-events.jsonl.gz').write_bytes(gzip.compress(raw,mtime=0))
    assert runs['retain']['rows'][0]==runs['clear']['rows'][0]
    a,b=(sum(r['distance'] for r in runs[c]['rows'][1:]) for c in ('retain','clear'))
    assert a<b,(key,a,b)
    report={'kind':'scripted_real_engine_validation_not_native_agent_results','new_model_calls':0,
        'design_id':design['design_id'],'configuration_sha256':sha256(path.read_bytes()).hexdigest(),
        'topology':authored['topology'],'geometry':stats,'geometric_review':geometric,'materials':design['material_selection'],
        'task_count':len(design['tasks']),'runs':runs,'followup_distance_reduction_percent':100*(1-a/b),
        'scope':'One deterministic feedback policy. Fixed world, actual delivered evidence only; no native memories or agent outcomes used in authoring. No guarantee of native-agent gains.'}
    (folder/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--map',choices=FILES,help='Validate one landscape before authoring the next')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for key in ([args.map] if args.map else FILES):
        report=check(key,args.output);reports.append(report)
        print(json.dumps({'map':key,'topology':report['topology'],'nearest_match_rate':report['geometry']['nearest_match_rate'],
            'distance_reduction_percent':report['followup_distance_reduction_percent'],
            'max_ops':{k:v['max_operations'] for k,v in report['runs'].items()}},ensure_ascii=False),flush=True)
    (args.output/'summary.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
