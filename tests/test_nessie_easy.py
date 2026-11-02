"""Themed-map feasibility, private/public boundary and evidence transfer."""
from collections import Counter
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.analysis import commute_graph
from memorybenchmark.map_catalog import map_detail
from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design, map_world
from memorybenchmark.prototypes.station_experience import experience_opportunities, experience_schedule
from memorybenchmark.prototypes.station_routes import known_world_route, walk
from memorybenchmark.prototypes.station_session import NESSIE_EASY_DESIGN, StationSession, play_human
from scripts.build_nessie_easy_map import build
from scripts.check_easy20_linked import FeedbackSimulation


class NessieEasyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(NESSIE_EASY_DESIGN)
        cls.world = map_world(cls.design)

    def test_reproducible_sparse_map_fixed_types_and_balanced_task_stream(self):
        d=self.design
        self.assertEqual(build(), json.loads(NESSIE_EASY_DESIGN.read_text(encoding='utf-8')))
        self.assertEqual((len(d['public']['locations']),len(d['public']['edges'])),(61,61))
        self.assertEqual(len(d['private_worlds']),576)
        self.assertEqual(len(d['public']['station_types']),8)
        self.assertEqual(list(d['tasks']),[f'T{i}' for i in range(1,21)])
        self.assertEqual(Counter(s['required_kind'] for t in d['tasks'].values() for s in t['stages']),
                         Counter({k:5 for k in d['public']['kinds']}))
        self.assertTrue(all(t['start']==t['submit_at']=='C' and t['max_steps']==88 for t in d['tasks'].values()))
        self.assertEqual(len([s for row in experience_schedule(d) for s in row['stages'] if s['earlier_same_kind_stages']]),32)
        with self.assertRaises(ValueError):map_world(d,'omega_00_00')

    def test_all_twenty_tasks_complete_with_actual_feedback_with_and_without_history(self):
        sim=FeedbackSimulation(self.design)
        for retain in (True,False):
            game=StationGame(self.world,self.design);facts={}
            for task in self.design['tasks']:
                row,new=sim.run(self.world,task,facts if retain else {},runtime=game)
                if retain:facts=new
                self.assertTrue(game.state.success)
                self.assertLessEqual(row['operations'],88)
                graph=commute_graph(game.events,game.task_run_id)
                self.assertEqual(graph['distance'],game.distance)
                self.assertEqual(len(graph['edges']),row['moves'])

    def test_successful_processing_transfers_to_unvisited_same_type_instance(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');walk(game,'P');walk(game,'C1')
        info=game.step({'type':'process'})['feedback']
        self.assertEqual((info['station_type'],info['capability']),('C','wake'))
        game.step({'type':'abandon'})
        game.start_task('T13');walk(game,'U');walk(game,'C2')
        record=experience_opportunities(self.design,game.events,game.task_run_id)['stages'][0]
        self.assertEqual(record['directly_observed_matching_types'],['C'])
        self.assertIn('C2',record['unvisited_matching_stations_of_observed_types'])
        self.assertTrue(record['first_branch_choice']['new_station_of_previously_observed_type'])
        self.assertEqual(record['first_branch_choice']['historical_status'],'known_match')
        self.assertEqual(record['direct_matching_feedback'][0]['task_id'],'T1')

    def test_untouched_failed_task_does_not_confer_an_experience(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');game.step({'type':'abandon'})
        self.assertEqual(len(compatible_worlds(self.design,game.events)),576)
        game.start_task('T13')
        record=experience_opportunities(self.design,game.events,game.task_run_id)['stages'][0]
        self.assertEqual(record['direct_matching_feedback'],[])
        self.assertFalse(record['has_prior_matching_opportunity'])

    def test_wrong_station_preserves_sample_and_records_feedback(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');walk(game,'P');walk(game,'A1')
        info=game.step({'type':'process'})['feedback']
        self.assertEqual(info['result'],'unsupported')
        self.assertTrue(game.state.raw)
        self.assertEqual(info['capability'],'reeds')
        self.assertLess(len(compatible_worlds(self.design,game.events)),576)

    def test_next_session_gets_public_geography_without_old_answers_or_future_tasks(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');walk(game,'A1');game.step({'type':'inspect'});game.step({'type':'abandon'})
        next_session=StationSession(game,'T2')
        clean=StationSession(StationGame(self.world,self.design),'T2')
        self.assertEqual(next_session.initial,clean.initial)
        text=json.dumps(next_session.initial,ensure_ascii=False)
        for forbidden in ('private_worlds','fixed_world','omega_','provenance','forestryandland','Foyers','T20','station_information'):
            self.assertNotIn(forbidden,text)
        self.assertEqual(len(next_session.initial['observation']['environment']['locations']),61)
        for command in ('design','next_task','world'):
            self.assertIn('error',next_session.dispatch({'command':command}))

    def test_reference_routes_finish_at_camp_after_ordered_collection_and_processing(self):
        assignment=self.design['private_worlds'][self.world]
        for task_id,task in self.design['tasks'].items():
            reference=known_world_route(self.design,task_id,assignment)
            game=StationGame(self.world,self.design);game.start_task(task_id)
            for stage,station in zip(task['stages'],reference['stations']):
                walk(game,stage['target'])
                self.assertNotIn({'type':'submit'},game.observation()['available_actions'])
                walk(game,station);game.step({'type':'process'})
            self.assertFalse(game.done)
            self.assertNotIn({'type':'submit'},game.observation()['available_actions'])
            walk(game,'C');game.step({'type':'submit'})
            self.assertTrue(game.state.success)
            self.assertEqual(game.distance,reference['distance'])

    def test_human_design_view_is_explicit_and_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            service=FieldService(Path(tmp),self.design);data=service.start({});token=data['instance_id']
            game=service.instances[token]['game'];before=deepcopy(game.events)
            detail=service.design_view(token)
            self.assertEqual(len(detail['triggers']),16)
            self.assertEqual(len(detail['tasks']),20)
            self.assertEqual(detail['name'],'尼斯湖水怪')
            self.assertEqual(game.events,before)
            self.assertNotIn('capabilities',data)
            geography=map_detail('nessie-easy')
            self.assertEqual((geography['terrain'],geography['node_count']),('nessie',61))
            self.assertEqual(len(geography['trigger_nodes']),16)
            self.assertNotIn('capabilities',geography)

    def test_current_map_roundtrips_through_shared_mcp_transport(self):
        from memorybenchmark.mcp_game import MCPGameClient,SDK_VERSION
        try:
            installed=version('mcp')
        except PackageNotFoundError:
            self.skipTest('install the mcp extra for SDK transport checks')
        if installed!=SDK_VERSION:self.skipTest('SDK pin not installed')
        session=StationSession(StationGame(self.world,self.design),'T1')
        with MCPGameClient(session.dispatch) as client:
            self.assertEqual(client({'command':'read'}),session.dispatch({'command':'read'}))
            result=client({'command':'action','request_id':'first','expected_revision':0,
                           'action':{'type':'move','target':'NC'}})
            self.assertEqual(result['observation']['location'],'NC')
            self.assertNotIn('private_worlds',json.dumps(result))

    def test_terminal_moves_accept_displayed_lowercase_transit_ids(self):
        game=StationGame(self.world,self.design)
        with patch('builtins.input',side_effect=['move nc','move nw','move a1p1','quit']),redirect_stdout(io.StringIO()):
            play_human(game,['T1'])
        self.assertEqual(game.state.position,'a1p1')
        self.assertEqual(game.steps,3)


if __name__=='__main__':unittest.main()
