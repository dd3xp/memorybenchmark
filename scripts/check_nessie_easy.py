"""Validate the fixed themed map without a model or authored agent memories."""
from hashlib import sha256
import argparse,json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame,load_design,map_world
from memorybenchmark.prototypes.station_experience import experience_schedule
from memorybenchmark.prototypes.station_session import NESSIE_EASY_DESIGN,StationSession
from scripts.check_easy20_linked import FeedbackSimulation,calibrate
from scripts.check_easy20_reuse import validate_success_guarantee


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    design=load_design(NESSIE_EASY_DESIGN);world=map_world(design)
    # Validate the one map that actually runs. Removing the public groups
    # expands evaluator hypotheses to 8!; it does not randomize the fixture.
    guarantee=validate_success_guarantee(design,world_ids=(world,))
    calibration=calibrate(design,design['design_id'],world_ids=(world,))
    sim=FeedbackSimulation(design);fixed={};public_boundary=[]
    for retain in (True,False):
        game=StationGame(world,design);facts={};rows=[]
        for task in design['tasks']:
            # One standalone observation contains only the selected commission.
            bound=StationSession(StationGame(world,design),task)
            encoded=json.dumps(bound.initial,ensure_ascii=False)
            assert not any(s in encoded for s in ('omega_','private_worlds','fixed_world','provenance','forestryandland'))
            public_boundary.append(task)
            row,new=sim.run(world,task,facts if retain else {},runtime=game)
            if retain:facts=new
            rows.append({'task':task,**row})
        fixed['retain' if retain else 'clear']={'rows':rows,'totals':{k:sum(r[k] for r in rows) for k in ('distance','operations','moves','station_attempts')},
            'followup_T2_T20':{k:sum(r[k] for r in rows[1:]) for k in ('distance','operations','moves','station_attempts')}}
    report={'kind':'scripted_map_feasibility_and_information_check_not_agent_results','llm_calls':0,
        'design_id':design['design_id'],'design_sha256':sha256(NESSIE_EASY_DESIGN.read_bytes()).hexdigest(),
        'validator_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'fixed_world':world,
        'nodes':len(design['public']['locations']),'roads':len(design['public']['edges']),
        'candidate_family_size':len(design['private_worlds']),
        'success_guarantee':guarantee,'feedback_policy_calibration':calibration,
        'fixed_fixture_real_kernel_replays':fixed,'public_boundary_checks':len(public_boundary),
        'schedule':experience_schedule(design),
        'scope':'Fixed actual map: forty feedback-policy simulations and forty real kernel replays. The full candidate family defines evaluator uncertainty, not runtime randomization. No all-assignment or arbitrary type-order budget guarantee. Scripted policy sees prior delivered feedback, not hidden assignments. References are not memory GT or native agent scores.'}
    (args.output/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'design_id':design['design_id'],'nodes':report['nodes'],'roads':report['roads'],
        'candidate_family_size':report['candidate_family_size'],'max_policy_operations':calibration['max_policy_operations'],
        'scripted_policy_replays':calibration['completed_replays'],'real_kernel_replays':40,
        'fixed_fixture_T2_T20':{k:v['followup_T2_T20'] for k,v in fixed.items()},'llm_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
