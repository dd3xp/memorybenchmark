"""Check bundled native dispatch code without an LLM or private source publication.

Usage: python scripts/check_native_contracts.py <legacy-archives-directory>
This verifies tool contracts, not full agent startup, isolation or memory.
"""
import argparse
from pathlib import Path
import sys
import tarfile
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memorybenchmark.agent_bridge import GameTool, register_genericagent, register_hermes
from memorybenchmark.adapters import GameAdapter
from memorybenchmark.game import Game


def source_module(archive, member, name):
    with tarfile.open(archive) as bundle:
        source = bundle.extractfile(member).read().decode("utf-8")
    module = types.ModuleType(name)
    module.__file__ = member
    sys.modules[name] = module
    exec(compile(source, member, "exec"), module.__dict__)
    return module


def check(directory):
    def tool():
        adapter = GameAdapter(Game())
        adapter.dispatch({"command":"start", "task_id":"T1"})
        return GameTool(adapter.dispatch)

    hermes = source_module(directory / "hermes-agent_src.tar.xz", "hermes-agent/tools/registry.py", "_bench_native_hermes_registry")
    registry = hermes.ToolRegistry()
    register_hermes(registry, lambda *args,**kwargs:None, tool())
    import json
    result = json.loads(registry.get_entry("game_action").handler({"action":"move","target":"J"}))
    assert result["observation"]["location"]["id"] == "J"
    ga = source_module(directory / "GenericAgent_src.tar.xz", "GenericAgent/agent_loop.py", "_bench_native_ga_loop")
    class Handler(ga.BaseHandler):
        def __init__(self, parent): self.parent = parent
    parent = types.SimpleNamespace()
    module = types.SimpleNamespace(GenericAgentHandler=Handler, TOOLS_SCHEMA=[])
    register_genericagent(module, parent, ga.StepOutcome, tool())
    generator = Handler(parent).dispatch("game_action", {"action":"move","target":"J"}, None)
    result = ga.exhaust(generator)
    assert result.data["observation"]["location"]["id"] == "J"
    return {"hermes_native_registry":"passed", "genericagent_native_base_dispatch":"passed", "llm_calls":0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    print(check(parser.parse_args().directory))
