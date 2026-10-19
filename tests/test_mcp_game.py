"""Real SDK clients: public boundary, replay semantics and stdio interoperability."""
import asyncio
from contextlib import redirect_stderr
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.agent_adapters import load_adapter
from memorybenchmark.errors import AdapterError
from memorybenchmark.experiment import experiment, main
from memorybenchmark.game import Game
from memorybenchmark.game_session import dispatch_current
from memorybenchmark.mcp_game import GAME_TRANSPORT, MCPGameClient, SDK_VERSION

try:
    HAS_MCP = version("mcp") == SDK_VERSION
except PackageNotFoundError:
    HAS_MCP = False


class AdapterSelectionTests(unittest.TestCase):
    def test_unsupported_agent_stops_before_creating_run_or_calling_model(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with self.assertRaises(AdapterError):
                experiment(None, output, None, lambda *_: self.fail("model called"), agent="unsupported")
            self.assertFalse(output.exists())

    def test_missing_adapter_is_a_cli_setup_error_without_credentials_or_wsl(self):
        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as ended:
            main(["--agent", "unsupported"])
        self.assertEqual(ended.exception.code, 2)
        self.assertIn("尚未适配", error.getvalue())
        self.assertNotIn("GATEWAY_KEY", error.getvalue())

    def test_hermes_tool_bridge_is_not_advertised_as_a_complete_adapter(self):
        with self.assertRaisesRegex(AdapterError, "完整评测适配器尚未提供"):
            load_adapter("hermes")

    def test_explicit_user_plugin_can_reuse_the_shared_lifecycle_runner(self):
        plugin = load_adapter("custom", "examples.custom_agent_adapter:create_adapter")
        self.assertEqual(plugin.worker_protocol, "agent-session-1")
        self.assertEqual(plugin.worker_filename, "agent_worker.py")
        with self.assertRaises(AdapterError):
            load_adapter("wrong", "examples.custom_agent_adapter:create_adapter")
        with self.assertRaises(AdapterError):
            load_adapter("custom", "examples.custom_agent_adapter:missing_factory")


@unittest.skipUnless(HAS_MCP, 'install the mcp extra to run real SDK integration tests')
class MCPGameTests(unittest.TestCase):
    def start(self, scenario="valley", task="T1"):
        game = Game(scenario=scenario)
        adapter = GameAdapter(game)
        adapter.dispatch({"command": "start", "task_id": task})
        return game, adapter

    def test_mcp_and_direct_actions_produce_identical_public_results_and_graph_costs(self):
        direct, adapter = self.start()
        remote, remote_adapter = self.start()
        # IDs are generated per instance; compare all remaining public fields.
        def normalized(result):
            result = deepcopy(result)
            result["observation"].pop("task_run_id")
            return result
        with MCPGameClient(lambda r: dispatch_current(remote_adapter, r)) as client:
            self.assertEqual(client.identity["game_transport"], GAME_TRANSPORT)
            for number, action in enumerate((
                    {"type": "move", "target": "J"}, {"type": "move", "target": "D"},
                    {"type": "take", "target": "snow_kit"}, {"type": "move", "target": "A"},
                    {"type": "submit"})):
                request = {"command": "action", "request_id": f"same-{number}", "action": action}
                self.assertEqual(normalized(client(request)), normalized(dispatch_current(adapter, request)))
            self.assertTrue(remote.success)
            self.assertEqual((remote.steps, remote.distance, remote.effort),
                             (direct.steps, direct.distance, direct.effort))

    def test_action_metadata_preserves_exact_replays_and_rejects_stale_revisions(self):
        game, adapter = self.start()
        with MCPGameClient(lambda r: dispatch_current(adapter, r)) as client:
            request = {"command": "action", "request_id": "retry-1", "expected_revision": game.revision,
                       "action": {"type": "move", "target": "J"}}
            first = client(request)
            self.assertEqual(client(request), first)
            self.assertEqual(game.steps, 1)
            stale = {**request, "request_id": "different", "action": {"type": "move", "target": "A"}}
            self.assertIn("error", client(stale))
            self.assertEqual(game.steps, 1)

    def test_only_bound_task_is_available_and_closed_game_cannot_be_advanced(self):
        game, adapter = self.start()
        before = game.snapshot()
        with MCPGameClient(lambda r: dispatch_current(adapter, r)) as client:
            for request in ({"command": "start", "task_id": "T6"},
                            {"command": "read", "instance_id": "other"},
                            {"command": "action", "action": {"type": "checkpoint"}}):
                self.assertIn("error", client(request))
            self.assertEqual(game.snapshot(), before)
            client({"command": "action", "action": {"type": "abandon"}})
            closed = game.snapshot()
            result = client({"command": "action", "action": {"type": "move", "target": "J"}})
            self.assertEqual(result["outcome"], "closed")
            self.assertEqual(game.snapshot(), closed)

    def test_stdio_service_with_an_unmodified_official_client_and_host_only_logs(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "host-log"

            async def run():
                parameters = StdioServerParameters(command=sys.executable, args=[
                    "-m", "memorybenchmark.mcp_server", "--scenario", "valley", "--task", "T1",
                    "--output", str(output)], cwd=Path(__file__).resolve().parents[1])
                async with stdio_client(parameters) as streams:
                    async with ClientSession(*streams) as client:
                        await client.initialize()
                        listed = await client.list_tools()
                        self.assertEqual([tool.name for tool in listed.tools], ["game_action"])
                        result = await client.call_tool("game_action", {"action": "read"})
                        public = result.structuredContent
                        self.assertEqual(public["observation"]["task_id"], "T1")
                        self.assertNotIn("snow_kit", json.dumps(public))
                        for target in ("J", "A"):
                            result = await client.call_tool("game_action", {"action": "move", "target": target})
                        result = await client.call_tool("game_action", {"action": "submit"})
                        self.assertTrue(result.structuredContent["observation"]["success"])
                        bad = await client.call_tool("game_action", {"action": "read", "task_id": "T8"})
                        self.assertTrue(bad.isError)
                        bad = await client.call_tool("reveal_world", {})
                        self.assertTrue(bad.isError)

            asyncio.run(run())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertTrue(summary["success"])
            self.assertEqual(summary["game_actions"], 3)
            self.assertTrue((output / "events.jsonl").is_file())
            self.assertTrue((output / "graph.json").is_file())


if __name__ == "__main__":
    unittest.main()
