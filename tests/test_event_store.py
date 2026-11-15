from copy import deepcopy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from contextlib import redirect_stdout
import io

from memorybenchmark.event_store import read_events, write_events, read_archive_events
from memorybenchmark.pilot_watch import public_deliveries
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import replay_checkpoint
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def snapshot(self, name, events, filename='events.jsonl'):
        path = self.root/'sessions'/name/filename
        path.parent.mkdir(parents=True, exist_ok=True)
        write_events(path, events)
        return path

    def test_legacy_array_jsonl_single_and_empty(self):
        path=self.root/'legacy'
        for body, expected in [('[]', []), ('', []), ('{"x":1}\n', [{'x':1}]), ('{"x":1}\n{"x":2}\n', [{'x':1},{'x':2}])]:
            path.write_text(body, encoding='utf-8')
            self.assertEqual(read_events(path),expected)

    def test_complete_prefixes_are_lossless_and_share_storage(self):
        events=[{'task_run_id':f'run-{i//8}', 'kind':'action', 'message':'中文资料'+str(i)*30} for i in range(256)]
        for n in range(8,257,8):
            p=self.snapshot(str(n),events[:n])
            q=self.snapshot(str(n),events[:n-8],'prior-events.json')
            self.assertEqual(read_events(p),events[:n])
            self.assertEqual(read_events(q),events[:n-8])
        raw=sum(len(gzip.decompress(p.read_bytes())) for p in (self.root/'event-store').glob('*.gz'))
        unique=len(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events).encode())
        self.assertLess(raw,unique*4)  # full snapshots would contain >32 complete copies

    def test_failed_branch_moves_without_importing_its_history(self):
        prefix=[{'value':i} for i in range(40)]
        first=self.snapshot('failed',prefix+[{'failed_attempt':'only here'}])
        archived=self.root/'failed-attempts'/'failed'
        archived.parent.mkdir()
        first.parent.rename(archived)
        next_path=self.snapshot('continued',prefix+[{'canonical':'own continuation'}])
        self.assertEqual(read_events(archived/'events.jsonl'),prefix+[{'failed_attempt':'only here'}])
        self.assertEqual(read_events(next_path),prefix+[{'canonical':'own continuation'}])

    def test_block_and_index_corruption_are_rejected(self):
        p=self.snapshot('1',[{'x':1}])
        descriptor=json.loads(p.read_text())
        blob=self.root/'event-store'/(descriptor['chunks'][0]['sha256']+'.jsonl.gz')
        original=blob.read_bytes()
        blob.write_bytes(gzip.compress(b'{"x":2}\n'))
        with self.assertRaisesRegex(ValueError,'integrity'):read_events(p)
        blob.write_bytes(original)
        descriptor['events']=2;p.write_text(json.dumps(descriptor))
        with self.assertRaisesRegex(ValueError,'integrity'):read_events(p)
        descriptor['store']='../../../other';p.write_text(json.dumps(descriptor))
        with self.assertRaisesRegex(ValueError,'location'):read_events(p)

    def test_archive_is_self_contained_and_legacy_archive_remains_readable(self):
        p=self.snapshot('1',[{'x':'中文'}])
        archive=self.root/'evidence.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for file in [p,*list((self.root/'event-store').glob('*.gz'))]:
                z.write(file,'run/'+file.relative_to(self.root).as_posix())
            z.writestr('retain/events.jsonl','{"legacy":true}\n')
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(read_archive_events(z,'run/sessions/1/events.jsonl'),[{'x':'中文'}])
            self.assertEqual(read_archive_events(z,'retain/events.jsonl'),[{'legacy':True}])

    def test_actual_game_checkpoint_and_public_projection_are_exact(self):
        design=load_design(DEFAULT_DESIGN)
        game=StationGame('omega_00',design)
        folders=[]
        for i in range(1,4):
            game.start_task(f'T{i}')
            game.step({'type':'abandon'})
            p=self.snapshot(str(i),deepcopy(game.events))
            (p.parent/'summary.json').write_text(json.dumps({'task_id':f'T{i}'}))
            (p.parent/'graph.json').write_text(json.dumps({'task_run_id':game.task_run_id}))
            folders.append(p.parent)
        restored=replay_checkpoint(design,'omega_00',folders)
        self.assertEqual(restored.events,game.events)
        expected=[{'request':{'action':e.get('action',{})},'response':e['delivered']} for e in game.events if e['task_run_id']==game.task_run_id and 'delivered' in e]
        self.assertEqual(list(public_deliveries(folders[-1])),expected)

    def test_original_strict_audit_accepts_both_conditions_and_unchanged_memory(self):
        from tests.test_station_independent import IndependentStationTests
        from memorybenchmark.prototypes.station_independent import execute
        from scripts.audit_station_native import audit
        fixture=IndependentStationTests()
        for condition in ('retain','clear'):
            run=fixture.make_run(self.root,condition)
            sessions,*_=fixture.fixture()
            with patch('memorybenchmark.prototypes.station_independent.StationNativeSessions',sessions), redirect_stdout(io.StringIO()):
                execute(run,None,None,retry_delay=0)
            for session in (run/'sessions').iterdir():
                summary_path=session/'summary.json'
                summary=json.loads(summary_path.read_text())
                summary['session_id']=session.name
                summary['initial_session']['native_tool_registry_unchanged']=True
                summary_path.write_text(json.dumps(summary))
            before=audit(run)
            for session in (run/'sessions').iterdir():
                for name in ('prior-events.json','events.jsonl'):
                    path=session/name
                    write_events(path,read_events(path))
            self.assertEqual(audit(run),before)


if __name__=='__main__': unittest.main()
