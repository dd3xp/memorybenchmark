"""Whole regions and four exposures of each complete Lunatic requirement."""
from collections import Counter
from hashlib import sha256
from pathlib import Path
from random import Random
import argparse,json
from scripts.lunatic_geography import THEMES,geography
from scripts.lunatic_geography.whole_region import REGION_NAMES
from scripts.build_hard_maps import NAMES,HUMAN,TYPES,area_km2
from scripts.build_difficulty_maps import geometry
from scripts.task_streams import regional_transfer_tasks,exposure_diagnostics

ROOT=Path(__file__).resolve().parents[1]
REQUIREMENTS={'catalogue':'归档编目','verify':'关联核验'}
REGIONS={
 'scandinavia':{'human_name':'斯堪的纳维亚','name':'霜湾岭国','version':'lunatic-01-v3.1','terrain':'fjord-peninsulas',
    'period':'c. 1250 CE landscape inspiration; modern geographic reference outline','bbox':[4.1,54.2,31.8,71.6],
    'geographic':['profile','elevation','shore','drainage','sediment','vegetation','lithology','water_quality'],
    'animal':['waterbird_record','otter_signs','livestock_signs','woodland_birds'],'seed':26110741,
    'sources':['https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2']},
 'mongolia':{'human_name':'蒙古','name':'苍原驿邦','version':'lunatic-02-v3.1','terrain':'steppe-corridors',
    'period':'c. 1250 CE landscape inspiration; modern geographic reference outline','bbox':[87.4,41.3,120.2,52.3],
    'geographic':['profile','elevation','slope','soil','drainage','vegetation','lithology','land_cover'],
    'animal':['ungulate_tracks','livestock_signs','farmland_birds','small_mammal_signs'],'seed':26110742,
    'sources':['https://www.mongolianatlas.ac.mn/en/atlas/general','https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2']},
 'andes':{'human_name':'安第斯','name':'云脊长邦','version':'lunatic-03-v3.1','terrain':'andean-passes',
    'period':'c. 1500 CE landscape inspiration; modern geographic reference outline','bbox':[-82.5,-55.8,-62.0,11.5],
    'geographic':['profile','elevation','slope','soil','drainage','lithology','erosion_form','land_cover'],
    'animal':['ungulate_tracks','livestock_signs','woodland_birds','small_mammal_signs'],'seed':26110743,
    'sources':['https://wikicolombia.unocha.org/index.php?title=Cordillera_de_los_Andes','https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2']}}

def tasks_for(kinds,surveys,seed):
    return regional_transfer_tasks(kinds,surveys,requirements=REQUIREMENTS,regions=REGION_NAMES,
        order_seed=761107,target_seed=seed,max_steps=352,name='全域分区巡测')

