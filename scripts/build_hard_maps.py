"""Author fixed regional Hard maps, using geometry only and zero model calls.

Reference windows are explicitly selected WGS84 rectangles. Node positions and
roads are schematic authored geography, not a reconstruction of historical roads.
This script writes only new Hard assets; Easy/Normal snapshots are never touched.
"""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from math import atan2, cos, hypot, pi, radians, sin
from pathlib import Path
from random import Random
import json

from scripts.build_difficulty_maps import geometry
from scripts.task_streams import requirement_interference_tasks, exposure_diagnostics, requirement_interference_diagnostics

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'memorybenchmark/data'
TYPES = 'ABCDEFGHIJKLMNOPQRSTUVWX'
GAME_OPERATIONS = 352
MODEL_CALLS = 400
REQUIREMENTS = {'catalogue': '归档编目', 'verify': '关联核验'}
NAMES = {
    'profile': '剖面资料', 'elevation': '高程资料', 'slope': '坡度资料',
    'soil': '土壤资料', 'drainage': '水系资料', 'vegetation': '植被资料',
    'lithology': '岩性资料', 'land_cover': '地表覆盖资料', 'shore': '岸线资料',
    'streamflow': '流量资料', 'erosion_form': '侵蚀地貌资料',
    'water_quality': '水质资料', 'sediment': '沉积物资料', 'bathymetry': '水深资料',
    'ungulate_tracks': '有蹄动物足迹资料', 'livestock_signs': '牧畜活动资料',
    'woodland_birds': '林鸟声学资料', 'small_mammal_signs': '小型哺乳动物活动资料',
    'otter_signs': '水獭活动资料', 'reptile_signs': '爬行动物活动资料',
    'farmland_birds': '农田鸟类观察资料', 'waterbird_record': '水鸟观察资料',
    'amphibian_record': '两栖动物活动资料', 'water_edna': '水域动物环境 DNA 资料',
    'built_form': '建筑形制资料', 'waterworks': '水工设施资料',
    'settlement_layout': '聚落格局资料', 'historic_road': '历史道路遗迹资料',
}
HUMAN = ['built_form', 'waterworks', 'settlement_layout', 'historic_road']
REGIONS = {
    'orcia': {
        'human_name': '奥尔恰谷', 'name': '金穗丘原', 'version': 'hard-01-v4.0',
        'terrain': 'hill-country', 'period': 'c. 1500 CE',
        'bbox': [11.43, 42.94, 11.75, 43.09],
        'geographic': ['profile', 'elevation', 'slope', 'soil', 'drainage', 'vegetation', 'lithology', 'land_cover'],
        'animal': ['ungulate_tracks', 'livestock_signs', 'woodland_birds', 'small_mammal_signs'],
        'sources': [
            'https://whc.unesco.org/en/list/1026/',
            'https://www.regione.toscana.it/-/castore',
            'https://www.visittuscany.com/it/attrazioni/riserva-naturale-regionale-di-ripa-dorcia/'],
        'seed': 15101,
    },
    'hampi': {
        'human_name': '亨比', 'name': '赤岩河邦', 'version': 'hard-02-v4.0',
        'terrain': 'rock-river', 'period': 'first half of the 16th century CE, before 1565',
        'bbox': [76.41, 15.22, 76.64, 15.36],
        'geographic': ['profile', 'elevation', 'lithology', 'shore', 'streamflow', 'soil', 'erosion_form', 'water_quality'],
        'animal': ['otter_signs', 'reptile_signs', 'farmland_birds', 'livestock_signs'],
        'sources': [
            'https://whc.unesco.org/en/list/241/',
            'https://whc.unesco.org/en/list/241/maps/',
            'https://maxwellmuseum.unm.edu/news-events/blog/research-wednesday-surveying-imperial-city-vijayanagara-south-india',
            'https://iucnosgbull.org/Volume37/Samad_et_al_2020.html'],
        'seed': 15102,
    },
    'angkor': {
        'human_name': '吴哥', 'name': '青陂水原', 'version': 'hard-03-v4.0',
        'terrain': 'reservoir-plain', 'period': 'c. 1200–1250 CE',
        'bbox': [103.76, 13.33, 103.99, 13.49],
        'geographic': ['profile', 'soil', 'drainage', 'sediment', 'bathymetry', 'water_quality', 'vegetation', 'land_cover'],
        'animal': ['waterbird_record', 'amphibian_record', 'water_edna', 'small_mammal_signs'],
        'sources': [
            'https://whc.unesco.org/en/list/668/',
            'https://pmc.ncbi.nlm.nih.gov/articles/PMC1964867/'],
        'seed': 15103,
    },
}


