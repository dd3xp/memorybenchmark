"""Build one reviewed Easy/Normal map at a time; geometry-only, zero model calls."""
import argparse,json
from copy import deepcopy
from pathlib import Path
from scripts.field_geography import THEMES,geography
from scripts.build_difficulty_maps import choose_fixture,balance_task_locations,fixture_diagnostics
from scripts.easy_map_common import fixed_world
from scripts.task_streams import four_exposure_tasks, exposure_diagnostics

ROOT=Path(__file__).resolve().parents[1]
LEGACY_FILES={'capulin':'rainbow_easy20','forest':'forest_geo_easy20','cascade':'cascade_easy20',
              'nessie':'nessie_normal30','dingo':'dingo_normal30','boar':'boar_normal30'}
FILES={'capulin':'capulin_easy16','forest':'forest_geo_easy16','cascade':'cascade_easy16',
       'nessie':'nessie_normal24','dingo':'dingo_normal24','boar':'boar_normal24'}

def build(theme):
    original=json.loads((ROOT/'memorybenchmark/data/history/difficulty-v1'/(LEGACY_FILES[theme]+'.json')).read_text(encoding='utf-8'))
    design=deepcopy(original);geo=geography(theme);normal=original['public']['difficulty']=='Normal'
    index=(('nessie','dingo','boar') if normal else ('capulin','forest','cascade')).index(theme)+1
    version=f'{"normal" if normal else "easy"}-{index:02d}-v3.0'
    design['design_id']=design['public']['version']=version
    design['status']='individually_authored_field_v2_pending_native_calibration'
    if theme=='capulin':
        design['design_id']=design['public']['version']='easy-01-v4.0'
        design['public'].update(name='玄锥熔原',terrain='volcanic-cone')
        design['provenance']={'reference_region':'Capulin Volcano National Monument','official_area_approx_acres':800,
            'official_area_approx_km2':3.2,'sources':['https://www.nps.gov/cavo/learn/nature/naturalfeaturesandecosystems.htm',
            'https://www.nps.gov/cavo/planyourvisit/choosing-your-hike.htm'],
            'scope':'The named whole national monument is the landscape reference, not a small crop of Danxia. Authored paths and distances are schematic, not a surveyed trail map.'}
        design['material_selection']['theme']='capulin'
    for field in ('locations','edges','view_box'):design['public'][field]=deepcopy(geo[field])
    design['presentation']={'terrain':design['public']['terrain'],'regions':geo['regions']}
    design['evaluation'].pop('authoring_geometry_check',None)
    seed=26110500+index+(10 if normal else 0)
    design['material_selection']['protocol']='four-exposure-materials-v1'
    if 'geographic' not in design['material_selection']:
        design['material_selection']['geographic']=list(design['public']['kinds'])
    design['material_selection'].setdefault('animal',[])
    design['material_selection']['human']=[]
    surveys=[k for k,v in design['public']['locations'].items() if v['kind']=='survey']
    design['tasks']=four_exposure_tasks(design['public']['kinds'],surveys,
        order_seed=67110502 if normal else 67110501,target_seed=seed+1200,
        max_steps=168 if normal else 88,name='区域巡测')
    design['evaluation']['stream_design']='Each material appears four times in four balanced blocks; two stages per task, no tutorial or unlock.'
    design['evaluation']['exposure_diagnostics']=exposure_diagnostics(design['tasks'])
    if normal:
        original_tasks=deepcopy(design['tasks'])
        for attempt in range(12):
            design['tasks']=deepcopy(original_tasks)
            fixture=choose_fixture(design,normal=True,seed=seed+attempt*10000,trials=4000)
            design['private_station_capabilities']=fixture
            balance_task_locations(design,seed=seed+300+attempt*10000)
            if not fixture_diagnostics(design,fixture)['unused_strict_replicas']:
                design['evaluation']['authoring_geometry_check']['joint_fixture_target_attempt']=attempt+1
                break
    else:
        fixture=choose_fixture(design,normal=False,seed=seed,trials=4000)
        design['fixed_world']=fixed_world(design['public']['kinds'],fixture)
        initial=fixture_diagnostics(design,fixture)
        if initial['unused_strict_replicas'] or abs(initial['nearest_match_rate']-.125)>.05:
            balance_task_locations(design,seed=seed+300,fixture=fixture)
    stats=fixture_diagnostics(design,fixture)
    if stats['unused_strict_replicas']:raise ValueError((theme,stats['unused_strict_replicas']))
    design['evaluation']['authoring_geometry_check'].update(stats)
    design['provenance'].update(layout_revision='individually-authored-field-v2',
        supersedes=original['design_id'],authoring_rationale=geo['rationale'],
        public_geography_review=geo['geometry_review'],
        boundary='Schematic authored roads inspired by the named landscape. Real names and sources remain private; no surveyed road reconstruction or guaranteed native-agent score.')
    design['native_session_budget']={'main_model_calls':180 if normal else 100,'final_model_calls':6,
        'effective_wall_seconds':3600,'reasoning_effort':'high','whole_session_transport_retries':0,
        'whole_session_failure_limit':0,'basis':'Preserve the declared Easy/Normal budgets; fresh zero-model feasibility checks precede future native evaluation.'}
    return design

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--map',choices=THEMES,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();design=build(args.map)
    path=args.output or ROOT/'memorybenchmark/data'/(FILES[args.map]+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'map':args.map,'version':design['design_id'],'nodes':len(design['public']['locations']),
          'roads':len(design['public']['edges']),'geometry':design['evaluation']['authoring_geometry_check'],
          'new_model_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
