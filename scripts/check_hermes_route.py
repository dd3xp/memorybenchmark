"""Scripted upstream Hermes/MCP route contract, with no real model calls."""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memorybenchmark.ga_runtime import WSLJail, make_support
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import StationNativeSessions, movement_tool
from memorybenchmark.prototypes.station_routes import shortest_route
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN
from scripts.check_station_native_sessions import ScriptedResponses, response_observations, check_feedback_delivery


def check(root):
    root=Path(root)
    pilot=json.loads((root/'pilot.json').read_text(encoding='utf-8')) if (root/'pilot.json').exists() else None
    folders=[root/'sessions'/row['name'] for row in pilot['sessions'] if row['infrastructure_ok']] if pilot else [root]
    totals={'sessions':len(folders),'route_calls':0,'moves_in_routes':0,'multi_move_calls':0}
    for folder in folders:
        route_calls=moves=multi=0
        with (folder/'audit.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                prefix=line[:150]
                if '"kind": "tool"' not in prefix:continue
                item=json.loads(line)
                if item['name']=='mcp__cartography__game_action':
                    path=item.get('args',{}).get('path')
                    if path:
                        route_calls+=1;moves+=len(path);multi+=len(path)>1
        # Request lengths describe batching intent. Authoritative logs separately
        # count executed moves, errors and costs; a stopped route can be shorter.
        totals['route_calls']+=route_calls;totals['moves_in_routes']+=moves;totals['multi_move_calls']+=multi
    return totals


def main(args):
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    support=make_support(output/'support')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'memorybenchmark/hermes_worker.py',support/'hermes_worker.py')
    reference=args.reference_run.resolve()
    jail=WSLJail(args.distro,args.runtime,args.runtime_dependency)
    sessions=StationNativeSessions(reference/'source/hermes-agent',support,jail,agent='hermes',game_access='native',
        movement_mode='route',action_policy='batch',feedback_mode='compact',model_alias='fixture',max_turns=20,final_turns=3,seed=1)
    game=StationGame('omega_00_00',load_design(EASY20_REUSE_DESIGN))
    tools=[('game_action',{'action':'read'})];position='C'
    for destination,process in (('P',False),('A1',True),('R',False),('E1',True),('C',False)):
        path=shortest_route(game.design,position,destination)[0][1:]
        tools.append(('game_action',{'action':'move','path':path}));position=destination
        if process:tools.append(('game_action',{'action':'process'}))
    tools.append(('game_action',{'action':'submit'}))
    model=ScriptedResponses(tools,'hermes','native')
    result=sessions.run(game,'T1',reference/'baseline',output/'complete',model,condition='prefix')
    assert result['infrastructure_ok'],result.get('infrastructure_error')
    assert result['success'] and game.steps==29 and game.distance==30
    initial=result['initial_session']
    assert initial['initial_history_size']==initial['initial_backend_history_size']==0 and initial['working']=={}
    assert initial['native_mcp_game_tools']==['mcp__cartography__game_action']
    assert initial['native_mcp_sdk_version']=='2.3.0' and initial['movement_mode']=='route'
    assert '"path"' in json.dumps(model.requests[0],ensure_ascii=False)
    check_feedback_delivery(output/'complete',result,model,'compact')
    outputs=list(response_observations(model.requests))
    for event in game.events:
        if event['kind']!='action':continue
        delivered=event['delivered']['feedback']
        assert any(row['feedback']==delivered for row in outputs),delivered
    batching=check(output/'complete')
    assert batching['route_calls']==5 and batching['multi_move_calls']==5
    result={'passed':True,'real_model_calls':0,'kind':'scripted_real_upstream_hermes_route_mcp_contract',
            'game_operations':game.steps,'distance':game.distance,'batching':batching,'all_atomic_feedback_reached_model':True,
            'upstream_native_mcp_and_fresh_context_verified':True}
    (output/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime',required=True);parser.add_argument('--runtime-dependency',action='append',default=[])
    parser.add_argument('--distro',default='Ubuntu');main(parser.parse_args())
