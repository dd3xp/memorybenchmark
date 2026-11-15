"""Public regional constraints, exact encounter denominators and feedback."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile,unittest
from memorybenchmark.prototypes.station_capability import StationGame,load_design,map_world,region_matches
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_routes import walk,station_options,known_world_route
from memorybenchmark.prototypes.station_knowledge import evidence_support
from memorybenchmark.prototypes.station_metrics import score_stream,summarize_stream
from memorybenchmark.prototypes.station_pilot import access_guide,movement_tool
from memorybenchmark.prototypes.field_service import FieldService
from scripts.build_lunatic_maps import REGIONS
from scripts.lunatic_geography import geography
from scripts.hard_geography.review import enters_polygon

ROOT=Path(__file__).resolve().parents[1]
class RegionalLunaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps={t:load_design(ROOT/'memorybenchmark/data'/(t+'_lunatic64.json')) for t in REGIONS}

    def single(self):
        d=deepcopy(self.maps['scandinavia']);stage=deepcopy(d['tasks']['T1']['stages'][0])
        d['tasks']={'T1':{'name':'分区验收','start':'C','submit_at':'C',**stage,'stages':[stage],'max_steps':352}}
        typ=next(t for t,v in d['private_station_capabilities'].items() if stage['required_kind'] in v[stage['requirement']])
        stations={d['public']['locations'][s]['region_category']:s for s in d['public']['station_types'][typ]['stations']}
        return d,stage,stations

    def collect(self,game):
        walk(game,game.task['target']);game.step({'type':'survey'})

    def finish(self,game,station):
        walk(game,station);feedback=game.step({'type':'process'})['feedback']
        self.assertEqual(feedback['result'],'processed')
        walk(game,'C');self.assertTrue(game.step({'type':'submit'})['observation']['success'])
        return feedback

    def test_material_purpose_repeats_four_times_across_regions_on_the_whole_map(self):
        for theme,d in self.maps.items():
            public=d['public'];self.assertGreaterEqual(len(public['locations']),200)
            stages=[s for t in d['tasks'].values() for s in t['stages']]
            contexts=Counter((s['required_kind'],s['requirement']) for s in stages)
            self.assertEqual((len(d['tasks']),len(contexts),set(contexts.values())),(64,32,{4}))
            self.assertEqual(set(Counter(s['target'] for s in stages).values()),{2})
            zone_counts=Counter(s['required_region'] for s in stages)
            self.assertLessEqual(max(zone_counts.values())-min(zone_counts.values()),1)
            for kind,requirement in contexts:
                zones=[s['required_region'] for s in stages if (s['required_kind'],s['requirement'])==(kind,requirement)]
                self.assertEqual(len(set(zones)),3)
                self.assertTrue(all(a!=b for a,b in zip(zones,zones[1:])))
            self.assertEqual((len(public['kinds']),len(d['material_selection']['geographic']),len(d['material_selection']['animal']),len(d['material_selection']['human'])),(16,8,4,4))
            for typ,group in public['station_types'].items():
                self.assertEqual({public['locations'][s]['region_category'] for s in group['stations']},set(public['processing_regions']))
                self.assertEqual(len(group['stations']),3)
            for kind in public['kinds']:
                by={r:{t for t,v in d['private_station_capabilities'].items() if kind in v[r]} for r in public['requirements']}
                self.assertFalse(by['catalogue'] & by['verify'])
            geo=geography(theme)
            self.assertEqual(public['locations'],geo['locations'])
            self.assertEqual(public['edges'],geo['edges'])
            for k,n in public['locations'].items():
                region=next(r for r in geo['regions'] if r['id']==n['region_id'])
                self.assertEqual(n['region_category'],region['category'])

    def test_land_connections_do_not_silently_cross_lakes(self):
        for theme,d in self.maps.items():
            geo=geography(theme);locations=d['public']['locations']
            for a,b,_ in d['public']['edges']:
                if 'ferry' in geo['edge_tags']['|'.join(sorted((a,b)))]:
                    continue
                p,q=locations[a],locations[b]
                self.assertFalse(any(enters_polygon((p['x'],p['y']),(q['x'],q['y']),ring)
                                     for ring in geo['features']['lakes']),(theme,a,b))

    def test_wrong_region_never_reveals_capability_and_cannot_mask_first_error(self):
        d,stage,stations=self.single();game=StationGame(map_world(d),d);StationSession(game,'T1')
        self.collect(game)
        wrong=next(s for r,s in stations.items() if r!=stage['required_region'])
        walk(game,wrong);before=deepcopy(game.state);facts=evidence_support(d,game.events).facts
        feedback=game.step({'type':'process'})['feedback']
        self.assertEqual(feedback['kind'],'wrong_processing_region')
        self.assertNotIn('capability',feedback);self.assertEqual(game.state,before)
        self.assertEqual(evidence_support(d,game.events).facts,facts)
        self.finish(game,stations[stage['required_region']])
        scored=score_stream(d,game.events,condition='retain');task=scored['tasks'][0]
        self.assertTrue(task['success']);self.assertFalse(scored['stages'][0]['first_process_correct'])
        self.assertEqual((task['processing_attempt_count'],task['successful_processing_count'],task['wrong_region_processing_count']),(2,1,1))
        self.assertEqual(summarize_stream(scored)['all_tasks']['stages']['first_process_accuracy']['numerator'],0)
        self.assertFalse(scored['negative_feedback_sources'])

    def test_unexecuted_second_stage_stays_in_first_process_denominator(self):
        d=deepcopy(self.maps['mongolia']);d['tasks']={'T1':d['tasks']['T1']}
        game=StationGame(map_world(d),d);StationSession(game,'T1');game.step({'type':'abandon'})
        summary=summarize_stream(score_stream(d,game.events,condition='clear'))
        self.assertEqual(summary['all_tasks']['stages']['first_process_accuracy'],{'numerator':0,'denominator':2,'value':0.0})
        self.assertEqual(summary['first_planned_encounters']['requirements'],2)

    def test_capability_transfers_across_regions_without_resetting_encounter_count(self):
        d,base,stations=self.single();regions=list(stations);d['tasks']={}
        for i,zone in enumerate((regions[0],regions[1],regions[1]),1):
            stage={**base,'required_region':zone}
            d['tasks']['T'+str(i)]={'name':'区域计数','start':'C','submit_at':'C',**stage,'stages':[stage],'max_steps':352}
        game=StationGame(map_world(d),d);feedback=[]
        for task,zone in zip(d['tasks'],(regions[0],regions[1],regions[1])):
            initial=StationSession(game,task,feedback_mode='compact').initial
            self.assertIn(d['public']['processing_regions'][zone],initial['text'])
            self.collect(game);feedback.append(self.finish(game,stations[zone]))
        self.assertEqual(feedback[0]['capability'],feedback[1]['capability'])
        scored=score_stream(d,game.events,condition='retain')
        self.assertEqual([s['planned_encounter'] for s in scored['stages']],[1,2,3])
        self.assertTrue(scored['stages'][1]['historical_matching_opportunity'])
        self.assertEqual(scored['stages'][1]['historical_matching_stations'],[stations[regions[1]]])
        summary=summarize_stream(scored)
        self.assertEqual(summary['first_planned_encounters']['requirements'],1)
        self.assertEqual(summary['after_first_planned_encounters']['requirements'],2)
        self.assertEqual(summary['encounter_key'],['required_kind','requirement'])
        self.assertTrue(scored['stages'][1]['cross_region_matching_opportunity'])
        self.assertTrue(scored['stages'][1]['first_process_at_unprocessed_station_of_other_region_known_type'])
        self.assertFalse(scored['stages'][2]['first_process_at_unprocessed_station_of_other_region_known_type'])

    def test_route_candidates_and_physical_bounds_respect_required_regions(self):
        for d in self.maps.values():
            for i,stage in enumerate(d['tasks']['T1']['stages']):
                options=station_options(d,'T1',stage_index=i)
                self.assertEqual(len(options),24)
                self.assertTrue(all(region_matches(d,stage,o['station']) for o in options))
            reference=known_world_route(d,'T1',d['private_worlds'][map_world(d)])
            self.assertTrue(all(region_matches(d,stage,station) for stage,station in zip(d['tasks']['T1']['stages'],reference['stations'])))

    def test_human_design_view_filters_station_choices_by_region(self):
        for design in self.maps.values():
            with tempfile.TemporaryDirectory() as directory:
                service=FieldService(Path(directory),design)
                initial=service.start({});token=initial['instance_id']
                before=deepcopy(service.instances[token]['game'].events)
                detail=service.design_view(token)
                self.assertEqual(len(detail['triggers']),72)
                for task in detail['tasks']:
                    for stage,options in zip(design['tasks'][task['id']]['stages'],task['stage_options']):
                        self.assertEqual(len(options['matching_stations']),2)
                        self.assertTrue(all(region_matches(design,stage,s) for s in options['matching_stations']))
                        self.assertEqual(len(options['options']),24)
                self.assertEqual(service.instances[token]['game'].events,before)

    def test_missing_or_unknown_regional_requirement_is_rejected(self):
        for value in (None,'secret-zone'):
            d=deepcopy(self.maps['andes']);d['tasks']['T1']['stages'][0]['required_region']=value
            d['tasks']['T1']['required_region']=value
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'design.json';path.write_text(json.dumps(d),encoding='utf-8')
                with self.assertRaises(ValueError):load_design(path)

    def test_native_guide_and_public_task_anchor_expose_both_region_requirements(self):
        for d in self.maps.values():
            initial=StationSession(StationGame(map_world(d),d),'T1',feedback_mode='compact').initial
            reminder=initial['text'].splitlines()[0]
            for stage in d['tasks']['T1']['stages']:
                self.assertIn(d['public']['processing_regions'][stage['required_region']],reminder)
                self.assertIn(d['public']['requirements'][stage['requirement']],reminder)
            guide=access_guide('hermes','native',d)
            self.assertIn('区域不符时保留资料、不推进阶段，也不揭示能力',guide)
            self.assertNotIn('无论是否匹配，实际反馈都会说明本站处理类型',guide)
            tool=movement_tool('step',d)
            self.assertIn('区域不符时保留资料、不推进且不揭示能力',tool['description'])
            self.assertIn('survey',tool['parameters']['properties']['action']['enum'])
            self.assertNotIn('inspect',tool['parameters']['properties']['action']['enum'])

if __name__=='__main__':unittest.main()
