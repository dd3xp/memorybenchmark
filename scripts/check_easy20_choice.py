"""Validate proximity controls and replay feedback policies, without a model."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from itertools import permutations
import argparse
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, capability_groups, compatible_worlds, load_design
from memorybenchmark.prototypes.station_choice import choice_context
from memorybenchmark.prototypes.station_routes import feedback_policy, schedule, station_options, task_group, walk
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN
from scripts.check_station_capability import export_case


def check(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    design=load_design(EASY20_CHOICE_DESIGN);groups=capability_groups(design)
    distribution=[];replays=[];worst=0;order_cases=0
    for tid,task in design['tasks'].items():
        options=station_options(design,tid)
        nearest=min(options,key=lambda r:r['distance_from_target'])['station']
        correct=sum(world[nearest]==task['required_kind'] for world in design['private_worlds'].values())
        assert correct==len(design['private_worlds'])//2
        assert len({r['completion_distance'] for r in options})==4
        distribution.append({'task':tid,'nearest_station':nearest,'nearest_matches_worlds':correct,
            'nearest_misses_worlds':len(design['private_worlds'])-correct,'options':options})
    # Other groups cannot affect a task's capability or geography: replay all six
    # local allocations for each group's five tasks, holding the others fixed.
    for group_index,(group_name,group) in enumerate(groups.items()):
        tasks=[t for t in design['tasks'] if task_group(design,t)==group_name]
        for index in range(6):
            digits=['0']*4;digits[group_index]=str(index);world='omega_'+''.join(digits)
            for retain in (True,False):
                game=StationGame(world,design)
                for tid in tasks:
                    game.start_task(tid);feedback_policy(game,retain_history=retain)
                    assert game.state.success and game.steps<=24
                    replays.append({'world':world,'task':tid,'retained_feedback_policy':retain,
                        'distance':game.distance,'operations':game.steps})
            # Each of the two target positions is tested with every ordering of
            # the four candidates. Complementary allocations cover both kinds.
            for tid in tasks[:2]:
                assert design['tasks'][tasks[0]]['target']!=design['tasks'][tasks[1]]['target']
                for order in permutations(group['stations']):
                    game=StationGame(world,design);game.start_task(tid);walk(game,game.task['target'])
                    for station in order:
                        walk(game,station)
                        feedback=game.step({'type':'inspect'})['feedback']
                        if feedback['capability']==game.task['required_kind']:
                            game.step({'type':'process'});break
                    walk(game,game.task['submit_at']);game.step({'type':'submit'})
                    assert game.state.success and game.steps<=24
                    worst=max(worst,game.steps);order_cases+=1
    # Actual delivered source feedback establishes two matches by exclusion.
    source=StationGame('omega_5000',design);source.start_task('T1')
    for station in ('A','B'):
        walk(source,station);source.step({'type':'inspect'})
    source.step({'type':'abandon'})
    examples=[]
    for name,retain in [('history_excludes_nearest',True),('current_task_nearest_first',False)]:
        game=deepcopy(source);prior=deepcopy(game.events);game.start_task('T19')
        feedback_policy(game,retain_history=retain)
        row=export_case(output,name,game)
        first=next(e['to'] for e in game.events if e['task_run_id']==game.task_run_id and e['kind']=='action' and e['to'] in groups['AB']['stations'])
        row['choice_context']=choice_context(design,'T19',prior,first)
        examples.append(row)
    assert examples[0]['distance']<examples[1]['distance']
    # Knowing A alone does not justify penalizing a failure to discover N2.
    partial=StationGame('omega_2000',design);partial.start_task('T1');walk(partial,'A')
    partial.step({'type':'inspect'});partial.step({'type':'abandon'})
    unresolved=choice_context(design,'T8',partial.events,'A')
    assert unresolved['conditional_distance_reference'] is None
    # Same public observation, different nearest-station capability.
    initial=[StationGame(w,design).start_task('T1') for w in ('omega_0000','omega_5000')]
    assert initial[0]==initial[1]
    report={'kind':'scripted_route_choice_calibration_not_native_memory_score','design_id':design['design_id'],
        'design_sha256':sha256(EASY20_CHOICE_DESIGN.read_bytes()).hexdigest(),
        'world_count':len(design['private_worlds']),'nodes':len(design['public']['locations']),
        'edges':len(design['public']['edges']),'cycle_rank':len(design['public']['edges'])-len(design['public']['locations'])+1,
        'task_count':len(design['tasks']),'world_task_choices_checked':len(distribution)*len(design['private_worlds']),
        'proximity_distribution':distribution,'feedback_policy_replays':replays,
        'candidate_order_replays':order_cases,'max_candidate_order_operations':worst,
        'witnesses':examples,'partial_history_witness':unresolved,'schedule':schedule(design),
        'limitations':['scripted calibration, no model or agent-generated memory',
            'nearest matching behavior alone is not retrieval proof',
            'only history-proven alternatives justify history-conditioned avoidable cost']}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k in ('design_id','world_count','nodes','edges','cycle_rank','task_count','world_task_choices_checked','candidate_order_replays','max_candidate_order_operations')}))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    check(parser.parse_args().output)
