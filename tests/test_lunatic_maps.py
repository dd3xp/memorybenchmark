"""Long-gap context selection, native budgets and cross-condition isolation."""
from collections import Counter
from pathlib import Path
import json,unittest
from copy import deepcopy
from scripts.lunatic_geography import THEMES,geography
from scripts.build_lunatic_maps import stream_diagnostics
from memorybenchmark.prototypes.station_capability import load_design,StationGame,map_world
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_knowledge import evidence_support

ROOT=Path(__file__).resolve().parents[1]
class LunaticMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.designs={t:load_design(ROOT/'memorybenchmark/data'/(t+'_lunatic64.json')) for t in THEMES}

    def test_long_balanced_streams_keep_two_requirements_distinct(self):
        for theme,d in self.designs.items():
            p=d['public'];self.assertEqual(p['difficulty'],'Lunatic')
            self.assertEqual((len(p['kinds']),len(p['station_types']),len(p['requirements']),len(d['tasks'])),(16,24,2,64))
            self.assertEqual(len({n['name'] for n in p['locations'].values() if n['kind']=='survey'}),64)
            stats=stream_diagnostics(d['tasks']);self.assertGreaterEqual(stats['minimum_repeat_gap_tasks'],12)
            self.assertEqual(set(stats['context_exposures'].values()),{4});self.assertEqual(stats['repeat_count'],96)
            self.assertEqual(set(Counter(s['target'] for t in d['tasks'].values() for s in t['stages']).values()),{2})
            self.assertEqual({t['max_steps'] for t in d['tasks'].values()},{352})
            self.assertEqual(d['native_session_budget']['main_model_calls'],400)
            self.assertEqual(d['native_session_budget']['whole_session_transport_retries'],0)
            for k in p['kinds']:
                sets=[frozenset(t for t,v in d['private_station_capabilities'].items() if k in v[r]) for r in p['requirements']]
                self.assertEqual(len(set(sets)),2);self.assertEqual(set(map(len,sets)),{2})

    def test_three_authored_geographies_are_distinct_and_geometrically_valid(self):
        signatures=[]
        for theme,d in self.designs.items():
            geo=geography(theme)
            for k in ('locations','edges','view_box'):self.assertEqual(geo[k],d['public'][k])
            r=geo['geometry_review'];self.assertFalse(r['unconnected_visual_crossings']);self.assertFalse(r['unapproved_barrier_crossings'])
            self.assertGreaterEqual(r['minimum_point_separation'],85)
            self.assertFalse(d['evaluation']['authoring_geometry_check']['unused_strict_replicas'])
            signatures.append((geo['topology']['cycle_rank'],tuple(geo['topology']['core_branch_degree_histogram'].items())))
        self.assertEqual(len(set(signatures)),3)

    def test_each_requirement_delivers_only_its_current_capability(self):
        for d in self.designs.values():
            self.assertEqual(set(d['public']['requirements']),{'catalogue','verify'})
            for requirement in ('catalogue','verify'):
                task_id=next(t for t,v in d['tasks'].items() if v['stages'][0]['requirement']==requirement)
                game=StationGame(map_world(d),d);initial=StationSession(game,task_id,feedback_mode='compact').initial
                encoded=json.dumps(initial,ensure_ascii=False)
                self.assertNotIn('private_station_capabilities',encoded);self.assertNotIn('https://',encoded)
                t=game.task;walk(game,t['target']);game.step({'type':'survey'})
                typ=next(k for k,v in d['private_station_capabilities'].items() if t['required_kind'] in v[requirement])
                station=next(s for s in d['public']['station_types'][typ]['stations'] if d['public']['locations'][s]['region_category']==t['required_region'])
                walk(game,station);delivered=game.step({'type':'process'})['feedback']
                self.assertEqual(delivered['result'],'processed');self.assertEqual(delivered['requirement'],requirement)
                self.assertEqual(delivered['capability'],d['private_station_capabilities'][typ][requirement])
                facts=evidence_support(d,game.events).facts
                self.assertEqual({key[1] for key,value in facts},{requirement})
                game.step({'type':'abandon'})
                fresh=StationSession(game,'T64').initial
                self.assertEqual(fresh,StationSession(StationGame(map_world(d),d),'T64').initial)

if __name__=='__main__':unittest.main()
