"""Reasoning configuration, provider acknowledgements and usage coverage."""
import json
from pathlib import Path
import tempfile
import unittest
import sys

from memorybenchmark.agent_sessions import WorkerSessions, native_model_request_kind
from scripts.compare_station_experiments import compare
from scripts.report_station_experiment import model_usage
from memorybenchmark.prototypes.station_independent import PROTOCOL
from memorybenchmark.watch import atomic_json as save_json


class ReasoningEffortTests(unittest.TestCase):
    def test_only_native_tool_free_hermes_title_is_exempt_from_agent_effort(self):
        title = {"instructions": "You name chat sessions. Given the user's opening message, write a title that lets them find this conversation again.", "input": []}
        self.assertEqual(native_model_request_kind(title, "hermes-session-1"), "session_title")
        self.assertEqual(native_model_request_kind(title, "ga-session-1"), "agent")
        self.assertEqual(native_model_request_kind({**title, "tools": [{"type": "function", "name": "memory"}]}, "hermes-session-1"), "agent")
        self.assertEqual(native_model_request_kind({"instructions": "Review this session and update memories", "input": []}, "hermes-session-1"), "agent")

    def test_task_configuration_preserves_legacy_low_and_forwards_high(self):
        initial = {"text": "task", "observation": {}}
        for effort in ("low", "high"):
            options = {} if effort == "low" else {"reasoning_effort": effort}
            sessions = WorkerSessions(".", ".", None, model_alias="fixture", game_transport="legacy-rpc", **options)
            self.assertEqual(sessions.task_config(initial)["reasoning_effort"], effort)
        with self.assertRaisesRegex(ValueError, "reasoning effort"):
            WorkerSessions(".", ".", None, model_alias="fixture", reasoning_effort="typo")

    def test_provider_usage_has_coverage_and_rejects_wrong_effort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "model").mkdir()
            def write(index, response):
                event = {"type": "response.completed", "response": response}
                save_json(root / f"model/{index:03d}-response.json", {"lines": ["data: " + json.dumps(event)]})
            write(1, {"reasoning": {"effort": "high"}, "usage": {"input_tokens": 20, "output_tokens": 10,
                "output_tokens_details": {"reasoning_tokens": 7}}})
            usage = model_usage(root, "high")
            self.assertEqual(usage["reported_tokens"], {"input_tokens": 20, "output_tokens": 10, "reasoning_tokens": 7})
            self.assertTrue(usage["usage_complete"])
            with self.assertRaisesRegex(ValueError, "Provider reasoning effort"):
                model_usage(root, "low")
            write(2, {})
            usage = model_usage(root, "high")
            self.assertFalse(usage["usage_complete"])
            self.assertEqual(usage["calls_with_usage"], 1)
            self.assertEqual(usage["calls_with_effort_acknowledgement"], 1)
            save_json(root / "model/002-request.json", {"instructions": "You name chat sessions. Given the user's opening message, write a title"})
            write(2, {"reasoning": {"effort": "none"}, "usage": {"input_tokens": 3, "output_tokens": 2}})
            usage = model_usage(root, "high", "hermes")
            self.assertEqual(usage["request_kinds"], {"agent": 1, "session_title": 1, "context_compression": 0})
            self.assertEqual(usage["reported_tokens"]["input_tokens"], 23)

    def test_compression_requires_the_exact_native_tool_free_checkpoint_shape(self):
        prompt = "You are a summarization agent creating a context checkpoint.\n\nTURNS TO SUMMARIZE:\nsynthetic conversation"
        payload = {"instructions": "You are a helpful assistant.", "input": [
            {"role": "developer", "content": "current task"}, {"role": "user", "content": prompt}]}
        self.assertEqual(native_model_request_kind(payload, "hermes-session-1"), "context_compression")
        for changed, protocol in ((payload, "ga-session-1"),
            ({**payload, "tools": [{"name": "memory"}]}, "hermes-session-1"),
            ({**payload, "input": [{"role": "user", "content": "Review and save experience"}]}, "hermes-session-1"),
            ({**payload, "input": [{"role": "user", "content": prompt.split("\n\nTURNS")[0]}]}, "hermes-session-1")):
            self.assertEqual(native_model_request_kind(changed, protocol), "agent")

    def test_worker_preserves_native_compression_payload_and_still_rejects_missing_main_effort(self):
        checkpoint = {"instructions": "You are a helpful assistant.", "input": [{"role": "user", "content":
            "You are a summarization agent creating a context checkpoint.\n\nTURNS TO SUMMARIZE:\nfixture"}]}
        iterative_prompt = ("You are a summarization agent creating a context checkpoint."
            "\n\nYou are updating a context compaction summary. A previous compaction produced the summary below."
            "\n\nPREVIOUS SUMMARY:\nfixture summary\n\nNEW TURNS TO INCORPORATE:\nfixture new turns")
        iterative = {"instructions": "You are a helpful assistant.", "input": [
            {"role": "developer", "content": "current task"},
            {"role": "user", "content": [{"type": "input_text", "text": iterative_prompt}]}]}
        for label, payload, valid in (("fresh", checkpoint, True), ("iterative", iterative, True),
                ("main", {"instructions": "Review and save experience", "input": []}, False),
                ("with_tools", {**iterative, "tools": [{"name": "memory"}]}, False),
                ("missing_previous", {**iterative, "input": [{"role": "user", "content":
                    iterative_prompt.replace("\n\nPREVIOUS SUMMARY:\nfixture summary", "")}]}, False),
                ("missing_new_turns", {**iterative, "input": [{"role": "user", "content":
                    iterative_prompt.replace("\n\nNEW TURNS TO INCORPORATE:\nfixture new turns", "")}]}, False)):
            with self.subTest(shape=label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = root / "worker.py"
                script.write_text("import json,sys\nsys.stdin.readline()\n" +
                    "print(json.dumps({'kind':'request','id':1,'method':'model','params':" + repr(payload) + "}),flush=True)\n" +
                    "sys.stdin.readline()\nprint(json.dumps({'kind':'finished'}),flush=True)\n", encoding="utf-8")
                class Jail:
                    def command(self, *args, **kwargs):
                        return [sys.executable, "-u", str(script)]
                sessions = WorkerSessions(root, root, Jail(), model_alias="fixture", worker_protocol="hermes-session-1",
                    game_transport="legacy-rpc", reasoning_effort="high")
                received = []
                def model(value):
                    received.append(value)
                    return {"lines": []}
                report = sessions._worker(root, root, {"reasoning_effort": "high"}, model=model)
                self.assertEqual(report["infrastructure_ok"], valid)
                if valid:
                    self.assertEqual(received, [payload])
                    self.assertEqual(report["model_request_kinds"]["context_compression"], 1)
                else:
                    self.assertEqual(received, [])
                    self.assertIn("reasoning effort differs", report["infrastructure_error"])

    def test_offline_comparison_rejects_high_low_pair_and_accepts_legacy_low(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {c: root / c for c in ("retain", "clear")}
            common = dict.fromkeys(("agent", "model_alias", "seed", "world", "station_assignment_sha256", "map_configuration_sha256",
                "archive_sha256", "prompt_protocol", "feedback_protocol", "action_policy", "movement_mode", "max_turns", "final_turns", "wall_seconds"), "fixture")
            for condition, path in paths.items():
                path.mkdir()
                save_json(path / "pilot.json", {**common, "protocol": PROTOCOL, "status": "completed",
                    "memory_condition": condition, "experiment_id": condition, "tasks": ["T1"]})
                save_json(path / "analysis.json", {"experiment_id": condition, "rows": [{"task_id": "T1"}], "totals": {}, "successes": 1})
            self.assertEqual(compare(paths["retain"], paths["clear"])["reasoning_effort"], "low")
            pilot = json.loads((paths["retain"] / "pilot.json").read_text())
            pilot["reasoning_effort"] = "high"
            save_json(paths["retain"] / "pilot.json", pilot)
            with self.assertRaisesRegex(ValueError, "reasoning_effort"):
                compare(paths["retain"], paths["clear"])


if __name__ == "__main__":
    unittest.main()
