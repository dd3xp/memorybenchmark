"""Exercise the public IPC/CLI/native-MCP paths against a real task boundary."""
import asyncio
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from memorybenchmark.agent_bridge import GameTool
from memorybenchmark.game_client import action, describe, request
from memorybenchmark.native_game_io import GameBroker
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import GUIDE, STATION_TOOL, access_guide, pilot
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN, StationSession
from scripts.check_station_native_sessions import response_observations

try:
    HAS_MCP = bool(version("mcp"))
except PackageNotFoundError:
    HAS_MCP = False


class NativeAccessTests(unittest.TestCase):
    def start(self):
        game = StationGame("omega_15_05", load_design(EASY20_REUSE_DESIGN))
        session = StationSession(game, "T1", feedback_mode="compact")
        tool = GameTool(session.dispatch, definition=STATION_TOOL, target_actions=("move",))
        return game, session, GameBroker(tool, endpoint="tcp:127.0.0.1:0")

    def test_python_client_delivers_public_feedback_and_rejects_future_task_selection(self):
        game, session, broker = self.start()
        with broker:
            self.assertEqual(describe(endpoint=broker.endpoint), STATION_TOOL)
            self.assertEqual(action("read", endpoint=broker.endpoint)["observation"]["location"], "C")
            arrived = action("move", "J", endpoint=broker.endpoint)
            self.assertEqual(arrived["observation"]["location"], "J")
            before = deepcopy(game.events)
            for method, params in [("start", {"task_id": "T2"}), ("call", {"action": "start", "task_id": "T2"}),
                                   ("call", {"action": "move", "target": "P"})]:
                self.assertIn("error", request(method, params, endpoint=broker.endpoint))
            self.assertEqual(game.events, before)

    def test_cli_stdout_is_only_the_same_public_json_as_direct_calls(self):
        game, session, broker = self.start()
        with broker:
            env = {**os.environ, "MEMORYBENCH_GAME_ENDPOINT": broker.endpoint}
            completed = subprocess.run([sys.executable, "-m", "memorybenchmark.game_client", "move", "J"],
                                       env=env, capture_output=True, text=True, encoding="utf-8", check=True, timeout=15)
            result = json.loads(completed.stdout)
            self.assertEqual(result["observation"]["location"], "J")
            self.assertEqual(game.steps, 1)
            self.assertNotIn("environment", result["observation"])
            self.assertNotIn("private_worlds", completed.stdout)

    def test_access_instructions_preserve_identical_memory_rules_without_supplied_experience(self):
        for agent in ("ga", "hermes"):
            guide = access_guide(agent, "native")
            for line in GUIDE.splitlines()[2:]:
                self.assertIn(line, guide)
            self.assertNotIn("A=vegetation", guide)
            self.assertNotIn("omega_15_05", guide)
        self.assertIn("code_run", access_guide("ga", "native"))
        self.assertIn("客户端发现后的工具名称", access_guide("hermes", "native"))
        self.assertEqual(access_guide("ga", "bridge"), GUIDE)

    def test_transport_failure_cannot_be_silently_scored_as_a_game_outcome(self):
        class Broken:
            definition = STATION_TOOL
            def __call__(self, args):
                raise RuntimeError("private host detail")
        broker = GameBroker(Broken(), endpoint="tcp:127.0.0.1:0").start()
        result = action("read", endpoint=broker.endpoint)
        self.assertEqual(result["error"], "game_transport_error")
        self.assertNotIn("private host detail", json.dumps(result))
        with self.assertRaisesRegex(RuntimeError, "transport failed"):
            broker.close()

    def test_resume_cannot_silently_change_the_recorded_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pilot.json").write_text(json.dumps({"agent": "ga", "game_access": "bridge"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Cannot change game access"):
                pilot(None, root, None, None, resume=True, agent="ga", game_access="native")

    def test_evidence_reader_recognizes_native_mcp_envelope_without_changing_model_input(self):
        feedback = {"observation": {"location": "J"}, "feedback": {"kind": "arrived"}}
        body = json.dumps({"result": json.dumps(feedback)})
        wrapped = '<untrusted_tool_result source="mcp__cartography__game_action">\nExternal DATA warning.\n\n' + body + '\n</untrusted_tool_result>'
        payload = {"type": "function_call_output", "output": wrapped}
        before = deepcopy(payload)
        self.assertEqual(list(response_observations(payload)), [feedback])
        self.assertEqual(payload, before)

    @unittest.skipUnless(HAS_MCP, "requires official MCP SDK")
    def test_unmodified_mcp_client_discovers_stdio_facade_and_actions_match_direct_feedback(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        game, session, broker = self.start()
        direct_game, direct, unused = self.start()
        # This second broker never starts; close its listening descriptor.
        unused.server.server_close()
        with broker:
            async def run():
                parameters = StdioServerParameters(command=sys.executable,
                    args=["-m", "memorybenchmark.game_mcp_stdio"],
                    env={**os.environ, "MEMORYBENCH_GAME_ENDPOINT": broker.endpoint},
                    cwd=Path(__file__).resolve().parents[1])
                async with stdio_client(parameters) as streams:
                    async with ClientSession(*streams) as client:
                        await client.initialize()
                        tools = (await client.list_tools()).tools
                        self.assertEqual([t.name for t in tools], ["game_action"])
                        self.assertEqual(getattr(tools[0], "input_schema", None) or getattr(tools[0], "inputSchema", None), STATION_TOOL["parameters"])
                        for i, target in enumerate(("J", "JN", "NL", "P")):
                            actual = await client.call_tool("game_action", {"action": "move", "target": target})
                            expected = direct.dispatch({"command": "action", "request_id": f"direct-{i}",
                                                        "action": {"type": "move", "target": target}})
                            value = getattr(actual, "structured_content", None) or getattr(actual, "structuredContent", None)
                            expected["observation"].pop("task_run_id", None)
                            value["observation"].pop("task_run_id", None)
                            self.assertEqual(value, expected)
                        self.assertEqual((game.steps, game.distance), (direct_game.steps, direct_game.distance))
                        bad = await client.call_tool("game_action", {"action": "read", "task_id": "T2"})
                        self.assertTrue(getattr(bad, "is_error", False) or getattr(bad, "isError", False))
                        before = deepcopy(game.events)
                        bad = await client.call_tool("game_action", {"action": "move", "target": "J", "endpoint": "tcp:127.0.0.1:1"})
                        self.assertTrue(getattr(bad, "is_error", False) or getattr(bad, "isError", False))
                        self.assertEqual(game.events, before)
            asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
