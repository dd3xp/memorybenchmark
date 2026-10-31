"""Multi-stage isolation, naturally delivered facts, and actual graph boundaries."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.analysis import commute_graph
from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design
from memorybenchmark.prototypes.station_choice import station_decisions
from memorybenchmark.prototypes.station_routes import feedback_policy, known_world_route, schedule, walk
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN, EASY20_LINKED_DESIGN, StationSession
from scripts.build_easy20_linked_map import build
from scripts.check_easy20_linked import FeedbackSimulation
from scripts.audit_station_decisions import align_tools


class LinkedStationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(EASY20_LINKED_DESIGN)

    def test_two_independent_decisions_share_a_stable_balanced_world(self):
        d = self.design
        raw = json.loads(EASY20_LINKED_DESIGN.read_text(encoding='utf-8'))
        self.assertEqual(build(), raw)
        self.assertEqual((len(d['public']['locations']), len(d['public']['edges']), len(d['private_worlds'])), (70, 77, 1296))
        count = {g:0 for g in d['public']['capability_groups']}
        for row in schedule(d):
            self.assertEqual(len({s['group'] for s in row['stage_schedule']}), 2)
            for stage in row['stage_schedule']:count[stage['group']] += 1
        self.assertEqual(set(count.values()), {10})
        for station in ['A','B','N1','N2']:
            self.assertEqual(sum(w[station]=='profile' for w in d['private_worlds'].values()), 648)

    def test_first_processing_does_not_end_session_or_allow_early_submission(self):
        g = StationGame('omega_0000', self.design); session = StationSession(g,'T1')
        first = session.initial
        self.assertIn('第 2 段',first['text'].splitlines()[0])
        self.assertNotIn('T2',json.dumps(first))
        walk(g,'P');walk(g,'A');result = g.step({'type':'process'})
        self.assertFalse(g.done);self.assertEqual(g.state.stage,1)
        self.assertFalse(g.state.raw);self.assertFalse(g.state.processed)
        self.assertEqual(result['feedback']['next_stage'],2)
        self.assertEqual(result['observation']['task']['target'],'R')
        walk(g,'C');self.assertEqual(g.step({'type':'submit'})['feedback']['kind'],'not_ready')
        self.assertFalse(g.done)
        walk(g,'R');walk(g,'D');g.step({'type':'process'});walk(g,'C')
        self.assertTrue(g.step({'type':'submit'})['observation']['success'])
        self.assertEqual(g.observation()['stages_completed'],2)

    def test_early_visit_and_old_samples_do_not_satisfy_later_stage(self):
        g = StationGame('omega_0000',self.design);g.start_task('T1')
        walk(g,'R');self.assertFalse(g.state.raw)
        walk(g,'P');walk(g,'A');g.step({'type':'process'})
        walk(g,'D');self.assertNotIn({'type':'process'},g.observation()['available_actions'])
        walk(g,'R');self.assertTrue(g.state.raw)

    def test_failed_processing_reveals_only_one_fact_without_advancing(self):
        g = StationGame('omega_5555',self.design);g.start_task('T1')
        walk(g,'P');walk(g,'A');feedback = g.step({'type':'process'})['feedback']
        self.assertEqual(feedback['result'],'unsupported');self.assertTrue(g.state.raw)
        self.assertEqual(g.state.stage,0);self.assertEqual(len(compatible_worlds(self.design,g.events)),648)
        g.step({'type':'abandon'});session = StationSession(g,'T3')
        self.assertEqual(session.initial['observation']['stage_index'],0)
        self.assertEqual(session.initial['feedback'],{'kind':'started'})
        self.assertNotIn('station_information',json.dumps(session.initial))

    def test_graphs_retain_both_stage_choices_and_actual_intermediate_edges(self):
        d = self.design; sim = FeedbackSimulation(d); history={}; source=StationGame('omega_5555',d)
        for task in ('T1','T2'):
            _, history = sim.run('omega_5555',task,history,runtime=source)
        graphs=[];costs=[]
        for facts in (history,{}):
            g=deepcopy(source);row,_=sim.run('omega_5555','T3',facts,runtime=g)
            graph=commute_graph(g.events,g.task_run_id)
            self.assertEqual(len(graph['edges']),row['moves'])
            self.assertEqual(graph['distance'],row['distance'])
            for e in graph['edges']:
                self.assertIn(tuple(sorted((e['source'],e['target']))),{tuple(sorted((a,b))) for a,b,_ in d['public']['edges']})
            choice=station_decisions(d,g.events,g.task_run_id)
            self.assertEqual(len(choice['stages']),2)
            self.assertTrue(all(s['first_postcollection_station'] for s in choice['stages']))
            analysis=analyze_trace(d,g.events,g.task_run_id,exact_references=False)
            self.assertEqual((analysis['completed_stages'],analysis['total_stages']),(2,2))
            for branch in analysis['branch_excursions']:
                self.assertEqual(len(branch['move_event_ids']),6)
                self.assertTrue(branch['returned_to_fork'])
                self.assertGreaterEqual(branch['distance'],6)
            graphs.append(graph);costs.append((g.distance,g.steps))
        self.assertEqual(costs,[(36,31),(64,59)])
        self.assertGreater(len(graphs[1]['edges']),len(graphs[0]['edges']))

    def test_retrieval_after_branch_departure_is_not_counted_before_choice(self):
        g=StationGame('omega_5555',self.design);FeedbackSimulation(self.design).run('omega_5555','T1',{},runtime=g)
        decision=station_decisions(self.design,g.events,g.task_run_id)
        departure=decision['stages'][0]['first_postcollection_branch_choice']['event_id']
        arrival=decision['stages'][0]['first_postcollection_station']['event_id']
        self.assertLess(departure,arrival)
        messages=[]
        for event in g.events:
            if event['kind']!='action':continue
            messages.append({'kind':'request','method':'game','params':{'command':'action','action':event['action']}})
            if event['event_id']==departure:
                messages.append({'kind':'tool','name':'file_read','args':{'path':'survey_game_sop.md'}})
        messages.append({'kind':'request','method':'task_end'})
        windows=align_tools(g.events,g.task_run_id,messages,decision)['stages'][0]
        self.assertEqual(windows['before_first_postcollection_branch_choice']['file_read_basenames'],[])
        self.assertEqual(windows['before_first_postcollection_station']['file_read_basenames'],['survey_game_sop.md'])

    def test_zero_gain_control_and_runtime_policy_both_complete(self):
        sim=FeedbackSimulation(self.design);history={};game=StationGame('omega_0000',self.design)
        for task in ('T1','T2'):_,history=sim.run('omega_0000',task,history,runtime=game)
        a,_=sim.run('omega_0000','T3',history,runtime=deepcopy(game))
        b,_=sim.run('omega_0000','T3',{},runtime=deepcopy(game))
        self.assertEqual((a['distance'],a['operations']),(b['distance'],b['operations']))
        game.start_task('T3');feedback_policy(game);self.assertTrue(game.state.success)

    def test_default_human_design_view_covers_both_stages_without_leaking_to_play(self):
        with tempfile.TemporaryDirectory() as directory:
            service=FieldService(Path(directory), self.design);public=service.start({});g=service.instances[public['instance_id']]['game']
            self.assertEqual(public['observation']['environment']['version'],'lanting-easy20-linked-v3')
            self.assertNotIn('capabilities',public);before=deepcopy(g.events)
            design=service.design_view(public['instance_id']);self.assertEqual(g.events,before)
            self.assertEqual(len(design['triggers']),16)
            for task in design['tasks']:
                self.assertEqual(len(task['stage_options']),2)
                self.assertTrue(all(len(s['matching_stations'])==2 for s in task['stage_options']))
                reference=known_world_route(g.design,task['id'],design['capabilities'])
                self.assertEqual(task['known_world_route'],reference['path'])

    def test_legacy_choice_events_keep_their_original_shape(self):
        old=load_design(EASY20_CHOICE_DESIGN);g=StationGame('omega_0000',old)
        initial=g.start_task('T1');self.assertNotIn('stage_index',initial['observation'])
        walk(g,'P');walk(g,'A');g.step({'type':'process'})
        self.assertEqual(g.events[-1]['state_before'],{'raw':True,'processed':False})
        self.assertNotIn('next_stage',g.events[-1]['delivered']['feedback'])

    def test_native_runner_uses_linked_budget_and_one_session_per_two_stage_task(self):
        from memorybenchmark.ga_runtime import copy_memory
        from memorybenchmark.prototypes.station_pilot import pilot
        budgets=[];completed=[]
        class ScriptedFixture:
            def __init__(self,*args,**kwargs):budgets.append((kwargs['max_turns'],kwargs['wall_seconds']))
            def probe(self,baseline,output):output.mkdir();(output/'summary.json').write_text('{}')
            def run(self,game,task,memory,output,model,*,condition):
                output.mkdir(parents=True);game.start_task(task);feedback_policy(game,retain_history=condition!='clear')
                completed.append((task,condition,game.observation()['stages_completed']))
                copy_memory(memory,output/'memory-after')
                result={'task_id':task,'success':game.state.success,'distance':game.distance,'llm_calls':0,
                        'content_changed':[],'infrastructure_ok':True}
                (output/'summary.json').write_text(json.dumps(result))
                (output/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in game.events))
                return result
        def source_fixture(archive,destination):
            source=destination/'GenericAgent';(source/'memory').mkdir(parents=True);return source
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'fixture.tar';archive.write_bytes(b'synthetic fixture')
            with patch('memorybenchmark.prototypes.station_pilot.extract_native',source_fixture),\
                 patch('memorybenchmark.prototypes.station_pilot.make_support',lambda p:p.mkdir()),\
                 patch('memorybenchmark.prototypes.station_pilot.StationNativeSessions',ScriptedFixture),redirect_stdout(io.StringIO()):
                report=pilot(archive,root/'pilot',None,None,design_path=EASY20_LINKED_DESIGN,
                             tasks=['T1','T2','T3'])
            self.assertEqual(budgets,[(100,3600)]);self.assertEqual(report['max_turns'],100)
            self.assertEqual(report['wall_seconds'],3600)
            self.assertEqual(report['feedback_mode'],'compact')
            self.assertEqual(report['feedback_protocol'],'station-compact-feedback-1')
            with self.assertRaisesRegex(ValueError,'feedback mode'):
                pilot(archive,root/'pilot',None,None,resume=True,feedback_mode='full')
            with self.assertRaisesRegex(ValueError,'wall-clock budget'):
                pilot(archive,root/'pilot',None,None,design_path=EASY20_LINKED_DESIGN,
                      resume=True,wall_seconds=900)
            self.assertEqual(len(completed),6);self.assertTrue(all(n==2 for _,_,n in completed))


if __name__ == '__main__':unittest.main()
