from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch
import errno

from memorybenchmark.agents.hermes import HermesAdapter
from memorybenchmark.audit_records import read_audit, record_model_request
from memorybenchmark.ga_runtime import copy_memory, memory_manifest
from memorybenchmark.native_source_cache import extract_cached_native
from memorybenchmark.storage_lifecycle import retire_committed_state, retire_working_memory


class StorageLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def archive(self):
        archive=self.root/'native.tar'
        with tarfile.open(archive,'w') as tar:
            for name,body in {'run_agent.py':b'# fixture','tools/memory_tool.py':b'# fixture',
                              'agent/conversation_loop.py':b'# fixture',
                              'skills/default/SKILL.md':b'original native skill'}.items():
                info=tarfile.TarInfo('hermes-agent/'+name);info.size=len(body);tar.addfile(info,io.BytesIO(body))
        return archive

    def test_native_source_shared_but_both_conditions_memory_is_independent(self):
        archive=self.archive()
        a=self.root/'retain';b=self.root/'clear';a.mkdir();b.mkdir()
        left=HermesAdapter().prepare(archive,a);right=HermesAdapter().prepare(archive,b)
        self.assertTrue((left.source/'run_agent.py').samefile(right.source/'run_agent.py'))
        l=left.baseline/'skills/default/SKILL.md';r=right.baseline/'skills/default/SKILL.md'
        self.assertFalse(l.samefile(r));self.assertFalse(l.samefile(left.source/'skills/default/SKILL.md'))
        l.write_text('new learning')
        self.assertEqual(r.read_text(),'original native skill')
        self.assertEqual((right.source/'skills/default/SKILL.md').read_text(),'original native skill')

    def test_changed_cache_is_rejected_before_preparing_another_source(self):
        archive=self.archive();source=extract_cached_native(archive,self.root/'one/source',native='hermes')
        (source/'run_agent.py').write_text('unexpected external mutation')
        with self.assertRaisesRegex(ValueError,'contents changed'):
            extract_cached_native(archive,self.root/'two/source',native='hermes')
        self.assertFalse((self.root/'two/source').exists())

    def test_cross_volume_source_copy_is_explicit_and_verified(self):
        archive=self.archive()
        with patch('memorybenchmark.native_source_cache.os.link',side_effect=OSError(errno.EXDEV,'cross volume')):
            source=extract_cached_native(archive,self.root/'one/source',native='hermes')
        receipt=json.loads((source.parent.parent/'native-source-cache-receipt.json').read_text())
        self.assertEqual(receipt['cross_volume_files_copied'],4)
        self.assertFalse(receipt['mutable_memory_shared'])

    def state(self):
        state=self.root/'live-state'/('a'*32);state.mkdir(parents=True)
        (state/'memory.md').write_text('actual learned experience')
        output=self.root/'sessions/T1';output.mkdir(parents=True)
        expected=copy_memory(state,output/'memory-after')
        report={'infrastructure_ok':True,'output_memory':expected}
        (output/'summary.json').write_text(json.dumps(report))
        return state,output,expected,report

    def test_only_verified_committed_working_copy_is_removed(self):
        state,output,expected,report=self.state()
        retire_committed_state(state,output,report,allowed_parent=self.root/'live-state')
        self.assertFalse(state.exists());self.assertEqual(memory_manifest(output/'memory-after'),expected)
        self.assertEqual(json.loads((output/'working-memory-cleanup.json').read_text())['status'],'removed')

    def test_unique_or_failed_working_memory_is_retained(self):
        state,output,expected,report=self.state()
        (state/'uncommitted.md').write_text('unique evidence')
        retire_committed_state(state,output,report,allowed_parent=self.root/'live-state')
        self.assertTrue(state.exists());self.assertTrue((output/'working-memory-cleanup-deferred.json').exists())
        report['infrastructure_ok']=False
        retire_committed_state(state,output,report,allowed_parent=self.root/'live-state')
        self.assertEqual((state/'uncommitted.md').read_text(),'unique evidence')

    def test_missing_commit_and_escaped_delete_target_are_rejected(self):
        state,output,expected,report=self.state();(output/'summary.json').unlink()
        retire_committed_state(state,output,report,allowed_parent=self.root/'live-state')
        self.assertTrue(state.exists())
        with self.assertRaises(ValueError):retire_working_memory(state,output/'memory-after',expected,allowed_parent=self.root/'other/live-state')
        self.assertTrue(state.exists())

    def test_request_has_one_payload_copy_and_audit_is_logically_identical(self):
        params={'model':'gemini-3.5-flash-lite','reasoning_effort':'high','messages':[{'role':'user','content':'中文经验'*10000}], 'thought_signature':'opaque signed original'}
        message={'kind':'request','id':1,'method':'model','params':params}
        folder=self.root/'session';folder.mkdir()
        ref=record_model_request(message,folder,'model/001-request.json')
        (folder/'audit.jsonl').write_text(json.dumps(ref)+'\n',encoding='utf-8')
        self.assertLess((folder/'audit.jsonl').stat().st_size,1000)
        self.assertEqual(read_audit(folder),[message])
        self.assertEqual(json.loads((folder/'model/001-request.json').read_text(encoding='utf-8')),params)
        self.assertEqual(len(list(folder.rglob('*-request.json'))),1)

    def test_unforwarded_request_and_legacy_audit_are_preserved(self):
        folder=self.root/'session';folder.mkdir()
        message={'kind':'request','id':2,'method':'model','params':{'input':'native request beyond budget'}}
        ref=record_model_request(message,folder,'audit-model-rejections/002.json')
        legacy={'kind':'request','method':'game','params':{'action':'read'}}
        (folder/'audit.jsonl').write_text(json.dumps(ref)+'\n'+json.dumps(legacy)+'\n')
        self.assertEqual(read_audit(folder),[message,legacy]);self.assertFalse((folder/'model').exists())

    def test_model_reference_corruption_and_path_escape_fail_closed(self):
        folder=self.root/'session';folder.mkdir();message={'kind':'request','method':'model','params':{'x':1}}
        ref=record_model_request(message,folder,'model/001-request.json')
        (folder/'audit.jsonl').write_text(json.dumps(ref)+'\n')
        (folder/'model/001-request.json').write_text('{"x":2}')
        with self.assertRaisesRegex(ValueError,'integrity'):read_audit(folder)
        ref['_params_reference']['path']='../../secret.json';(folder/'audit.jsonl').write_text(json.dumps(ref)+'\n')
        with self.assertRaisesRegex(ValueError,'escaped'):read_audit(folder)


if __name__=='__main__':unittest.main()
