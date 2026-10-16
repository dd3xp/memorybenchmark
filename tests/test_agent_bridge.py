import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from memorybenchmark.agent_bridge import GAME_TOOL, GameTool, HTTPGameClient, register_genericagent, register_hermes
from memorybenchmark.server import make_server


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = make_server(port=0, log_root=Path(self.directory.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.started = self.server.service.start({"task_id": "T1"})
        self.client = HTTPGameClient(f"http://127.0.0.1:{self.server.server_port}", self.started["instance_id"])
        self.tool = GameTool(self.client)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.directory.cleanup()

    def test_tool_client_reads_takes_and_moves_using_public_interface(self):
        self.assertEqual(self.tool({"action":"read"})["observation"]["location"]["id"], "S")
        for target in ("J", "D"):
            self.tool({"action":"move", "target":target})
        taken = self.tool({"action":"take", "target":"snow_kit"})
        self.assertEqual(taken["observation"]["inventory"][0]["id"], "snow_kit")
        arrived = self.tool({"action":"move", "target":"A"})
        self.assertEqual(arrived["observation"]["effort"], 8)
        self.assertTrue(self.tool({"action":"submit"})["observation"]["success"])

    def test_unknown_tools_and_extra_arguments_do_not_change_state(self):
        game = self.server.service.adapter(self.started["instance_id"]).game
        snapshot = game.snapshot()
        for args in ({"action":"start"}, {"action":"move"}, {"action":"move","target":"J","extra":1}, {"action":"read","target":"J"}):
            self.assertIn("error", self.tool(args))
        self.assertEqual(snapshot, game.snapshot())

    def test_unused_empty_target_from_strict_gateway_is_accepted(self):
        game = self.server.service.adapter(self.started["instance_id"]).game
        before = game.steps
        for target in ("", None):
            result = self.tool({"action":"read", "target":target})
            self.assertEqual(result["outcome"],"read")
        self.assertEqual(game.steps,before)
        self.assertEqual(self.tool({"action":"submit","target":""})["outcome"],"incomplete")
        self.assertEqual(game.steps,before + 1)

    def test_hermes_registry_registration_preserves_native_memory_tools(self):
        entries = {"memory": object()}
        original = entries["memory"]
        registry = SimpleNamespace(register=lambda **kwargs: entries.update({kwargs["name"]:kwargs}))
        toolsets = []
        register_hermes(registry, lambda *a,**k:toolsets.append((a,k)), self.tool)
        result = json.loads(entries["game_action"]["handler"]({"action":"move", "target":"J"}))
        self.assertEqual(result["observation"]["location"]["id"], "J")
        self.assertIs(entries["memory"], original)
        self.assertEqual(toolsets[0][1]["tools"], ["game_action"])

    def test_genericagent_native_dispatch_contract_and_duplicate_registration(self):
        class Handler:
            def __init__(self, parent): self.parent = parent
        agent = SimpleNamespace()
        module = SimpleNamespace(GenericAgentHandler=Handler, TOOLS_SCHEMA=[{"type":"function","function":{"name":"file_read"}}])
        outcome = lambda data, next_prompt: SimpleNamespace(data=data,next_prompt=next_prompt)
        register_genericagent(module, agent, outcome, self.tool)
        register_genericagent(module, agent, outcome, self.tool)
        result = Handler(agent).do_game_action({"action":"move","target":"J","_index":0}, None)
        self.assertEqual(result.data["observation"]["location"]["id"], "J")
        self.assertEqual([e["function"]["name"] for e in module.TOOLS_SCHEMA], ["file_read","game_action"])
        self.assertEqual(json.loads(agent._submit_eval_cb(""))["outcome"], "incomplete")


if __name__ == "__main__":
    unittest.main()
