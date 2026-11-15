"""Map contracts: distinct routes, dry-land sites, budgets and fixed exposures."""
from collections import Counter
from pathlib import Path
import json
import unittest

from scripts.field_geography import THEMES,geography
from scripts.build_field_maps import FILES, LEGACY_FILES
from memorybenchmark.prototypes.station_capability import load_design

ROOT=Path(__file__).resolve().parents[1]

class FieldGeographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geographies={t:geography(t) for t in THEMES}
        cls.designs={t:load_design(ROOT/'memorybenchmark/data'/(FILES[t]+'.json')) for t in THEMES}

    def test_installed_graphs_match_individually_authored_sources(self):
        signatures=[]
        for theme,geo in self.geographies.items():
            design=self.designs[theme];p=design['public'];normal=p['difficulty']=='Normal'
            self.assertTrue(p['version'].endswith('-v4.0' if theme=='capulin' else '-v3.0'))
            for field in ('locations','edges','view_box'):self.assertEqual(geo[field],p[field],(theme,field))
            checked=geo['geometry_review'];self.assertFalse(checked['unconnected_visual_crossings'],theme)
            self.assertFalse(checked['unapproved_barrier_crossings'],theme)
            self.assertGreaterEqual(checked['minimum_point_separation'],85,theme)
            self.assertGreaterEqual(checked['minimum_station_separation'],85,theme)
            stats=geo['topology'];self.assertTrue(stats['connected'])
            self.assertGreaterEqual(stats['station_degree_histogram'].get(2,0),16 if normal else 6)
            signatures.append((stats['cycle_rank'],tuple(stats['core_branch_degree_histogram'].items()),tuple(stats['station_degree_histogram'].items())))
        self.assertEqual(len(set(signatures)),6,'Route structure must differ beyond names and terrain colours')

    def test_material_order_frequencies_and_declared_budgets_remain_controlled(self):
        for theme,design in self.designs.items():
            original=json.loads((ROOT/'memorybenchmark/data/history/difficulty-v1'/(LEGACY_FILES[theme]+'.json')).read_text(encoding='utf-8'))
            stages=[s for t in design['tasks'].values() for s in t['stages']]
            self.assertEqual(set(Counter(s['target'] for s in stages).values()),{4})
            self.assertEqual(set(Counter(s['required_kind'] for s in stages).values()),{4})
            normal=design['public']['difficulty']=='Normal'
            self.assertEqual(len(design['tasks']),24 if normal else 16)
            self.assertEqual({t['max_steps'] for t in design['tasks'].values()},{168 if normal else 88})
            self.assertEqual(design['native_session_budget']['main_model_calls'],180 if normal else 100)
            self.assertEqual(design['native_session_budget']['final_model_calls'],6)
            self.assertEqual(design['native_session_budget']['effective_wall_seconds'],3600)
            self.assertEqual(design['native_session_budget']['whole_session_transport_retries'],0)
            for key in ('geographic','animal'):
                expected=original['material_selection'].get(key,
                    original['material_selection'].get('common',[])+original['material_selection'].get('special',[]) if key=='geographic' else [])
                self.assertEqual(design['material_selection'][key],expected)
            self.assertEqual(design['material_selection']['human'],[])
            self.assertEqual(design['evaluation']['authoring_geometry_check']['unused_strict_replicas'],[])
            self.assertGreaterEqual(design['evaluation']['authoring_geometry_check']['nearest_match_rate'],.075)
            self.assertLessEqual(design['evaluation']['authoring_geometry_check']['nearest_match_rate'],.175)

    def test_water_crossings_have_different_roles_in_each_landscape(self):
        def components_without_bridges(geo):
            adj={n:set() for n in geo['locations']}
            for a,b,w in geo['edges']:
                if 'bridge' in geo['edge_tags']['|'.join(sorted((a,b)))]:continue
                adj[a].add(b);adj[b].add(a)
            unseen=set(adj);count=0
            while unseen:
                todo=[min(unseen)];seen=set()
                while todo:
                    n=todo.pop()
                    if n in seen:continue
                    seen.add(n);todo.extend(adj[n]-seen)
                unseen-=seen;count+=1
            return count
        self.assertEqual(components_without_bridges(self.geographies['forest']),2)
        self.assertEqual(components_without_bridges(self.geographies['boar']),3)
        self.assertEqual(components_without_bridges(self.geographies['dingo']),1)
        for theme in ('cascade','nessie','dingo'):
            self.assertFalse(self.geographies[theme]['features'].get('bridges'),theme)

    def test_lake_chain_preserves_unavoidable_shared_necks(self):
        geo=self.geographies['cascade']
        for removed in ('N1','N2','N3'):
            adj={n:set() for n in geo['locations'] if n!=removed}
            for a,b,w in geo['edges']:
                if removed not in (a,b):adj[a].add(b);adj[b].add(a)
            todo=['C'];seen=set()
            while todo:
                n=todo.pop()
                if n in seen:continue
                seen.add(n);todo.extend(adj[n]-seen)
            self.assertNotIn('N4',seen,removed)

if __name__=='__main__':unittest.main()
