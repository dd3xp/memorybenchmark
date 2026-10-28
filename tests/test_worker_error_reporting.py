"""A worker may fail while its last model response is still in flight."""
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from memorybenchmark.agent_sessions import WorkerSessions
from memorybenchmark.errors import InfrastructureError


class WorkerErrorReportingTests(unittest.TestCase):
    def test_wall_expiry_during_model_response_is_not_a_generic_pipe_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "worker.py"
            script.write_text(
                "import json,sys\n"
                "sys.stdin.readline()\n"
                "print(json.dumps({'kind':'request','id':1,'method':'model','params':{'input':[]}}),flush=True)\n"
                "raise SystemExit(9)\n", encoding="utf-8")
            class Jail:
                def command(self, *args, **kwargs):
                    return [sys.executable, "-u", str(script)]
            output = root / "session"; output.mkdir()
            sessions = WorkerSessions(root, root, Jail(), model_alias="fixture", game_transport="legacy-rpc")
            with patch("memorybenchmark.agent_sessions.time.monotonic", return_value=100) as clock:
                def model(payload):
                    clock.return_value = 1001
                    return {"lines": []}
                report = sessions._worker(root, output, {}, model=model)
            self.assertFalse(report["infrastructure_ok"])
            self.assertEqual(report["infrastructure_error"], "worker_wall_timeout")
            self.assertEqual(report["worker_returncode"], 9)
            self.assertEqual(report["worker_elapsed_seconds"], 901)
            self.assertEqual(report["wall_seconds"], 900)
            self.assertEqual(report["llm_calls"], 1)
            self.assertNotIn("host_io_error", report)

    def test_queued_worker_failure_survives_closed_model_response_pipe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "worker.py"
            script.write_text(
                "import json,sys\n"
                "sys.stdin.readline()\n"
                "print(json.dumps({'kind':'request','id':1,'method':'model','params':{'input':[]}}),flush=True)\n"
                "print(json.dumps({'kind':'worker_error','error_type':'RuntimeError','message':'review_fixture_failed'}),flush=True)\n"
                "raise SystemExit(2)\n", encoding="utf-8")
            class Jail:
                def command(self, *args, **kwargs):
                    return [sys.executable, "-u", str(script)]
            output = root / "session"
            output.mkdir()
            sessions = WorkerSessions(root, root, Jail(), model_alias="fixture", game_transport="legacy-rpc")
            children = []
            popen = subprocess.Popen
            def spawn(*args, **kwargs):
                child = popen(*args, **kwargs)
                children.append(child)
                return child
            def model(payload):
                # The worker has exited, leaving worker_error queued while the
                # parent finishes its already outstanding model operation.
                children[0].wait(timeout=5)
                return {"lines": []}
            with patch("memorybenchmark.agent_sessions.subprocess.Popen", side_effect=spawn):
                report = sessions._worker(root, output, {}, model=model)
            self.assertFalse(report["infrastructure_ok"])
            self.assertIn("review_fixture_failed", report["infrastructure_error"])
            self.assertEqual(report["worker_returncode"], 2)
            self.assertEqual(report["underlying_worker_error"]["error_type"], "RuntimeError")
            self.assertIn(report["host_io_error"]["type"], ("BrokenPipeError", "OSError"))
            self.assertNotIn("worker_result", report)

    def test_parent_transport_error_keeps_priority_over_cleanup_eof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "worker.py"
            script.write_text(
                "import json,sys\n"
                "sys.stdin.readline()\n"
                "print(json.dumps({'kind':'request','id':1,'method':'model','params':{'input':[]}}),flush=True)\n"
                "sys.stdin.readline()\n"
                "print(json.dumps({'kind':'worker_error','error_type':'RuntimeError','message':'runner_disconnected'}),flush=True)\n"
                "raise SystemExit(2)\n", encoding="utf-8")
            class Jail:
                def command(self, *args, **kwargs):
                    return [sys.executable, "-u", str(script)]
            output = root / "session"
            output.mkdir()
            sessions = WorkerSessions(root, root, Jail(), model_alias="fixture", game_transport="legacy-rpc")
            def model(payload):
                raise InfrastructureError("gateway_http_503")
            report = sessions._worker(root, output, {}, model=model)
            self.assertFalse(report["infrastructure_ok"])
            self.assertEqual(report["infrastructure_error"], "gateway_http_503")
            self.assertEqual(report["worker_returncode"], 2)
            self.assertNotIn("host_io_error", report)
            self.assertEqual(report["underlying_worker_error"]["message"], "runner_disconnected")


if __name__ == "__main__":
    unittest.main()
