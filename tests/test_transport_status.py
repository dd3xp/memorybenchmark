"""Observer handles cannot interrupt an acknowledged model response."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.request_recovery import RecoveringGatewayModel
from memorybenchmark.transport_status import publish_status, read_status


class TransportStatusTests(unittest.TestCase):
    def test_legacy_observation_uses_append_only_ledger_without_opening_mutable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'transport-status.json';target.write_text('{"kind":"old"}')
            ledger=Path(directory)/'transport-attempts.jsonl'
            ledger.write_text('{"kind":"request_completed","call":7}\n{')
            original=Path.read_text
            def read(path,*args,**kwargs):
                if path==target:raise PermissionError('Mutable status must not be opened')
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',read):
                self.assertEqual(read_status(target,ledger=ledger),{'kind':'request_completed','call':7})

    def test_reader_skips_partial_latest_and_old_status_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'transport-status.json'
            target.write_text('{"kind":"legacy"}')
            before=target.read_bytes()
            for i in range(25):publish_status(target,{'kind':'request_started','call':i})
            self.assertEqual(read_status(target)['call'],24)
            self.assertEqual(target.read_bytes(),before)
            versions=target.with_name('transport-status.versions')
            self.assertEqual(len(list(versions.glob('*.json'))),16)
            (versions/('9'*20+'-partial.json')).write_text('{')
            self.assertEqual(read_status(target)['call'],24)

    def test_successful_rpc_is_not_repeated_to_refresh_observer_status(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'transport-status.json'
            model=RecoveringGatewayModel('https://example.test','secret','fixture',None,status_path=target)
            model.output=Path(directory)/'session';model.output.mkdir()
            calls=[]
            def attempt(body):calls.append(body);return {'lines':['data: done']},{'input_tokens':7,'output_tokens':3}
            model._attempt=attempt
            with patch('memorybenchmark.request_recovery.durable_json',side_effect=PermissionError(13,'shared observer file')):
                self.assertEqual(model({'input':[]}),{'lines':['data: done']})
            self.assertEqual(len(calls),1)
            self.assertEqual(read_status(target)['kind'],'request_completed')
            rows=[json.loads(x) for x in (model.output/'transport-attempts.jsonl').read_text().splitlines()]
            self.assertEqual([x['kind'] for x in rows],['request_started','request_completed'])

    @unittest.skipUnless(os.name=='nt','Windows delete-sharing semantics')
    def test_real_windows_reader_denying_delete_cannot_block_publication(self):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        create=kernel.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'transport-status.json';target.write_text('{}')
            handle=create(str(target),0x80000000,1,None,3,0x80,None)
            self.assertNotEqual(handle,wintypes.HANDLE(-1).value)
            try:
                temporary=target.with_name('replacement.tmp');temporary.write_text('{}')
                with self.assertRaises(PermissionError):os.replace(temporary,target)
                publish_status(target,{'kind':'request_completed','call':33})
                self.assertEqual(read_status(target)['call'],33)
            finally:kernel.CloseHandle(handle)


if __name__=='__main__':unittest.main()