def area_km2(bbox):
    west, south, east, north = bbox
    return 6371.0088**2 * radians(east - west) * (sin(radians(north)) - sin(radians(south)))


def public_rules():
    return [
        '每项委托有两段。每段给出目标、指定资料与处理要求；依次到目标主动 survey 采集，在匹配的站主动 process 处理。两段成功后回 C 营地主动 submit。',
        '优先减少道路总距离，距离相同时减少操作。公开地图从第一项起全部开放；只能沿道路逐点移动，不可跳过中间节点。',
        '本图有十二类资料、二十四种站型，每型两座等价站。处理要求有“归档编目”和“关联核验”，每段要求直接公开。',
        '能力由“资料＋本段处理要求”共同决定。必须区分本段要求，不能直接沿用另一要求的选站结论。所有站型均为候选，字母、地名和资料主题不提示能力。',
        '每种站型在每种要求下支持一至两类资料；同型两站在相同要求下能力完全一致。所有能力在地图制作时固定，跨任务和 Agent 不变。',
        '只有采集当前原始资料后主动 process，才反馈该站型在本段要求下支持的全部资料与本次结果；经过或到访不揭示能力，不提供独立查询。反馈不揭示其他处理要求下的能力。',
        '处理不匹配时原始资料保留，可以换站；成功和失败均消耗操作。相同资料在另一种要求下的旧反馈不能直接作为本段能力结论。',
        '只有在本段目标主动 survey 才取得资料；到达不会自动采集。勘探占一次操作、不增加路程；成功处理后进入下一段并重新采集。',
        '每项从 C 开始，位置、资料、对话和工作记忆重置；只有 Agent 自主保存的持久记忆跨 session。失败后继续固定任务流，不补发能力答案。',
        '每项最多三百五十二次操作，read 免费。read 返回当前地图和状态，不附加历史能力。地图没有天气、战斗、体力或工具门槛。',
    ]


def build_geography(theme):
    from scripts.hard_geography import geography
    return geography(theme)


def tasks_for(kinds, surveys, seed):
    return requirement_interference_tasks(kinds,surveys,requirements=REQUIREMENTS,
        order_seed=67110503,target_seed=seed,max_steps=GAME_OPERATIONS,name='区域联程巡测')


