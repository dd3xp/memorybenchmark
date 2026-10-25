"""Public tool interoperability and actual-history checkpoint isolation."""
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memorybenchmark.agent_bridge import GameTool, register_genericagent
from memorybenchmark.mcp_game import MCPGameClient, SDK_VERSION
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.errors import InfrastructureError
from memorybenchmark.ga_runtime import copy_memory
from memorybenchmark.prototypes.station_pilot import STATION_TOOL, pilot, replay_checkpoint
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN, StationSession

try:
    HAS_MCP = version("mcp") == SDK_VERSION
except PackageNotFoundError:
    HAS_MCP = False


class StationNativeTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design(DEFAULT_DESIGN)
        self.game = StationGame("omega_00", self.design)
        self.session = StationSession(self.game, "T1")

    @unittest.skipUnless(HAS_MCP, "install the mcp extra for real SDK interoperability")
    def test_real_mcp_schema_handles_processing_without_legacy_tool_actions(self):
        with MCPGameClient(self.session.dispatch, definition=STATION_TOOL, target_actions=("move",)) as client:
            tool = GameTool(client, definition=STATION_TOOL, target_actions=("move",))
            initial = tool({"action": "read"})
            self.assertNotIn("private_worlds", json.dumps(initial))
            self.assertNotIn("omega_00", json.dumps(initial))
            for action in [{"action": "move", "target": n} for n in ("J", "P", "J", "A")]:
                self.assertNotIn("error", tool(action))
            self.assertEqual(tool({"action": "process", "target": ""})["feedback"]["result"], "processed")
            before = deepcopy(self.game.events)
            self.assertIn("error", tool({"action": "take", "target": "x"}))
            self.assertIn("error", client({"command": "start", "task_id": "T2"}))
            self.assertEqual(before, self.game.events)
            for n in ("J", "C"):
                tool({"action": "move", "target": n})
            self.assertTrue(tool({"action": "submit"})["observation"]["success"])

    def test_native_registration_uses_environment_schema(self):
        class Handler:
            pass
        module = SimpleNamespace(GenericAgentHandler=Handler, TOOLS_SCHEMA=[])
        tool = GameTool(self.session.dispatch, definition=STATION_TOOL, target_actions=("move",))
        register_genericagent(module, SimpleNamespace(), lambda *a, **k: None, tool)
        self.assertEqual(module.TOOLS_SCHEMA[0]["function"], STATION_TOOL)

    def test_host_termination_creates_no_fake_action_or_edge_and_replays_exactly(self):
        for node in ("J", "A"):
            self.game.step({"type": "move", "target": node})
        self.game.step({"type": "inspect"})
        self.game.finish_incomplete("model_budget")
        self.assertEqual((self.game.steps, self.game.distance), (3, 3))
        self.assertTrue(self.game.done)
        self.assertFalse(self.game.state.success)
        self.assertEqual(self.game.events[-1]["kind"], "runner_terminated")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "summary.json").write_text(json.dumps({"task_id": "T1"}), encoding="utf-8")
            (path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in self.game.events), encoding="utf-8")
            restored = replay_checkpoint(self.design, "omega_00", [path])
            self.assertEqual(restored.events, self.game.events)
            StationSession(restored, "T2")
            self.assertFalse(restored.state.raw)
            self.assertFalse(restored.state.processed)
            self.assertNotIn("capability", restored.events[-1]["delivered"]["feedback"])

    def test_resume_archives_infrastructure_attempt_without_repeating_successful_branches(self):
        calls = []
        class FixtureSessions:
            def __init__(self, *args, **kwargs):
                pass
            def probe(self, baseline, output):
                output.mkdir()
                (output / "summary.json").write_text("{}")
            def run(self, game, task, memory, output, model, *, condition):
                calls.append((task, condition))
                output.mkdir(parents=True)
                game.start_task(task)
                failed = (task, condition) == ("T2", "clear") and calls.count((task, condition)) == 1
                if not failed:
                    game.step({"type": "abandon"})
                    copy_memory(memory, output / "memory-after")
                result = {"task_id": task, "success": False if not failed else None, "distance": 0,
                          "llm_calls": 0, "content_changed": [], "infrastructure_ok": not failed}
                (output / "summary.json").write_text(json.dumps(result))
                (output / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in game.events))
                return result
        def source_fixture(archive, destination):
            source = destination / "GenericAgent"
            (source / "memory").mkdir(parents=True)
            (source / "memory" / "fixture.txt").write_text("native baseline fixture")
            return source
        def support_fixture(destination):
            destination.mkdir()
            return destination
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.tar"
            archive.write_bytes(b"synthetic archive fixture")
            output = root / "pilot"
            with patch("memorybenchmark.prototypes.station_pilot.extract_native", source_fixture), \
                 patch("memorybenchmark.prototypes.station_pilot.make_support", support_fixture), \
                 patch("memorybenchmark.prototypes.station_pilot.StationNativeSessions", FixtureSessions):
                with self.assertRaises(InfrastructureError):
                    pilot(archive, output, None, None, tasks=["T1", "T2", "T3"])
                report = pilot(archive, output, None, None, resume=True)
            self.assertEqual(report["status"], "completed")
            self.assertEqual(len(report["sessions"]), 5)
            self.assertEqual(len(report["attempt_history"]), 1)
            self.assertEqual(calls.count(("T1", "prefix")), 1)
            self.assertEqual(calls.count(("T2", "retain")), 1)
            self.assertEqual(calls.count(("T2", "clear")), 2)


if __name__ == "__main__":
    unittest.main()
