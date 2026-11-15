"""Retry a failed model request without replaying the native session."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from memorybenchmark.agent_sessions import WorkerSessions
from memorybenchmark.errors import InfrastructureError
from memorybenchmark.request_recovery import ActiveClock, RecoveringGatewayModel, RequestFailure, WEEK, durable_json
from memorybenchmark.recovery_runtime import RecoveryJail, install
from memorybenchmark.recovery_lease import NativeConfigJSON, native_transport_environment


class FakeTime:
    def __init__(self): self.now = 100.0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class RequestRecoveryTests(unittest.TestCase):
    def test_native_transport_settings_preserve_model_and_do_not_rewrite_payloads(self):
        proxy=NativeConfigJSON(3600)
        config={'model':{'base_url':'https://model.invalid/v1','default':'fixture','provider':'custom'},
                'terminal':{'backend':'local'}}
        result=json.loads(proxy.dumps(config))
        self.assertEqual(result['model'],config['model'])
        self.assertNotIn('providers',config)
        self.assertGreater(result['auxiliary']['compression']['timeout'],WEEK)
        payload={'input':[],'reasoning':{'effort':'high'}}
        self.assertEqual(json.loads(proxy.dumps(payload)),payload)
        self.assertTrue(all(int(v)>WEEK for v in native_transport_environment('hermes_worker.py',3600).values()))
        self.assertEqual(native_transport_environment('ga_worker.py',3600),{})

    def model(self, timer, **options):
        return RecoveringGatewayModel("https://example.test:443", "test-secret", "test-model", None,
            monotonic=timer.monotonic, sleep=timer.sleep, jitter=lambda a,b: 1, **options)

    def test_same_payload_and_logical_call_survive_multiple_errors(self):
        timer = FakeTime()
        model = self.model(timer)
        bodies = []
        def attempt(body):
            bodies.append(body)
            timer.sleep(20)
            if len(bodies) <= 2:
                raise RequestFailure("gateway_http_502", retryable=True, body="upstream error")
            return {"lines": ["data: done"]}, {"input_tokens": 7, "output_tokens": 3}
        with tempfile.TemporaryDirectory() as directory:
            model.output = Path(directory)
            (model.output / "model").mkdir()
            model._attempt = attempt
            result = model({"input": [{"role": "user", "content": "one task"}], "reasoning": {"effort": "high"}})
            events = [json.loads(line) for line in (model.output/"transport-attempts.jsonl").read_text().splitlines()]
        self.assertEqual(result, {"lines": ["data: done"]})
        self.assertEqual(len(bodies), 3)
        self.assertEqual(len(set(bodies)), 1)
        self.assertEqual(sum(e["kind"] == "request_completed" for e in events), 1)
        self.assertAlmostEqual(model.clock.elapsed(), 20)
        self.assertAlmostEqual(model.clock.infrastructure_seconds(), 46)

    def test_one_week_is_a_time_window_not_a_retry_counter(self):
        timer = FakeTime()
        model = self.model(timer, retry_window=10)
        model._attempt = lambda body: (_ for _ in ()).throw(RequestFailure("gateway_http_429", retryable=True))
        with self.assertRaisesRegex(InfrastructureError, "request_recovery_week_exhausted"):
            model({"input": []})
        self.assertAlmostEqual(timer.now, 110)
        self.assertAlmostEqual(model.clock.elapsed(), 0)
        self.assertEqual(WEEK, 604800)

    def test_auth_and_invalid_requests_are_not_blindly_retried(self):
        timer = FakeTime()
        model = self.model(timer)
        attempts = []
        def rejected(body):
            attempts.append(body)
            raise RequestFailure("gateway_http_401", retryable=False)
        model._attempt = rejected
        with self.assertRaisesRegex(InfrastructureError, "nonretryable_model_request"):
            model({"input": []})
        self.assertEqual(len(attempts), 1)
        self.assertNotIn("test-secret", model._clean("Bearer test-secret"))

    def test_transient_windows_sharing_violation_does_not_kill_publication(self):
        with patch("memorybenchmark.request_recovery.atomic_json", side_effect=[PermissionError(5,"sharing violation"),None]) as write:
            with patch("memorybenchmark.request_recovery.time.sleep"):
                durable_json("unused.json", {"heartbeat":1})
        self.assertEqual(write.call_count, 2)

    def test_sse_returns_at_terminal_event_and_preserves_tls_hostname(self):
        timer = FakeTime()
        model = self.model(timer, connect_host="127.0.0.1")
        class Response:
            status = 200
            def __init__(self): self.lines = iter([b'data: {"type":"response.completed","response":{"usage":{"input_tokens":1}}}\n'])
            def getheaders(self): return []
            def getheader(self, name, default=""): return default
            def readline(self, limit): return next(self.lines)  # A second read would fail.
        response = Response()
        with patch("memorybenchmark.request_recovery._RoutedHTTPS") as connection:
            connection.return_value.getresponse.return_value = response
            result = model({"input": []})
            args, _ = connection.call_args
        self.assertEqual(args, ("example.test", 443, "127.0.0.1"))
        self.assertEqual(len(result["lines"]), 1)

    def test_real_worker_keeps_its_pid_and_checkpoint_across_model_failures(self):
        install()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "toy.py"
            checkpoint = root / "checkpoint.json"
            worker.write_text('''import json, os, sys
config = json.loads(input())
path = config['checkpoint']
with open(path, 'w') as f: json.dump({'pid':os.getpid(), 'actions':['first_move']}, f)
print(json.dumps({'kind':'request','id':1,'method':'model','params':{'input':[]}}), flush=True)
reply = json.loads(input())
with open(path) as f: state=json.load(f)
assert state['pid']==os.getpid() and state['actions']==['first_move'] and reply['id']==1
print(json.dumps({'kind':'finished','pid':os.getpid()}), flush=True)
''', encoding="utf-8")
            class LocalRecoveryJail(RecoveryJail):
                def __init__(self):
                    self.recovery_root = root / "recovery"
                    self.clock = ActiveClock()
                    self.lease = None
                def command(self, *args, **kwargs): return [sys.executable, "-u", str(worker)]
            jail = LocalRecoveryJail()
            model = RecoveringGatewayModel("https://example.test", "test-secret", "test", None,
                                           sleep=lambda seconds: None, jitter=lambda a,b:0)
            attempts = []
            def attempt(body):
                attempts.append(json.loads(checkpoint.read_text()))
                if len(attempts) < 3:
                    raise RequestFailure("gateway_http_502", retryable=True)
                return {"lines": []}, None
            model._attempt = attempt
            session = WorkerSessions(root, root, jail, model_alias="test", wall_seconds=10, game_transport="legacy-rpc")
            result = session._worker(root, root, {"checkpoint":str(checkpoint)}, model=model)
            self.assertTrue(result["infrastructure_ok"], result)
            self.assertEqual(result["llm_calls"], 1)
            self.assertEqual(result["main_calls"], 1)
            self.assertEqual(len(attempts), 3)
            self.assertTrue(all(a == attempts[0] for a in attempts))
            self.assertEqual(result["worker_result"]["pid"], attempts[0]["pid"])


if __name__ == "__main__":
    unittest.main()
