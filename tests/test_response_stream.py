"""Real size/path boundaries, framing integrity and worker continuity; no models."""
from hashlib import sha256
import io
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import threading
import tracemalloc
import unittest
from unittest.mock import patch

from memorybenchmark.agent_sessions import WorkerSessions
from memorybenchmark.ga_worker import Wire
from memorybenchmark.request_recovery import RecoveringGatewayModel, RequestFailure
from memorybenchmark.response_stream import CHUNK_BYTES, SpoolLines, send_rpc, forwarded_httpx_response
from memorybenchmark.watch import atomic_json
from memorybenchmark.ga_runtime import filesystem_path
from memorybenchmark.model_gateway import GatewayModel


class StreamingResponseTests(unittest.TestCase):
    def spool(self, root, body):
        p = root / "response.sse"
        p.write_bytes(body)
        return SpoolLines(p, size=len(body), digest=sha256(body).hexdigest(),
                          line_count=len(body.splitlines()))

    def wire(self, incoming):
        value = Wire.__new__(Wire)
        value.input, value.output = incoming, io.StringIO()
        value.lock, value.sequence, value.pending_stream = threading.RLock(), 0, None
        return value

    def test_path_boundaries_and_serialized_spool_are_lossless(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for total in (258, 259, 260, 261, 350, 1024):
                folder = root
                while len(str(folder / "response.json")) + 37 < total - 80:
                    folder /= "segment" * 6
                filesystem_path(folder).mkdir(parents=True, exist_ok=True)
                length = total - 37 - len(str(folder)) - 1
                target = folder / ("x" * (length - 5) + ".json")
                self.assertEqual(len(str(target)) + 37, total)
                atomic_json(target, {"unicode": "记忆", "value": total})
                self.assertEqual(json.loads(filesystem_path(target).read_text(encoding="utf-8"))["value"], total)
            lines = self.spool(root, 'data: {"text":"汉字"}\r\n\r\ndata: done\n'.encode())
            atomic_json(root / "large-response.json", {"lines": lines})
            self.assertEqual(json.loads((root / "large-response.json").read_text(encoding="utf-8")),
                             {"lines": list(lines)})
            # Python3.10's TemporaryDirectory cleanup itself uses ordinary
            # Windows paths. Remove only this explicitly owned test tree with
            # the same extended-path support; no experiment directory is used.
            assert root.resolve().parent == Path(tempfile.gettempdir()).resolve()
            assert root.name.startswith("tmp") and not root.is_symlink()
            shutil.rmtree(filesystem_path(root))

    def test_sse_over_32_mib_is_archived_without_a_size_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            terminal = b'data: {"type":"response.completed","response":{"usage":{"input_tokens":7,"output_tokens":9}}}\n'
            padding = b": " + b"x" * 8190 + b"\n"
            class Response:
                status = 200
                def __init__(self): self.count = 0
                def getheaders(self): return []
                def getheader(self, name, default=""): return default
                def readline(self, limit):
                    self.count += 1
                    return padding if self.count <= 4097 else terminal
            model = RecoveringGatewayModel("https://example.test", "fixture", "fixture", None)
            model.output = root
            tracemalloc.start()
            with patch("memorybenchmark.request_recovery._RoutedHTTPS") as connection:
                connection.return_value.getresponse.return_value = Response()
                result, usage = model._attempt(b"fixed-native-request")
            peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            self.assertLess(peak, 8 * 1024**2, "SSE buffering grew with total response size")
            lines = result["lines"]
            self.assertIsInstance(lines, SpoolLines)
            self.assertGreater(lines.size, 32 * 1024**2)
            self.assertEqual(usage, {"input_tokens": 7, "output_tokens": 9})
            h = sha256()
            for _ in range(4097): h.update(padding)
            h.update(terminal)
            self.assertEqual(lines.digest, h.hexdigest())
            self.assertEqual(lines[-1], terminal.decode().rstrip())
            # Serializing the evidence is streaming and retains the existing
            # list-of-SSE-lines audit format, including streams over8MiB.
            atomic_json(root / "response.json", result)
            self.assertGreater((root / "response.json").stat().st_size, 32 * 1024**2)

    def test_single_large_event_and_unicode_chunk_boundaries_reach_native_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = ('data: ' + json.dumps({"text": "记忆" * (800_000)}, ensure_ascii=False) + '\n\n').encode()
            body += b'data: {"type":"response.completed","response":{}}\n'
            lines = self.spool(root, body)
            framed = root / "wire.jsonl"
            with framed.open("w", encoding="utf-8") as out: send_rpc(out, {"id": 1, "result": {"lines": lines}})
            with framed.open(encoding="utf-8") as incoming:
                wire = self.wire(incoming)
                result = wire.call("model", {"input": []})
                self.assertEqual(list(result["lines"]), list(lines))
                self.assertTrue(result["lines"].finished)
            with framed.open(encoding="utf-8") as incoming:
                wire = self.wire(incoming)
                received = b"".join(wire.call("model", {"input": []})["lines"].iter_bytes())
                self.assertEqual(received, body + b"\n\n")

    def test_early_close_drains_only_transport_and_allows_the_next_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lines = self.spool(root, b": padding\n" * 10000 + b"data: done\n")
            framed = io.StringIO()
            send_rpc(framed, {"id": 1, "result": {"lines": lines}})
            framed.write(json.dumps({"id": 2, "result": {"kept": True}}) + "\n")
            framed.seek(0)
            wire = self.wire(framed)
            reply = wire.call("model", {"input": []})
            stream = iter(reply["lines"].iter_bytes())
            self.assertLessEqual(len(next(stream)), CHUNK_BYTES)
            self.assertEqual(wire.call("game", {}), {"kept": True})
            self.assertTrue(reply["lines"].finished)

    def test_chunk_corruption_is_detected_and_releases_rpc_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lines = self.spool(Path(directory), b"data: done\n")
            framed = io.StringIO(); send_rpc(framed, {"id": 1, "result": {"lines": lines}})
            rows = framed.getvalue().splitlines(); header = json.loads(rows[0]);header["result_stream"]["sha256"] = "0" * 64
            rows[0] = json.dumps(header)
            wire = self.wire(io.StringIO("\n".join(rows) + "\n"))
            with self.assertRaisesRegex(RuntimeError, "SHA mismatch"): wire.call("model", {"input": []})
            acquired = []
            def check():
                value = wire.lock.acquire(blocking=False); acquired.append(value)
                if value: wire.lock.release()
            t = threading.Thread(target=check);t.start();t.join()
            self.assertEqual(acquired, [True])

    def test_hermes_http_response_preserves_both_client_read_modes(self):
        import httpx
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);body=b'data: {"type":"response.completed","response":{}}\n'
            for streaming in (False,True):
                framed=io.StringIO();send_rpc(framed,{'id':1,'result':{'lines':self.spool(root,body)}});framed.seek(0)
                wire=self.wire(framed);lines=wire.call('model',{'input':[]})['lines']
                response=forwarded_httpx_response(httpx,httpx.Request('POST','https://model.invalid/v1/responses'),lines,streaming=streaming)
                if streaming:self.assertFalse(response.is_stream_consumed)
                else:self.assertEqual(response.content,body+b'\n\n')
                self.assertEqual(response.read(),body+b'\n\n');response.close()
                self.assertTrue(lines.finished)

    def test_other_native_tool_thread_can_call_before_model_iterator_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            body=b'data: {"type":"response.completed","response":{}}\n'
            framed=io.StringIO();send_rpc(framed,{'id':1,'result':{'lines':self.spool(Path(directory),body)}})
            framed.write(json.dumps({'id':2,'result':{'moved':True}})+'\n');framed.seek(0)
            wire=self.wire(framed);reply=wire.call('model',{'input':[]})
            # Match GA: parse the terminal event but leave its iterator alive.
            iterator=iter(reply['lines']);self.assertEqual(next(iterator),body.decode().rstrip())
            results=[]
            t=threading.Thread(target=lambda:results.append(wire.call('game',{})),daemon=True)
            t.start();t.join(timeout=2)
            self.assertFalse(t.is_alive(),'Native tool broker blocked on an unclosed model iterator')
            self.assertEqual(results,[{'moved':True}]);reply['lines'].close()

    def test_real_worker_accepts_request_over_four_mib_and_preserves_its_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); checkpoint = root / "checkpoint.json"
            body = b": original SSE bytes\n" * 500_000 + b'data: {"type":"response.completed"}\n'
            lines = self.spool(root, body)
            worker = root / "worker.py"
            worker.write_text('''import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from memorybenchmark.ga_worker import Wire
w=Wire(); c=json.loads(w.input.readline()); p=Path(c['checkpoint'])
p.write_text(json.dumps({'pid':os.getpid(),'actions':['first_move'],'memory':'unchanged'}))
r=w.call('model',{'input':[{'role':'user','content':'x'*(5*1024**2)}]})
from hashlib import sha256
h=sha256()
for part in SpoolLines.iter_bytes(r['lines']):h.update(part)
assert json.loads(p.read_text())=={'pid':os.getpid(),'actions':['first_move'],'memory':'unchanged'}
w.emit('finished',pid=os.getpid(),digest=h.hexdigest())
'''.replace('from memorybenchmark.ga_worker import Wire','from memorybenchmark.ga_worker import Wire\nfrom memorybenchmark.response_stream import SpoolLines'), encoding="utf-8")
            class Jail:
                def command(self, *args, **kwargs): return [sys.executable, "-u", str(worker), str(Path.cwd())]
            seen = []
            def model(payload):
                seen.append(len(payload["input"][0]["content"]))
                return {"lines": lines}
            sessions = WorkerSessions(root, root, Jail(), model_alias="fixture", wall_seconds=30, game_transport="legacy-rpc")
            report = sessions._worker(root, root, {"checkpoint": str(checkpoint)}, model=model)
            self.assertTrue(report["infrastructure_ok"], report)
            self.assertEqual(report["worker_result"]["digest"], sha256(body).hexdigest())
            self.assertEqual(seen, [5 * 1024**2])
            self.assertEqual(report["llm_calls"], 1)

    def test_partial_large_stream_is_retained_and_same_request_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);(root / "model").mkdir();(root / "model/001-request.json").write_text("{}")
            padding = b": " + b"x" * 8190 + b"\n"
            terminal = b'data: {"type":"response.completed","response":{"usage":{"input_tokens":1,"output_tokens":2}}}\n'
            class Response:
                status = 200
                def __init__(self, fail): self.fail,self.count = fail,0
                def getheaders(self): return []
                def getheader(self, name, default=""): return default
                def readline(self, limit):
                    self.count += 1
                    if self.count <= 1100: return padding
                    return b"" if self.fail else terminal
            model = RecoveringGatewayModel("https://example.test", "fixture", "fixture", None,
                                           sleep=lambda _:None, jitter=lambda a,b:0)
            model.output = root
            with patch("memorybenchmark.request_recovery._RoutedHTTPS") as connection:
                connection.return_value.getresponse.side_effect = [Response(True),Response(False)]
                result = model({"input": [], "reasoning":{"effort":"high"}})
                payloads = [c.kwargs["body"] for c in connection.return_value.request.call_args_list]
            self.assertEqual(len(payloads), 2)
            self.assertEqual(payloads[0], payloads[1])
            self.assertEqual(len(list((root / "model-streams").glob("*.sse"))), 2)
            events = [json.loads(x) for x in (root / "transport-attempts.jsonl").read_text().splitlines()]
            failed = next(x for x in events if x["kind"] == "request_failed")
            self.assertTrue(failed["retryable"])
            self.assertGreater(failed["response_stream_evidence"]["bytes"],8*1024**2)
            self.assertTrue(Path(failed["response_stream_evidence"]["path"]).exists())
            self.assertGreater(result["lines"].size,8*1024**2)

    def test_nonrecovery_gateway_also_has_no_eight_mib_response_cutoff(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def __iter__(self):
                for _ in range(1200): yield b": " + b"x" * 8190 + b"\n"
                yield b'data: {"type":"response.completed","response":{"usage":{}}}\n'
        with tempfile.TemporaryDirectory() as directory:
            model=GatewayModel('https://example.test','fixture','fixture',None);model.output=Path(directory)
            with patch('memorybenchmark.model_gateway.urlopen',return_value=Response()):
                result=model({'input':[],'reasoning':{'effort':'high'}})
            self.assertGreater(result['lines'].size,8*1024**2)

    def test_archive_flush_failure_is_not_misclassified_as_a_network_retry(self):
        class Response:
            status=200
            def getheaders(self):return []
            def getheader(self,name,default=''):return default
            def readline(self,limit):return b'data: {"type":"response.completed","response":{}}\n'
        with tempfile.TemporaryDirectory() as directory:
            model=RecoveringGatewayModel('https://example.test','fixture','fixture',None);model.output=Path(directory)
            original=Path.open
            class Writer:
                def __init__(self,stream):self.stream=stream
                def write(self,value):return self.stream.write(value)
                def flush(self):raise OSError(28,'synthetic full archive disk')
                def close(self):return self.stream.close()
            def open_file(path,*args,**kwargs):
                stream=original(path,*args,**kwargs)
                return Writer(stream) if args and args[0]=='wb' and path.suffix=='.sse' else stream
            with patch('memorybenchmark.request_recovery._RoutedHTTPS') as connection,patch.object(Path,'open',open_file):
                connection.return_value.getresponse.return_value=Response()
                with self.assertRaises(RequestFailure) as caught:model._attempt(b'unchanged')
            self.assertEqual(caught.exception.detail['reason'],'response_archive_io_error')
            self.assertFalse(caught.exception.retryable)


if __name__ == "__main__": unittest.main()
