"""Normal set capabilities, honest evidence support, frozen replay and web play."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from memorybenchmark.map_catalog import map_detail, station_design
from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world, compatible_worlds, ReferencePlanner
from memorybenchmark.prototypes.station_knowledge import evidence_support, matching_stations, supports, support_count
from memorybenchmark.prototypes.station_routes import known_world_route, walk
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_experience import experience_opportunities
from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_metrics import score_stream, summarize_stream
from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.server import make_server


class DifficultyMapTests(unittest.TestCase):
    def test_normal_call_budget_reaches_shared_native_executor(self):
        from unittest.mock import patch
        from memorybenchmark.agent_sessions import WorkerSessions
        from memorybenchmark.prototypes.station_pilot import StationNativeSessions
        with patch('memorybenchmark.agent_sessions.require_mcp'):
            for agent in ('ga', 'hermes'):
                session = StationNativeSessions(Path('source'), Path('support'), None,
                    agent=agent, model_alias='test', max_turns=180, final_turns=6)
                self.assertEqual(session.max_turns, 180)
                self.assertEqual(session.final_turns, 6)
        with self.assertRaises(ValueError):
            WorkerSessions(Path('source'), Path('support'), None,
                model_alias='test', max_turns=401)

    @classmethod
    def setUpClass(cls):
        cls.designs={key:load_design(station_design(key)) for key in ('nessie-normal','dingo-normal','boar-normal')}

    def test_new_map_counts_and_no_dead_replicas_or_geographic_guess_shortcut(self):
        for key,design in self.designs.items():
            p=design['public'];self.assertEqual(p['difficulty'],'Normal')
            points=[(n['x'],n['y']) for n in p['locations'].values()]
            self.assertEqual(len(points),len(set(points)))
            self.assertEqual(len(p['kinds']),12);self.assertEqual(len(p['station_types']),16)
            self.assertEqual(len(design['tasks']),24)
            self.assertEqual(len(design['material_selection']['geographic']),8)
            self.assertEqual(len(design['material_selection']['animal']),4)
            stats=design['evaluation']['authoring_geometry_check']
            self.assertEqual(stats['unused_strict_replicas'],[])
            self.assertGreaterEqual(stats['nearest_match_rate'],.075)
            self.assertLessEqual(stats['nearest_match_rate'],.175)
            self.assertEqual(map_detail(key)['difficulty'],'Normal')

    def test_runtime_fixture_is_never_treated_as_full_agent_knowledge(self):
        for design in self.designs.values():
            support=evidence_support(design,[])
            self.assertIsNone(support_count(support))
            self.assertTrue(all(not matching_stations(design,support,k) for k in design['public']['kinds']))
            with self.assertRaises(ValueError):compatible_worlds(design,[])
            with self.assertRaises(ValueError):ReferencePlanner(design,'T1')

    def test_failed_process_delivers_full_set_and_transfers_only_observed_type(self):
        for design in self.designs.values():
            world=map_world(design);assignment=design['private_worlds'][world]
            game=StationGame(world,design);session=StationSession(game,'T1',feedback_mode='compact')
            kind=game.task['required_kind']
            station=next(s for s,v in assignment.items() if len(v)==2 and not supports(v,kind))
            walk(game,game.task['target']);game.step({'type':'survey'});walk(game,station)
            response=session.dispatch({'command':'action','action':{'type':'process'},'request_id':'wrong'})
            self.assertEqual(response['feedback']['result'],'unsupported');self.assertTrue(game.state.raw)
            self.assertEqual(len(response['feedback']['capability']),2)
            for k in assignment[station]:self.assertIn(design['public']['kinds'][k],response['text'])
            support=evidence_support(design,game.events)
            for k in assignment[station]:
                self.assertEqual(set(matching_stations(design,support,k)),set(design['public']['station_types'][station[0]]['stations']))
            game.step({'type':'abandon'});game.start_task('T2')
            analysis=analyze_trace(design,game.events,game.task_run_id,exact_references=False)
            self.assertIsNone(analysis['prior_compatible_world_count'])
            score=score_stream(design,game.events,condition='retain')
            self.assertIsNone(summarize_stream(score)['all_tasks']['totals']['new_historical_bits'])

    def test_both_valid_types_process_and_wrong_type_does_not_progress(self):
        for design in self.designs.values():
            world=map_world(design);assignment=design['private_worlds'][world];task=design['tasks']['T1']
            matching=[s for s,v in assignment.items() if supports(v,task['required_kind'])]
            self.assertEqual(len(matching),4)
            for station in matching:
                game=StationGame(world,design);game.start_task('T1')
                walk(game,task['target']);game.step({'type':'survey'});walk(game,station)
                response=game.step({'type':'process'})
                self.assertEqual(response['feedback']['result'],'processed');self.assertEqual(game.state.stage,1)

    def test_frozen_design_reloads_and_rejects_changed_runtime_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'design.json'
            for design in self.designs.values():
                path.write_text(json.dumps(design,ensure_ascii=False),encoding='utf-8')
                loaded=load_design(path);self.assertEqual(loaded,design)
                changed=deepcopy(design);world=map_world(changed)
                changed['private_worlds'][world]['A1']=['not_a_material']
                path.write_text(json.dumps(changed),encoding='utf-8')
                with self.assertRaises(ValueError):load_design(path)

    def test_read_and_new_session_have_no_historical_capabilities(self):
        for design in self.designs.values():
            game=StationGame(map_world(design),design);s=StationSession(game,'T1')
            before=s.initial;walk(game,game.task['target']);game.step({'type':'survey'});walk(game,'A1');game.step({'type':'process'});game.step({'type':'abandon'})
            reused=StationSession(game,'T2').initial
            fresh=StationSession(StationGame(map_world(design),design),'T2').initial
            self.assertEqual(reused,fresh)
            self.assertNotIn('private_station_capabilities',json.dumps(before))

    def test_real_mcp_returns_capability_sets_without_exposing_fixture(self):
        from importlib.metadata import version, PackageNotFoundError
        from memorybenchmark.mcp_game import MCPGameClient, SDK_VERSION
        from memorybenchmark.prototypes.station_pilot import movement_tool
        try: installed=version('mcp')
        except PackageNotFoundError: installed=None
        if installed!=SDK_VERSION:self.skipTest('MCP SDK extra unavailable')
        design=self.designs['boar-normal'];game=StationGame(map_world(design),design)
        session=StationSession(game,'T1',feedback_mode='compact')
        assignment=design['private_worlds'][map_world(design)]
        station=next(s for s,v in assignment.items() if len(v)==2)
        walk(game,game.task['target']);game.step({'type':'survey'});walk(game,station)
        with MCPGameClient(session.dispatch,definition=movement_tool('step',design),target_actions=('move',)) as client:
            result=client({'command':'action','request_id':'normal-process','action':{'type':'process'}})
            self.assertEqual(result['feedback']['capability'],assignment[station])
            self.assertNotIn('private_station_capabilities',json.dumps(result))

    def test_normal_native_budget_is_frozen_without_model_calls(self):
        from unittest.mock import patch, Mock
        from memorybenchmark.prototypes.station_independent import initialize
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'native.tar';archive.write_bytes(b'test fixture')
            adapter=Mock();adapter.prepare.side_effect=lambda archive,output:(output/'baseline').mkdir()
            with patch('memorybenchmark.prototypes.station_independent.load_adapter',return_value=adapter):
                report=initialize(root/'run',archive,agent='hermes',condition='clear',design_path=station_design('boar-normal'))
            self.assertEqual(report['max_turns'],180)
            self.assertEqual(len(report['tasks']),24)
            self.assertEqual(report['movement_mode'],'step')
            self.assertEqual(report['action_policy'],'single')
            loaded=load_design(root/'run'/'design.json')
            self.assertEqual(loaded['design_id'],'normal-03-v3.0')

    def test_http_real_play_and_explicit_design_handle_capability_lists(self):
        with tempfile.TemporaryDirectory() as directory:
            server=make_server(port=0,log_root=Path(directory));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                for key in ('capulin-easy','forest-easy','nessie-normal','dingo-normal','boar-normal'):
                    with urlopen(Request(base+'/api/field/start?map='+key,data=b'{}',headers={'Content-Type':'application/json'})) as response:
                        data=json.load(response)
                    self.assertNotIn('capabilities',data)
                    with urlopen(base+'/api/field/design?map='+key+'&instance_id='+data['instance_id']) as response:
                        detail=json.load(response)
                    expected=32 if key.endswith('normal') else 16
                    self.assertEqual(len(detail['triggers']),expected)
                    self.assertTrue(detail['tasks'][0]['matching_stations'])
                    terrain=data['observation']['environment']['terrain']
                    with urlopen(base+'/'+terrain+'-terrain.svg') as response:self.assertIn('<',response.read().decode())
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
