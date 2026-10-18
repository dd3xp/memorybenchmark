import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.game import Game
from memorybenchmark.server import make_server
from memorybenchmark.watch import Observer,WatchStore,frame,observer_atlas


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.run=self.root/'real-run'
        self.run.mkdir()
        self.report={'agent':'GenericAgent','model_alias':'test','tasks':['T1','T2'],'prefix_count':1,
                     'prefix':[],'pairs':[],'complete':False,'kind':'test'}

    def tearDown(self): self.temp.cleanup()

    def test_live_projection_preserves_actions_and_excludes_private_state(self):
        observer=Observer(self.run); observer.begin(self.report)
        game=Game(); adapter=GameAdapter(game)
        initial=adapter.dispatch({'command':'start','task_id':'T1'})
        before={'native-sop.md':{'size':10,'sha256':'before'}}
        sid=observer.open('T1','prefix',initial,before)
        moved=adapter.action('move','J'); observer.observe(sid,moved,{'type':'move','target':'J'})
        observer.observe(sid,moved,{'type':'move','target':'J'})
        observer.activity(sid,'model_start','等待模型响应',calls=1,phase='thinking')
        observer.memory(sid,before,{**before,'lesson.md':{'size':20,'sha256':'after'}},True)
        observer.close(sid,{'success':True,'infrastructure_ok':True,'llm_calls':1})
        value=WatchStore(self.root).snapshot('real-run')
        self.assertEqual(value['completed_sessions'],1)
        row=value['sessions'][0]
        self.assertEqual(len(row['frames']),2)
        self.assertTrue(row['frames'][1]['moved'])
        self.assertEqual(row['frames'][1]['target'],'J')
        self.assertEqual(row['memory']['changed'],['lesson.md'])
        wire=json.dumps(value)
        self.assertNotIn('hazards',wire); self.assertNotIn('system_prompt',wire)
        self.assertNotIn('gateway',wire)

    def test_historical_import_whitelists_and_keeps_repeated_moves(self):
        directory=self.run/'prefix/T1'; directory.mkdir(parents=True)
        game=Game(log_path=directory/'events.jsonl'); adapter=GameAdapter(game)
        adapter.dispatch({'command':'start','task_id':'T1'})
        for target in ('J','S','J','A'): adapter.action('move',target)
        adapter.action('submit')
        row={'path':'prefix/T1','task_id':'T1','infrastructure_ok':True,'success':True,'llm_calls':7,
             'input_memory':{},'output_memory':{},'initial_session':{'system_prompt':'SECRET_SENTINEL'}}
        self.report.update(prefix=[row],complete=True)
        (self.run/'experiment.json').write_text(json.dumps(self.report),encoding='utf-8')
        value=WatchStore(self.root).snapshot('real-run')
        self.assertEqual(sum(f['moved'] for f in value['sessions'][0]['frames']),4)
        self.assertNotIn('SECRET_SENTINEL',json.dumps(value))
        for bad in ('../real-run','/etc/passwd','a/b',''):
            with self.assertRaises(ValueError): WatchStore(self.root).snapshot(bad)

    def test_retry_progress_counts_logical_sessions(self):
        observer=Observer(self.run); observer.begin(self.report)
        game=Game(); initial=GameAdapter(game).dispatch({'command':'start','task_id':'T2'})
        first=observer.open('T2','clear',initial,{})
        observer.close(first,{'success':None,'infrastructure_ok':False,'llm_calls':1})
        second=observer.open('T2','clear',initial,{})
        observer.close(second,{'success':True,'infrastructure_ok':True,'llm_calls':2})
        self.assertEqual(observer.data['completed_sessions'],1)
        self.assertEqual(observer.data['failed_attempts'],1)

    def test_atlas_uses_retained_history_without_sibling_or_future_leakage(self):
        def session(game, task, condition, route, sid):
            adapter = GameAdapter(game)
            response = adapter.dispatch({'command':'start','task_id':task})
            frames = [frame(response)]
            for target in route:
                source = game.position
                response = adapter.action('move',target)
                frames.append(frame(response,{'type':'move','target':target},source))
            if route:
                response=adapter.action('submit')
                frames.append(frame(response,{'type':'submit'},game.position))
            return {'id':sid,'task_id':task,'condition':condition,'status':'complete' if route else 'running','frames':frames}
        game = Game()
        prefix = session(game,'T1','prefix',['J','A'],'prefix')
        checkpoint = game.snapshot()
        cleared = Game(); cleared.restore(checkpoint)
        clear = session(cleared,'T2','clear',['J','L','H','K'],'clear')
        retained = Game(); retained.restore(checkpoint)
        retain = session(retained,'T2','retain',['J','D','A','K'],'retain')
        current = session(retained,'T3','retain',[],'current')
        data = {'tasks':['T1','T2','T3'],'sessions':[prefix,clear,retain,current]}
        prior = observer_atlas(data,'current',0)
        self.assertIn('D',prior['surveyed'])
        self.assertNotIn('L',prior['surveyed'])
        self.assertNotIn('H',prior['surveyed'])
        replay_start = observer_atlas(data,'clear',0)
        self.assertNotIn('D',replay_start['surveyed'])  # Sibling at same task is excluded.
        self.assertNotIn('L',replay_start['surveyed'])  # This session is not yet submitted.
        replay_end = observer_atlas(data,'clear',len(clear['frames'])-1)
        self.assertIn('L',replay_end['surveyed'])
        self.assertNotIn('D',replay_end['surveyed'])

    def test_http_watch_is_read_only_and_private_files_are_not_served(self):
        observer=Observer(self.run); observer.begin(self.report)
        server=make_server(port=0,log_root=self.root/'play',watch_root=self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/watch/runs') as r: self.assertEqual(json.load(r)['runs'][0]['id'],'real-run')
            with urlopen(base+'/api/watch/run?id=real-run') as r: self.assertEqual(json.load(r)['status'],'running')
            for path in ('/','/watch','/play','/watch.js','/watch.css'):
                with urlopen(base+path) as r: self.assertEqual(r.status,200)
            for path in ('/api/watch/run?id=../real-run','/.runs/real-run/live.json','/world-before.json'):
                with self.assertRaises(HTTPError): urlopen(base+path)
            with self.assertRaises(HTTPError):
                urlopen(Request(base+'/api/watch/run',data=b'{}',headers={'Content-Type':'application/json'}))
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()
