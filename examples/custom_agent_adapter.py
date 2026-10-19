"""Example lifecycle plugin for a user-written native worker bundle.

This is a template, not an additional evaluated agent. Bundle layout:
source/ (native code), baseline/ (native persistent defaults), support/agent_worker.py.
The worker must implement the documented agent-session-1 contract using its own
agent's loop and memory tools. No synthetic planner or prewritten game lessons.
"""
from pathlib import Path
import shutil

from memorybenchmark.agent_adapters import AgentAdapter, PreparedAgent
from memorybenchmark.ga_runtime import copy_memory


class CustomAgentAdapter(AgentAdapter):
    agent_id = "custom"
    label = "User-provided native agent"
    prompt_protocol = "custom-native-memory-1"

    def prepare(self, archive, root):
        bundle = Path(archive)
        source, support, baseline = root / "source/native", root / "support", root / "baseline"
        shutil.copytree(bundle / "source", source)
        shutil.copytree(bundle / "support", support)
        copy_memory(bundle / "baseline", baseline)
        return PreparedAgent(source, support, baseline)


def create_adapter():
    return CustomAgentAdapter()
