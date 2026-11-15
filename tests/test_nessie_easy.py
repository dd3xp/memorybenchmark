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
from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design, map_world
from memorybenchmark.prototypes.station_experience import experience_opportunities, experience_schedule
from memorybenchmark.prototypes.station_routes import known_world_route, shortest_route, station_options, walk
from memorybenchmark.prototypes.station_pilot import access_guide, movement_tool
from memorybenchmark.prototypes.station_session import NESSIE_EASY_DESIGN, StationSession, play_human
from scripts.build_nessie_easy_map import build
from scripts.build_easy20_reuse_map import build as reference_map
from scripts.check_easy20_linked import FeedbackSimulation
from scripts.check_station_capability import trace_graph


class NessieEasyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(NESSIE_EASY_DESIGN)
        cls.world = map_world(cls.design)

    def test_reproducible_sparse_map_fixed_types_and_balanced_task_stream(self):
        d=self.design
        self.assertEqual(build(), json.loads(NESSIE_EASY_DESIGN.read_text(encoding='utf-8')))
        self.assertEqual((len(d['public']['locations']),len(d['public']['edges'])),(61,61))
        self.assertEqual(len(d['private_worlds']),40320)
        self.assertNotIn('capability_groups',d['public'])
        self.assertEqual(len(d['public']['station_types']),8)
        self.assertEqual(list(d['tasks']),[f'T{i}' for i in range(1,21)])
        self.assertEqual(Counter(s['required_kind'] for t in d['tasks'].values() for s in t['stages']),
                         Counter({k:5 for k in d['public']['kinds']}))
        self.assertTrue(all(t['start']==t['submit_at']=='C' and t['max_steps']==88 for t in d['tasks'].values()))
        self.assertEqual(len([s for row in experience_schedule(d) for s in row['stages'] if s['earlier_same_kind_stages']]),32)
        with self.assertRaises(ValueError):map_world(d,'omega_00_00')

    def test_original_survey_plan_is_preserved_with_only_one_themed_station_type(self):
        reference=reference_map()
        self.assertEqual([[(s['target']) for s in task['stages']] for task in self.design['tasks'].values()],
                         [[s['target'] for s in task['stages']] for task in reference['tasks'].values()])
        self.assertEqual(len(self.design['material_selection']['common']),6)
        self.assertEqual(set(self.design['material_selection']['special']),{'lake_sonar','lake_sighting'})
        themed={id_:place for id_,place in self.design['public']['locations'].items()
                if '水怪' in place['name']}
        self.assertEqual(set(themed),{'H1','H2'})
        self.assertEqual({place['station_type'] for place in themed.values()},{'H'})
        self.assertEqual(self.design['public']['vocabulary']['process'],'处理')

    def test_all_types_can_initially_support_every_material_without_group_inference(self):
        worlds=self.design['private_worlds']
        for type_id,group in self.design['public']['station_types'].items():
            self.assertEqual({w[group['stations'][0]] for w in worlds.values()},set(self.design['public']['kinds']))
        self.assertTrue(all(row['publicly_possible'] for row in station_options(self.design,'T1')))
        # Knowing A/B/C must not identify D by the old four-type restriction.
        prior=[{'delivered':{'feedback':{'kind':'station_information','station':s,'capability':kind}}}
               for s,kind in [('A1','vegetation'),('B1','lithology'),('C1','profile')]]
        possible=compatible_worlds(self.design,prior)
        self.assertEqual(len(possible),120)
        self.assertEqual({worlds[w]['D1'] for w in possible},
                         set(self.design['public']['kinds'])-{'vegetation','lithology','profile'})
        game=StationGame(self.world,self.design);session=StationSession(game,'T1')
        self.assertNotIn('capability_groups',session.initial['observation']['environment'])
        for old_rule in ('A/B/C/D','E/F/G/H','每个站网'):
            self.assertNotIn(old_rule,json.dumps(session.initial,ensure_ascii=False))
        analysis=analyze_trace(self.design,game.events,game.task_run_id,exact_references=False)
        self.assertEqual(analysis['prior_compatible_world_count'],40320)
        self.assertIn('station_decisions',analysis)

    def test_ungrouping_preserves_the_fixed_map_and_historical_protocol(self):
        historical=load_design(NESSIE_EASY_DESIGN.parent/'nessie_easy20_1_3.json')
        self.assertEqual(len(historical['private_worlds']),576)
        ungrouped=load_design(NESSIE_EASY_DESIGN.parent/'nessie_easy20_1_4.json')
        self.assertEqual(ungrouped['private_worlds'][map_world(ungrouped)],historical['private_worlds'][map_world(historical)])
        self.assertEqual(ungrouped['tasks'],historical['tasks'])
        for key in ('locations','edges','station_types','station_query_enabled','manual_survey_required'):
            self.assertEqual(self.design['public'][key],historical['public'][key])

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
        game.start_task('T1');walk(game,'P');game.step({'type':'survey'});walk(game,'C1')
        info=game.step({'type':'process'})['feedback']
        self.assertEqual((info['station_type'],info['capability']),('C','profile'))
        game.step({'type':'abandon'})
        game.start_task('T13');walk(game,'U');game.step({'type':'survey'});walk(game,'C2')
        record=experience_opportunities(self.design,game.events,game.task_run_id)['stages'][0]
        self.assertEqual(record['directly_observed_matching_types'],['C'])
        self.assertIn('C2',record['unvisited_matching_stations_of_observed_types'])
        self.assertTrue(record['first_branch_choice']['new_station_of_previously_observed_type'])
        self.assertEqual(record['first_branch_choice']['historical_status'],'known_match')
        self.assertEqual(record['direct_matching_feedback'][0]['task_id'],'T1')

    def test_untouched_failed_task_does_not_confer_an_experience(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');game.step({'type':'abandon'})
        self.assertEqual(len(compatible_worlds(self.design,game.events)),40320)
        game.start_task('T13')
        record=experience_opportunities(self.design,game.events,game.task_run_id)['stages'][0]
        self.assertEqual(record['direct_matching_feedback'],[])
        self.assertFalse(record['has_prior_matching_opportunity'])

    def test_wrong_station_preserves_sample_and_records_feedback(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');walk(game,'P');game.step({'type':'survey'});walk(game,'A1')
        info=game.step({'type':'process'})['feedback']
        self.assertEqual(info['result'],'unsupported')
        self.assertTrue(game.state.raw)
        self.assertEqual(info['capability'],'vegetation')
        self.assertEqual(len(compatible_worlds(self.design,game.events)),5040)

    def test_no_query_or_processing_before_collection_and_no_passive_capability(self):
        game=StationGame(self.world,self.design)
        session=StationSession(game,'T1');walk(game,'A1')
        self.assertEqual(self.design['public']['version'],'easy-01-v1.5')
        self.assertFalse(self.design['public']['station_query_enabled'])
        self.assertFalse(any(a['type'] in ('inspect','process') for a in game.observation()['available_actions']))
        self.assertEqual(game.events[-1]['delivered']['feedback']['kind'],'arrived')
        self.assertEqual(len(compatible_worlds(self.design,game.events)),40320)
        before=deepcopy(game.events)
        result=session.dispatch({'command':'action','request_id':'query-bypass','action':{'type':'inspect'}})
        self.assertEqual(result['error'],'invalid_action')
        self.assertEqual(game.events,before)
        self.assertNotIn('capability',session.dispatch({'command':'read'})['feedback'])
        walk(game,'P');game.step({'type':'survey'});walk(game,'A1')
        self.assertNotIn({'type':'inspect'},game.observation()['available_actions'])
        self.assertIn({'type':'process'},game.observation()['available_actions'])

    def test_survey_requires_the_current_target_and_cannot_be_repeated(self):
        game=StationGame(self.world,self.design);game.start_task('T1')
        walk(game,'R')
        self.assertFalse(game.state.raw)
        self.assertNotIn({'type':'survey'},game.observation()['available_actions'])
        with self.assertRaises(ValueError):game.step({'type':'survey'})
        walk(game,'P')
        self.assertFalse(game.state.raw)
        self.assertFalse(game.events[-1]['delivered']['feedback']['raw_collected'])
        before=trace_graph(game)
        operations,distance=game.steps,game.distance
        game.step({'type':'survey'})
        self.assertTrue(game.state.raw)
        self.assertEqual(game.steps,operations+1)
        self.assertEqual(game.distance,distance)
        self.assertTrue(game.events[-1]['delivered']['feedback']['raw_collected'])
        graph=trace_graph(game)
        self.assertEqual(graph['edges'],before['edges'])
        self.assertEqual(graph['node_events'][-1]['action'],{'type':'survey'})
        events=deepcopy(game.events)
        with self.assertRaises(ValueError):game.step({'type':'survey'})
        self.assertEqual(game.events,events)
        walk(game,'C1');game.step({'type':'process'})
        self.assertEqual(game.state.stage,1)
        self.assertFalse(game.state.raw)
        walk(game,'R');self.assertFalse(game.state.raw)
        game.step({'type':'survey'});self.assertTrue(game.state.raw)

    def test_survey_is_available_through_the_adapter_with_exact_retry(self):
        game=StationGame(self.world,self.design)
        session=StationSession(game,'T1',feedback_mode='compact')
        for location in shortest_route(self.design,'C','P')[0][1:]:
            response=session.dispatch({'command':'action','request_id':'move-'+location,
                                       'action':{'type':'move','target':location}})
        self.assertIn('survey',response['text'])
        self.assertFalse(response['observation']['raw'])
        request={'command':'action','request_id':'survey-once','expected_revision':session.revision,
                 'action':{'type':'survey'}}
        response=session.dispatch(request)
        self.assertEqual(response['feedback']['kind'],'surveyed')
        self.assertTrue(response['observation']['raw'])
        self.assertIn('勘探完成',response['text'])
        count=len(game.events)
        self.assertEqual(session.dispatch(request),response)
        self.assertEqual(len(game.events),count)

    def test_finished_sample_cannot_inflate_submission_accuracy_by_reprocessing(self):
        game=StationGame(self.world,self.design);game.start_task('T1')
        walk(game,'P');game.step({'type':'survey'});walk(game,'C1');game.step({'type':'process'})
        walk(game,'R');game.step({'type':'survey'});walk(game,'H1');game.step({'type':'process'})
        self.assertTrue(game.state.processed)
        self.assertNotIn({'type':'process'},game.observation()['available_actions'])
        before=deepcopy(game.events)
        with self.assertRaises(ValueError):game.step({'type':'process'})
        self.assertEqual(game.events,before)
        walk(game,'C')
        self.assertFalse(game.done)
        game.step({'type':'submit'});self.assertTrue(game.state.success)

    def test_native_interfaces_only_offer_submission_and_keep_legacy_queries(self):
        for agent in ('ga','hermes'):
            for access in ('native','bridge'):
                guide=access_guide(agent,access,self.design)
                self.assertNotIn('inspect',guide)
                self.assertIn('不提供独立查询',guide)
                self.assertIn('process',guide)
                self.assertIn('survey',guide)
                self.assertNotIn('自动采集',guide)
        tool=movement_tool('step',self.design)
        self.assertNotIn('inspect',tool['parameters']['properties']['action']['enum'])
        self.assertNotIn('inspect',tool['description'])
        self.assertIn('survey',tool['parameters']['properties']['action']['enum'])
        self.assertNotIn('自动采集',tool['description'])
        historical=load_design(NESSIE_EASY_DESIGN.parent/'nessie_easy20_1_1.json')
        old=StationGame(map_world(historical),historical);old.start_task('T1');walk(old,'A1')
        self.assertIn({'type':'inspect'},old.observation()['available_actions'])
        self.assertIn('inspect',movement_tool('step',historical)['parameters']['properties']['action']['enum'])
        self.assertEqual(old.step({'type':'inspect'})['feedback']['capability'],'vegetation')
        previous=load_design(NESSIE_EASY_DESIGN.parent/'nessie_easy20_1_2.json')
        old=StationGame(map_world(previous),previous);old.start_task('T1');walk(old,'P')
        self.assertTrue(old.state.raw)
        self.assertNotIn('survey',movement_tool('step',previous)['parameters']['properties']['action']['enum'])

    def test_next_session_gets_public_geography_without_old_answers_or_future_tasks(self):
        game=StationGame(self.world,self.design)
        game.start_task('T1');walk(game,'P');game.step({'type':'survey'});walk(game,'A1');game.step({'type':'process'});game.step({'type':'abandon'})
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
                game.step({'type':'survey'})
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
            self.assertEqual(detail['name'],'暮湾长湖')
            self.assertEqual(game.events,before)
            self.assertNotIn('capabilities',data)
            with self.assertRaises(ValueError):
                map_detail('nessie-easy')

    def test_current_map_roundtrips_through_shared_mcp_transport(self):
        from memorybenchmark.mcp_game import MCPGameClient,SDK_VERSION
        try:
            installed=version('mcp')
        except PackageNotFoundError:
            self.skipTest('install the mcp extra for SDK transport checks')
        if installed!=SDK_VERSION:self.skipTest('SDK pin not installed')
        session=StationSession(StationGame(self.world,self.design),'T1')
        with MCPGameClient(session.dispatch,definition=movement_tool('step',self.design),target_actions=('move',)) as client:
            self.assertEqual(client({'command':'read'}),session.dispatch({'command':'read'}))
            result=client({'command':'action','request_id':'first','expected_revision':0,
                           'action':{'type':'move','target':'NC'}})
            self.assertEqual(result['observation']['location'],'NC')
            self.assertNotIn('private_worlds',json.dumps(result))
            for location in shortest_route(self.design,'NC','P')[0][1:]:
                result=client({'command':'action','request_id':'mcp-move-'+location,
                               'action':{'type':'move','target':location}})
            self.assertFalse(result['observation']['raw'])
            result=client({'command':'action','request_id':'mcp-survey','action':{'type':'survey'}})
            self.assertEqual(result['feedback']['kind'],'surveyed')
            self.assertTrue(result['observation']['raw'])

    def test_terminal_moves_accept_displayed_lowercase_transit_ids(self):
        game=StationGame(self.world,self.design)
        with patch('builtins.input',side_effect=['move nc','move nw','move a1p1','quit']),redirect_stdout(io.StringIO()):
            play_human(game,['T1'])
        self.assertEqual(game.state.position,'a1p1')
        self.assertEqual(game.steps,3)


if __name__=='__main__':unittest.main()