def fixture_candidate(kinds, rng):
    order=list(kinds);rng.shuffle(order);types=list(TYPES);rng.shuffle(types)
    count=len(order)
    assert count==12
    primary=types[:count];secondary=types[count:]
    table={t:{r:[] for r in REQUIREMENTS} for t in TYPES}
    # Both alternatives change purpose: no type can bypass the requirement.
    changed=list(range(count));rng.shuffle(changed)
    destination={i:changed[(j+1)%count] for j,i in enumerate(changed)}
    for i,k in enumerate(order):
        table[primary[i]]['catalogue'].append(k)
        table[secondary[i]]['catalogue'].append(k)
        table[primary[destination[i]]]['verify'].append(k)
        table[secondary[(i+count//2)%count]]['verify'].append(k)
    return {t:{r:sorted(v) for r,v in by.items()} for t,by in table.items()}


def diagnostics(design, fixture, distances=None):
    d=distances or geometry(design);pub=design['public'];counts=Counter();nearest=0.;costs=[]
    stations={s:t for t,v in pub['station_types'].items() for s in v['stations']}
    for task in design['tasks'].values():
        for i,stage in enumerate(task['stages']):
            target=stage['target'];destination=task['stages'][i+1]['target'] if i==0 else 'C'
            valid=[s for s,t in stations.items() if stage['required_kind'] in fixture[t][stage['requirement']]]
            least=min(d[target][s] for s in stations);near=[s for s in stations if d[target][s]==least]
            nearest+=sum(s in valid for s in near)/len(near)
            best=min(d[target][s]+d[s][destination] for s in valid)
            winners=[s for s in valid if d[target][s]+d[s][destination]==best]
            if len(winners)==1:counts.update(winners)
            costs.append(best)
    return {'stage_contexts':len(costs),'nearest_match_rate':nearest/len(costs),
        'unused_strict_replicas':sorted(set(stations)-set(counts)),
        'strict_replica_counts':dict(sorted(counts.items())),
        'mean_processing_leg_distance':sum(costs)/len(costs)}


def choose_fixture(design, seed, trials=24000):
    rng=Random(seed);d=geometry(design);best=None
    for trial in range(trials):
        fixture=fixture_candidate(design['public']['kinds'],rng);stats=diagnostics(design,fixture,d)
        score=(len(stats['unused_strict_replicas']),abs(stats['nearest_match_rate']-1/12))
        if best is None or score<best[0]:best=(score,fixture,stats,trial+1)
        if score[0]==0 and score[1]<=.04:break
    design['evaluation']['authoring_geometry_check']={**best[2],'seed':seed,'trials_examined':trial+1,'selected_candidate':best[3],
        'method':'Predeclared fixed-seed geometry-only candidate search; no model outcomes.'}
    return best[1]


def balance_targets(design, seed):
    """Swap only target locations, preserving all context counts and exposures."""
    fixture=design['private_station_capabilities'];d=geometry(design)
    initial=diagnostics(design,fixture,d)
    if not initial['unused_strict_replicas']:return
    stages=[s for task in design['tasks'].values() for s in task['stages']]
    rng=Random(seed);current=initial
    def score(stats):return 5*len(stats['unused_strict_replicas'])+abs(stats['nearest_match_rate']-1/12)
    best=(score(current),[s['target'] for s in stages],current);accepted=0
    for step in range(6000):
        a,b=rng.sample(range(len(stages)),2)
        if a//2==b//2:continue
        stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
        if any(stages[i]['target']==stages[i+1]['target'] for i in (a//2*2,b//2*2)):
            stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target'];continue
        candidate=diagnostics(design,fixture,d)
        if score(candidate)<=score(current)+.01:
            current=candidate;accepted+=1
            if score(current)<best[0]:best=(score(current),[s['target'] for s in stages],current)
        else:stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
        if not best[2]['unused_strict_replicas'] and abs(best[2]['nearest_match_rate']-1/12)<=.04:break
    for stage,target in zip(stages,best[1]):stage['target']=target
    for task in design['tasks'].values():task['target']=task['stages'][0]['target']
    design['evaluation']['authoring_geometry_check'].update(best[2],target_swap_seed=seed,
        target_swap_trials_examined=step+1,target_swaps_accepted=accepted,
        target_swap_scope='Only target locations; material/requirement order and every target frequency preserved.')
    if best[2]['unused_strict_replicas']:raise ValueError('Dominated Hard replicas remain: '+str(best[2]['unused_strict_replicas']))


def material_catalog():
    categories={k:('human' if k in HUMAN else 'geographic') for k in NAMES}
    for spec in REGIONS.values():
        for k in spec['animal']:categories[k]='animal'
    return {'version':'hard-materials-1','materials':{k:{'name':v,'category':categories[k]} for k,v in NAMES.items()},
        'scope':'Authored observation-package categories, not historical species distributions or station capabilities.',
        'sources':{theme:spec['sources'] for theme,spec in REGIONS.items()}}


def build(theme):
    spec=REGIONS[theme];geography=build_geography(theme)
    loc,edges,surveys=(geography[k] for k in ('locations','edges','surveys'))
    selected=spec['geographic']+HUMAN;kinds={k:NAMES[k] for k in selected}
    catalog=material_catalog();catalog_sha=sha256(json.dumps(catalog,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    design={'design_id':spec['version'],'status':'authored_hard_disjoint_v4_pending_native_agent_calibration',
        'world_generator':'fixed_conditional_station_sets','fixed_world':'omega_hard_'+theme,
        'material_selection':{'protocol':'four-exposure-materials-v1','catalog_version':catalog['version'],
            'catalog_sha256':catalog_sha,'theme':theme,'geographic':spec['geographic'],'animal':[],'human':HUMAN},
        'native_session_budget':{'main_model_calls':MODEL_CALLS,'final_model_calls':6,'effective_wall_seconds':604800,'reasoning_effort':'high',
                                 'whole_session_transport_retries':0,'whole_session_failure_limit':0,
                                 'basis':'Common authoring budget; new independently authored geographies require a fresh zero-model feasibility check before native calibration.'},
        'public':{'version':spec['version'],'name':spec['name'],'difficulty':'Hard','terrain':spec['terrain'],
            'capability_model':'conditional-overlapping-sets-v1','requirements':REQUIREMENTS,
            'station_query_enabled':False,'manual_survey_required':True,'view_box':geography['view_box'],
            'rules':public_rules(),'kinds':kinds,
            'vocabulary':{'survey':'测绘点','station':'处理站','collect':'采集','process':'处理','item':'资料','submit':'交付'},
            'station_types':{t:{'name':f'{t}型','stations':[t+'1',t+'2']} for t in TYPES},
            'locations':loc,'edges':edges},
        'tasks':tasks_for(kinds,surveys,spec['seed']+1200),
        'presentation':{'terrain':spec['terrain'],'regions':geography['regions']},
        'evaluation':{'experience_protocol':'station-experience-opportunity-1',
            'knowledge_protocol':'delivered-conditional-capability-sets-v1','exact_unknown_world_references':False,
            'candidate_family':'Unobserved (type, requirement) pairs remain unknown; the fixed fixture is not a hypothesis family.',
            'stream_design':'48 ordinary tasks, 96 stages, each of 24 material/requirement pairs appears four times; each survey site six times; no tutorial or unlock.'},
        'provenance':{'layout_authoring':{'revision':'individually-authored-v2','rationale':geography['rationale'],
            'topology':geography['topology'],'planar_junctions_added':geography['planar_junctions_added'],
            'features':geography['features'],'edge_tags':geography['edge_tags']},'reference_region':spec['human_name'],'reference_period':spec['period'],'sources':spec['sources'],
            'reference_window':{'crs':'EPSG:4326','bbox_west_south_east_north':spec['bbox'],
                'approximate_area_km2':round(area_km2(spec['bbox']),3),
                'area_method':'Spherical longitude/latitude rectangle, mean Earth radius 6371.0088 km.',
                'basis':'Author-selected regional reference rectangle, not a heritage boundary or measured navigable footprint.'},
            'scope':'Historical landscape inspiration only. Roads, drawing coordinates, sites, tasks and processing capabilities are authored; not a historical road reconstruction. Current ecology sources do not establish historical species locations.',
            'private_boundary':'Real names, dates, source URLs and coordinates are excluded from agent observations.'}}
    design['private_station_capabilities']=choose_fixture(design,spec['seed'])
    balance_targets(design,spec['seed']+4400)
    design['evaluation']['exposure_diagnostics']=exposure_diagnostics(design['tasks'])
    design['evaluation']['requirement_disjointness']={'all_materials_disjoint':True,'correct_types_per_requirement':2,
        'overlap_per_material':{kind:len({t for t,v in design['private_station_capabilities'].items() if kind in v['catalogue']}
            & {t for t,v in design['private_station_capabilities'].items() if kind in v['verify']}) for kind in kinds}}
    design['evaluation']['requirement_interference']=requirement_interference_diagnostics(design['tasks'])
    return design


def main():
    DATA.mkdir(exist_ok=True)
    catalog=material_catalog()
    (DATA/'material_catalog_hard_v1.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map',choices=tuple(REGIONS),help='Author and review one landscape at a time')
    args=parser.parse_args()
    for theme in ([args.map] if args.map else REGIONS):
        design=build(theme);path=DATA/(theme+'_hard48.json')
        path.write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'map':theme,'nodes':len(design['public']['locations']),'roads':len(design['public']['edges']),
                          'area_km2':design['provenance']['reference_window']['approximate_area_km2'],
                          'geometry':design['evaluation']['authoring_geometry_check']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
