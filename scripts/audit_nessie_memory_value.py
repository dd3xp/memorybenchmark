"""Check scripted information value and export genuine engine trace witnesses.

This reads the verified design-calibration artifact and replays two independent
feedback policies. It never runs a language model or supplies memories to one.
"""
from hashlib import sha256
import argparse
import gzip
import json
from pathlib import Path

from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_session import NESSIE_EASY_DESIGN
from scripts.check_easy20_linked import FeedbackSimulation
from scripts.check_station_capability import export_case


def audit(output, validation):
    raw=gzip.decompress(Path(validation).read_bytes())
    verified=json.loads(raw)
    design=load_design(NESSIE_EASY_DESIGN)
    assert verified['design_id']==design['design_id']
    assert verified['design_sha256']==sha256(NESSIE_EASY_DESIGN.read_bytes()).hexdigest()
    modes=verified['fixed_fixture_real_kernel_replays']
    retain,clear=[modes[mode]['followup_T2_T20'] for mode in ('retain','clear')]
    rows=[{'task':a['task'],'retained_distance':a['distance'],'cleared_distance':b['distance'],
           'saved_distance':b['distance']-a['distance']}
          for a,b in zip(modes['retain']['rows'][1:],modes['clear']['rows'][1:])]
    assert len(rows)==19 and all(a['task']==b['task'] for a,b in zip(modes['retain']['rows'],modes['clear']['rows']))
    assert modes['retain']['rows'][0]==modes['clear']['rows'][0], 'T1 must have no historical information advantage'
    assert retain['distance']<clear['distance'] and retain['station_attempts']<clear['station_attempts']
    worlds=verified['feedback_policy_calibration']['per_world']
    gains=[1-row['all']['retain']['distance']/row['all']['clear']['distance'] for row in worlds]
    assert len(worlds)==576 and min(gains)>0, 'The identical feedback policy must benefit over the full stream in every candidate assignment'
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    simulator=FeedbackSimulation(design);witnesses=[]
    for mode in ('retain','clear'):
        game=StationGame(map_world(design),design);facts={}
        for task in list(design['tasks'])[:13]:
            row,new=simulator.run(map_world(design),task,facts if mode=='retain' else {},runtime=game)
            if mode=='retain':facts=new
        reference=next(r for r in modes[mode]['rows'] if r['task']=='T13')
        assert row=={key:value for key,value in reference.items() if key!='task'}
        case=export_case(output,'T13-scripted-'+mode,game)
        log=output/case['log'];body=log.read_bytes()
        case['uncompressed_log_sha256']=sha256(body).hexdigest()
        compressed=log.with_suffix(log.suffix+'.gz')
        compressed.write_bytes(gzip.compress(body,mtime=0));log.unlink()
        case['log']+='.gz'
        case['log_encoding']='Lossless gzip of authoritative scripted engine events'
        case['condition']=mode
        witnesses.append(case)
    result={'kind':'scripted_memory_opportunity_audit_not_native_agent_results',
            'design_id':design['design_id'],'design_sha256':verified['design_sha256'],
            'validation_uncompressed_sha256':sha256(raw).hexdigest(),
            'auditor_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
            'policy':'Identical public-geography feedback policy; only prior actually delivered station feedback persists in retain. Clear starts each task with empty facts. Current-task learning and public bijection inference are allowed in both.',
            'fixed_map_followup_T2_T20':{'retain':retain,'clear':clear,
                'distance_reduction_percent':100*(1-retain['distance']/clear['distance']),
                'operations_reduction_percent':100*(1-retain['operations']/clear['operations']),
                'lower_distance_tasks':sum(r['saved_distance']>0 for r in rows),
                'equal_distance_tasks':sum(r['saved_distance']==0 for r in rows),
                'higher_distance_tasks':sum(r['saved_distance']<0 for r in rows),'rows':rows},
            'candidate_assignment_sensitivity':{'worlds':576,'period':'T1-T20',
                'all_worlds_positive_distance_gain':True,
                'distance_reduction_percent_min_max':[100*min(gains),100*max(gains)],
                'actual_runtime_assignment_remains_fixed':True},
            'witnesses':witnesses,'new_real_kernel_tasks':26,'model_calls':0,
            'scope':'Checks that historical station knowledge has useful route-cost signal. This is one scripted policy, not an optimal-policy bound or a guarantee that any native agent saves, retrieves, applies memory, or wins every task. Native outcomes must be reported separately without changing the map after seeing them.'}
    (output/'memory-value.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation',type=Path,default=Path('docs/assets/nessie-easy/validation-full.json.gz'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit(args.output,args.validation)
    print(json.dumps({'design_id':result['design_id'],
                      'fixed_map':result['fixed_map_followup_T2_T20'],
                      'candidate_assignments':result['candidate_assignment_sensitivity'],
                      'model_calls':0},ensure_ascii=False))


if __name__=='__main__':main()
