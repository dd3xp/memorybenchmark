import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from memorybenchmark.agent_adapters import load_adapter
from memorybenchmark.agent_bridge import GameTool, register_hermes
from memorybenchmark.ga_runtime import extract_native, filesystem_path, copy_memory, memory_manifest
from memorybenchmark.model_gateway import GatewayModel
from memorybenchmark.prototypes.station_pilot import STATION_TOOL


class NativeUpgradeTests(unittest.TestCase):
    def archive(self, root, prefix, files):
        archive = root / "source.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, content in files.items():
                data = content.encode()
                member = tarfile.TarInfo(prefix + "/" + name)
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
        return archive

    def test_codeload_ga_root_is_normalized_without_importing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict.fromkeys(("agentmain.py", "agent_loop.py", "ga.py", "memory/memory_management_sop.md"), "fixture")
            files.update({"mykey.py": "not a runtime credential", ".env": "not copied"})
            archive = self.archive(root, "GenericAgent-" + "a" * 40, files)
            source = extract_native(archive, root / "source")
            self.assertEqual(source.name, "GenericAgent")
            self.assertFalse((source / "mykey.py").exists())
            self.assertFalse((source / ".env").exists())

    def test_hermes_baseline_excludes_source_conversations_and_user_memories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = dict.fromkeys(("run_agent.py", "tools/memory_tool.py", "agent/conversation_loop.py"), "fixture")
            files.update({"sessions/old.json": "old transcript", "memories/MEMORY.md": "old facts"})
            archive = self.archive(root, "hermes-agent-" + "b" * 40, files)
            run = root / "run"
            run.mkdir()
            prepared = load_adapter("hermes").prepare(archive, run)
            prepared.validate(run, "hermes_worker.py")
            self.assertFalse(list((prepared.baseline / "memories").iterdir()))
            self.assertFalse((prepared.baseline / "sessions").exists())

    def test_hermes_bridge_exposes_station_actions_instead_of_legacy_equipment_schema(self):
        registrations = []
        registry = SimpleNamespace(register=lambda **kwargs: registrations.append(kwargs))
        tool = GameTool(lambda request: {"request": request}, definition=STATION_TOOL, target_actions=("move",))
        handler = register_hermes(registry, lambda *args, **kwargs: None, tool)
        enum = registrations[0]["schema"]["parameters"]["properties"]["action"]["enum"]
        self.assertIn("inspect", enum)
        self.assertNotIn("take", enum)
        self.assertEqual(json.loads(handler({"action": "inspect"}))["request"]["action"]["type"], "inspect")

    def test_deep_skill_paths_survive_complete_memory_snapshot(self):
        # The cleanup path must also use Windows extended syntax; otherwise
        # Python's TemporaryDirectory can leave a correctly copied deep tree.
        with tempfile.TemporaryDirectory(dir=filesystem_path(tempfile.gettempdir())) as directory:
            root = Path(directory)
            source = root / "baseline"
            relative = Path(*(["long-native-skill-directory"] * 8)) / "SKILL.md"
            path = filesystem_path(source / relative)
            path.parent.mkdir(parents=True)
            path.write_text("native skill fixture", encoding="utf-8")
            copy_memory(source, root / "retained")
            self.assertEqual(memory_manifest(source), memory_manifest(root / "retained"))

    def test_gateway_preserves_hermes_native_system_instructions(self):
        captured = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self):
                return iter([b'data: {"type":"response.completed"}\n'])
        def urlopen(request, **kwargs):
            captured.append(json.loads(request.data))
            return Response()
        with patch("memorybenchmark.model_gateway.urlopen", urlopen):
            GatewayModel("https://fixture.invalid", "dummy", "fixture", None)(
                {"instructions": "native memory and rules", "input": [], "tools": [],
                 "include": ["reasoning.encrypted_content"], "tool_choice": "none",
                 "previous_response_id": "must-not-cross-session"})
        self.assertEqual(captured[0]["instructions"], "native memory and rules")
        self.assertEqual(captured[0]["include"], ["reasoning.encrypted_content"])
        self.assertEqual(captured[0]["tool_choice"], "none")
        self.assertNotIn("previous_response_id", captured[0])
        self.assertFalse(captured[0]["store"])


if __name__ == "__main__":
    unittest.main()