def fixture_candidate(kinds,rng):
    kinds=list(kinds);rng.shuffle(kinds);types=list(TYPES);rng.shuffle(types)
    table={t:{r:[] for r in REQUIREMENTS} for t in TYPES}
    primary_shift=rng.randrange(1,16);secondary_shift=rng.randrange(1,8)
    for i,kind in enumerate(kinds):
        table[types[i]]['catalogue'].append(kind)
        table[types[16+i//2]]['catalogue'].append(kind)
        table[types[(i+primary_shift)%16]]['verify'].append(kind)
        table[types[16+(i//2+secondary_shift)%8]]['verify'].append(kind)
    return {t:{r:sorted(v) for r,v in by.items()} for t,by in table.items()}

def stream_diagnostics(tasks):
    stats=exposure_diagnostics(tasks)
    stats['repeat_count']=sum(n-1 for n in stats['context_exposures'].values())
    stats['encounter_key']=['required_kind','requirement']
    return stats

def diagnostics(design,fixture,distances=None):
    d=distances or geometry(design);public=design['public'];groups={r:[s for s,n in public['locations'].items()
        if n['kind']=='station' and n['region_category']==r] for r in REGION_NAMES}
    matches={(kind,requirement,region):[s for s in groups[region] if kind in fixture[public['locations'][s]['station_type']][requirement]]
             for kind in public['kinds'] for requirement in REQUIREMENTS for region in REGION_NAMES}
    wins=Counter();nearest=0;costs=[]
    for task in design['tasks'].values():
        for i,stage in enumerate(task['stages']):
            target=stage['target'];destination=task['stages'][i+1]['target'] if i==0 else 'C'
            valid=matches[stage['required_kind'],stage['requirement'],stage['required_region']]
            closest=min(d[target][s] for s in groups[stage['required_region']]);near=[s for s in groups[stage['required_region']] if d[target][s]==closest]
            nearest+=sum(s in valid for s in near)/len(near)
            best=min(d[target][s]+d[s][destination] for s in valid)
            winners=[s for s in valid if d[target][s]+d[s][destination]==best]
            if len(winners)==1:wins.update(winners)
            costs.append(best)
    stations={s for group in groups.values() for s in group}
    return {'stage_contexts':len(costs),'nearest_match_rate':nearest/len(costs),'unused_strict_replicas':sorted(stations-set(wins)),
        'strict_replica_counts':dict(sorted(wins.items())),'mean_processing_leg_distance':sum(costs)/len(costs)}

def balance_regional_targets(design,fixture,seed):
    """Swap only survey assignments so the smaller stream still uses every station.

    Material/purpose order, four exposures, regional transfers, survey visit
    counts and hidden abilities remain fixed. No model outcomes are consulted.
    """
    distance=geometry(design);locations=design['public']['locations']
    stages=[s for t in design['tasks'].values() for s in t['stages']]
    choices={(k,r,z):[s for s,n in locations.items() if n['kind']=='station' and n['region_category']==z
        and k in fixture[n['station_type']][r]] for k in design['public']['kinds'] for r in REQUIREMENTS for z in REGION_NAMES}
    def winner(i):
        stage=stages[i];destination=stages[i+1]['target'] if i%2==0 else 'C'
        options=choices[stage['required_kind'],stage['requirement'],stage['required_region']]
        costs={s:distance[stage['target']][s]+distance[s][destination] for s in options}
        best=min(costs.values());winners=[s for s,c in costs.items() if c==best]
        return winners[0] if len(winners)==1 else None
    winners=[winner(i) for i in range(len(stages))];counts=Counter(s for s in winners if s)
    rng=Random(seed);accepted=0
    for attempt in range(60000):
        if len(counts)==72:break
        a,b=rng.sample(range(len(stages)),2)
        if a//2==b//2 or stages[a]['target']==stages[b]['target']:continue
        if stages[a^1]['target']==stages[b]['target'] or stages[b^1]['target']==stages[a]['target']:continue
        affected={a,b}
        if a%2:affected.add(a-1)
        if b%2:affected.add(b-1)
        before=len(counts);old={i:winners[i] for i in affected}
        for s in old.values():
            if s:
                counts[s]-=1
                if not counts[s]:del counts[s]
        stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
        new={i:winner(i) for i in affected}
        counts.update(s for s in new.values() if s)
        if len(counts)>before or len(counts)==before and rng.random()<.3:
            accepted+=1
            for i,s in new.items():winners[i]=s
        else:
            for s in new.values():
                if s:
                    counts[s]-=1
                    if not counts[s]:del counts[s]
            counts.update(s for s in old.values() if s)
            stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
    for task in design['tasks'].values():task.update(task['stages'][0])
    if len(counts)!=72:raise ValueError(('Station usefulness target not reached',len(counts)))
    return {'seed':seed,'proposals':attempt+1,'accepted_survey_swaps':accepted,
        'method':'Fixed-seed survey swaps for physical station usefulness;128 stages,64 survey sites twice, regional sequence and abilities unchanged.'}

def build(theme):
    spec=REGIONS[theme];geo=geography(theme);selected=spec['geographic']+spec['animal']+HUMAN
    kinds={k:NAMES[k] for k in selected}
    rules=[
        '整张公开地图可自由通行。逐点移动；道路权重是实验距离单位。水路连接已公开标出，连接线交叉处不能中途换乘。',
        '每项任务含两段。每段先到指定测绘点主动 survey 采集资料，再去支持该资料与本段处理要求的站处理；两段完成后回营地 submit。',
        '本图有十六类资料、二十四种站型。每种站型在自然区域、人类聚居区和动物栖息区各有一座站。',
        '每段同时明确给出“归档编目”或“关联核验”，以及必须前往的处理区域类别。资料类别不限定处理区域：地理资料也可能要求在聚居区处理。',
        '能力由资料与处理要求决定；相同站型在相同要求下的能力跨区域相同。区域是额外的公开地点约束，不改变站型能力。',
        '到访、经过和看地图不揭示站型能力。携带资料主动 process，只揭示该型在本段处理要求下支持的全部资料与本次结果，不揭示另一要求。',
        '到错区域处理时，原始资料保留，阶段不推进，也不揭示站型能力。到正确区域但能力不匹配时，原始资料保留，并交付本次要求下的能力反馈。',
        '基站字母、地名和资料主题不提示隐藏能力。尽量减少道路总距离，距离相同时减少操作。任务结束后的持久记忆由你自主读写。']
    d={'design_id':spec['version'],'status':'authored_regional_lunatic_pending_native_calibration',
       'world_generator':'fixed_conditional_station_sets','fixed_world':'omega_lunatic_regional_'+theme,
       'material_selection':{'protocol':'four-exposure-materials-v1','theme':theme,'geographic':spec['geographic'],'animal':spec['animal'],'human':HUMAN},
       'native_session_budget':{'main_model_calls':400,'final_model_calls':6,'effective_wall_seconds':604800,
           'reasoning_effort':'high','whole_session_transport_retries':0,'whole_session_failure_limit':0,
           'basis':'Same per-task calls/operations as Hard; week effective wall; no native result calibration.'},
       'public':{'version':spec['version'],'name':spec['name'],'difficulty':'Lunatic','terrain':spec['terrain'],
           'capability_model':'conditional-overlapping-sets-v1','requirements':REQUIREMENTS,'processing_regions':REGION_NAMES,
           'station_query_enabled':False,'manual_survey_required':True,'view_box':geo['view_box'],'rules':rules,'kinds':kinds,
           'vocabulary':{'survey':'测绘点','station':'处理站','collect':'采集','process':'处理','item':'资料','submit':'交付'},
           'station_types':{t:{'name':t+'型','stations':[t+str(i) for i in (1,2,3)]} for t in TYPES},
           'locations':geo['locations'],'edges':geo['edges'],'ferry_edges':[key.split('|') for key,tags in geo['edge_tags'].items() if 'ferry' in tags]},
       'tasks':tasks_for(kinds,geo['surveys'],spec['seed']+1200),
       'presentation':{'terrain':spec['terrain'],'regions':geo['regions'],'edge_tags':geo['edge_tags']},
       'evaluation':{'experience_protocol':'station-experience-opportunity-1','knowledge_protocol':'delivered-conditional-capability-sets-v1',
           'exact_unknown_world_references':False,'primary_encounter_key':['required_kind','requirement'],
           'stream_design':'64 ordinary two-stage tasks;32 material/purpose contexts exactly four times. Their four encounters cover all three destination regions, changing region at every repeat. Region is not a new ability or encounter identity;64 survey sites each twice.'},
       'provenance':{'reference_region':spec['human_name'],'reference_period':spec['period'],'sources':spec['sources'],
           'reference_window':{'crs':'EPSG:4326','bbox_west_south_east_north':spec['bbox'],'approximate_area_km2':round(area_km2(spec['bbox']),3),
              'basis':'Whole-region reference extent. Not a historical boundary, actual Andes polygon, or walkable-surface measurement.'},
           'layout_authoring':{'revision':'whole-region-zones-v1','rationale':geo['rationale'],'topology':geo['topology'],
              'geometry_review':geo['geometry_review'],'source_data':geo['source_data'],'reference_locations':geo['reference_locations'],'shore_access_adjustments':geo['access_adjustments']},
           'scope':'Modern reference geography with authored roads, facilities, survey points and mutually exclusive benchmark region partitions. Not a reconstruction of historical transport, population or animal ranges.'}}
    fixture=json.loads((ROOT/'scripts/lunatic_geography/whole_region_data'/(theme+'-capabilities.json')).read_text(encoding='utf-8'))
    d['private_station_capabilities']=fixture
    d['evaluation']['survey_assignment_review']=balance_regional_targets(d,fixture,spec['seed']+77)
    d['evaluation']['authoring_geometry_check']={**diagnostics(d,fixture),'method':'Previously authored station abilities preserved; reducing task count does not resample abilities. Public region constrains physical destination.'}
    d['evaluation']['stream_diagnostics']=stream_diagnostics(d['tasks'])
    d['evaluation']['exposure_diagnostics']=exposure_diagnostics(d['tasks'])
    return d

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',choices=THEMES,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();d=build(a.map);target=a.output or ROOT/'memorybenchmark/data'/(a.map+'_lunatic64.json')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'map':a.map,'design':d['design_id'],'nodes':len(d['public']['locations']),'roads':len(d['public']['edges']),
        'tasks':len(d['tasks']),'geometry':d['evaluation']['authoring_geometry_check'],'model_calls':0}),flush=True)

if __name__=='__main__':main()
