"""New map mechanics, evidence opportunities, anonymity and HTTP integration."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from memorybenchmark.materials import easy_material_preset, select_easy_materials
from memorybenchmark.map_catalog import map_detail
from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_experience import experience_opportunities
from memorybenchmark.prototypes.station_pilot import access_guide, movement_tool
from memorybenchmark.prototypes.station_routes import walk
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.server import make_server
from scripts.build_easy_maps import BUILDERS, DESIGN_PATHS
from scripts.check_easy_maps import FORBIDDEN, replica_choices, topology
from scripts.check_station_capability import trace_graph


ROOT = Path(__file__).resolve().parents[1]


class EasyMapsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs = {key: load_design(DESIGN_PATHS[key]) for key in BUILDERS}

    def test_distinct_topologies_with_reproducible_fixed_six_plus_two_materials(self):
        self.assertEqual(topology(self.designs['forest'])['independent_cycles'], 3)
        self.assertEqual(topology(self.designs['forest'])['core_articulation_nodes'], [])
        self.assertEqual(topology(self.designs['cascade'])['independent_cycles'], 4)
        self.assertIn('N2', topology(self.designs['cascade'])['core_articulation_nodes'])
        for key, design in self.designs.items():
            self.assertEqual(BUILDERS[key](), json.loads(DESIGN_PATHS[key].read_text(encoding='utf-8')))
            self.assertEqual(len(design['private_worlds']), 40320)
            self.assertEqual(len(design['material_selection']['common']), 6)
            self.assertEqual(len(design['material_selection']['special']), 2)
            self.assertEqual(len(design['tasks']), 20)
        self.assertNotEqual(set(self.designs['forest']['public']['kinds']), set(self.designs['cascade']['public']['kinds']))

    def test_each_physical_replica_has_a_strict_distance_advantage_in_the_stream(self):
        for key, design in self.designs.items():
            for stations in replica_choices(design).values():
                for station, counts in stations.items():
                    self.assertGreater(counts['strictly_preferred'], 0, (key, station, counts))

    def test_material_authoring_rejects_wrong_theme_duplicates_and_wrong_counts(self):
        common = ['profile', 'elevation', 'bearing', 'vegetation', 'soil', 'drainage']
        with self.assertRaises(ValueError): select_easy_materials('forest', common, ['lake_sonar', 'lake_sighting'])
        with self.assertRaises(ValueError): select_easy_materials('forest', common, ['salmon_habitat', 'salmon_habitat'])
        with self.assertRaises(ValueError): select_easy_materials('forest', common[:-1], ['redwood_community', 'salmon_habitat'])
        self.assertEqual(easy_material_preset('forest'), easy_material_preset('forest'))

    def test_agent_inputs_are_anonymous_and_reset_without_answers(self):
        for design in self.designs.values():
            world = map_world(design); game = StationGame(world, design)
            session = StationSession(game, 'T1', feedback_mode='compact')
            for response in (session.initial, session.dispatch({'command': 'read'})):
                text = json.dumps(response, ensure_ascii=False).lower()
                self.assertFalse(any(token in text for token in FORBIDDEN))
                self.assertNotIn('material_selection', text)
            for agent in ('ga', 'hermes'):
                self.assertFalse(any(token in access_guide(agent, 'native', design).lower() for token in FORBIDDEN))
                verbs = movement_tool('step', design)['parameters']['properties']['action']['enum']
                self.assertIn('survey', verbs); self.assertNotIn('inspect', verbs)
            walk(game, 'P'); game.step({'type': 'survey'})
            station = next(s for s in design['public']['station_types']['A']['stations'])
            walk(game, station); game.step({'type': 'process'}); game.step({'type': 'abandon'})
            inherited = StationSession(game, 'T2', feedback_mode='compact')
            fresh = StationSession(StationGame(world, design), 'T2', feedback_mode='compact')
            self.assertEqual(inherited.initial, fresh.initial)

    def test_actual_failure_feedback_transfers_to_unvisited_replica_and_enters_graph(self):
        for design in self.designs.values():
            world = map_world(design); assignment = design['private_worlds'][world]
            game = StationGame(world, design); game.start_task('T1')
            walk(game, 'P'); game.step({'type': 'survey'}); walk(game, 'A1')
            info = game.step({'type': 'process'})['feedback']
            self.assertEqual(info['result'], 'unsupported')
            source_graph = trace_graph(game)
            self.assertTrue(any(e['feedback'].get('result') == 'unsupported' for e in source_graph['node_events']))
            self.assertEqual(sum(e['action']['type'] == 'survey' for e in source_graph['node_events']), 1)
            game.step({'type': 'abandon'})
            task_id, index = next((task_id, i) for task_id, task in design['tasks'].items() if task_id != 'T1'
                                  for i, stage in enumerate(task['stages']) if stage['required_kind'] == assignment['A1'])
            game.start_task(task_id)
            record = experience_opportunities(design, game.events, game.task_run_id)['stages'][index]
            self.assertIn('A2', record['unvisited_matching_stations_of_observed_types'])
            self.assertEqual(record['direct_matching_feedback'][0]['result'], 'unsupported')
            self.assertTrue(record['has_prior_matching_opportunity'])
            self.assertNotIn('station_information', json.dumps(game.observation()))
            game.step({'type': 'abandon'})
            prior_graph = trace_graph(game)
            self.assertEqual(prior_graph['distance'], 0)

    def test_configured_game_does_not_depend_on_live_authoring_catalog(self):
        from unittest.mock import patch
        with patch('memorybenchmark.materials._catalog', side_effect=AssertionError('runtime catalog read')):
            for key in BUILDERS:
                loaded = load_design(DESIGN_PATHS[key])
                self.assertEqual(loaded['public']['difficulty'], 'Easy')

    def test_web_lists_both_maps_and_serves_their_real_terrain_and_design_view(self):
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(port=0, log_root=Path(directory))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for key, terrain in (('forest', 'forest-valley'), ('cascade', 'cascade-lakes')):
                    detail = map_detail(key+'-easy')
                    self.assertTrue(detail['station_game']); self.assertEqual(detail['terrain'], terrain)
                    with urlopen(base+'/'+terrain+'-terrain.svg') as response:
                        self.assertIn('<svg', response.read().decode())
                    with urlopen(Request(base+'/api/field/start?map='+key+'-easy', data=b'{}', headers={'Content-Type': 'application/json'})) as response:
                        initial = json.load(response)
                    self.assertNotIn('capabilities', initial)
                    self.assertFalse(any(token in json.dumps(initial['observation'], ensure_ascii=False).lower() for token in FORBIDDEN))
                    with urlopen(base+'/api/field/design?map='+key+'-easy&instance_id='+initial['instance_id']) as response:
                        self.assertEqual(len(json.load(response)['triggers']), 16)
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
