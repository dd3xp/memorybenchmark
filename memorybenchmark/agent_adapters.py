"""Agent lifecycle plugins. Game rules and memory intervention live in the runner."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import importlib
import inspect
from pathlib import Path
import re

from .errors import AdapterError


ADAPTER_PROTOCOL = "agent-adapter-1"


@dataclass(frozen=True)
class PreparedAgent:
    source: Path
    support: Path
    baseline: Path

    def validate(self, root, worker_filename):
        root = Path(root).resolve()
        for path in (self.source, self.support, self.baseline):
            if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(root):
                raise AdapterError("agent source, support and baseline must be real directories inside the run")
        directories = [path.resolve() for path in (self.source, self.support, self.baseline)]
        if any(left.is_relative_to(right) or right.is_relative_to(left)
               for index, left in enumerate(directories) for right in directories[index + 1:]):
            raise AdapterError("source, support and baseline must be separate directories")
        if self.baseline.resolve() != root / "baseline":
            raise AdapterError("baseline must use the shared runner's baseline directory")
        if not (self.support / worker_filename).is_file():
            raise AdapterError("adapter worker is missing")
        return self


class AgentAdapter(ABC):
    """A plugin prepares native code and selects a native worker, never lessons.

    The worker contract is documented in docs/AGENT_INTEGRATION.md. The shared
    WorkerSessions handles a new process per task, game MCP access, budgets,
    complete persistent-directory checkpoints, clear controls and rollback.
    """
    adapter_protocol = ADAPTER_PROTOCOL
    agent_id = ""
    label = ""
    version = "1"
    prompt_protocol = "agent-native-memory-1"
    task_anchor = "public_current_task_in_game_feedback"
    worker_protocol = "agent-session-1"
    worker_filename = "agent_worker.py"

    @abstractmethod
    def prepare(self, archive, root):
        """Return PreparedAgent under root; baseline includes only native defaults."""

    def create_sessions(self, prepared, jail, report, observer=None):
        from .agent_sessions import WorkerSessions
        return WorkerSessions(prepared.source, prepared.support, jail,
            worker_protocol=self.worker_protocol, worker_filename=self.worker_filename,
            model_alias=report["model_alias"], max_turns=report["max_turns"],
            final_turns=report["final_turns"], seed=report["seed"], observer=observer,
            prompt_protocol=report["prompt_protocol"], game_transport=report["game_transport"])


def load_adapter(agent_id, factory=None):
    """Explicit user-supplied Python plugins; no silent bare-model fallback."""
    if not isinstance(agent_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", agent_id):
        raise AdapterError("agent ID must use lowercase letters, digits, underscores or hyphens")
    if factory is None:
        if agent_id == "ga":
            from .agents.genericagent import GenericAgentAdapter
            adapter = GenericAgentAdapter()
        elif agent_id == "hermes":
            raise AdapterError("Hermes 尚只有工具注册桥，完整评测适配器尚未提供；不能作为零分运行。")
        else:
            raise AdapterError(f"agent '{agent_id}' 尚未适配；请用 --adapter your_module:create_adapter 提供适配器。")
    else:
        module, separator, attribute = factory.partition(":")
        if not separator or not module or not attribute.isidentifier():
            raise AdapterError("--adapter must be an importable module:factory")
        try:
            creator = getattr(importlib.import_module(module), attribute)
            adapter = creator()
        except Exception as error:
            # Plugin code is explicitly selected by the user. Keep arbitrary
            # plugin exception contents (possibly configuration) out of logs.
            raise AdapterError(f"无法加载 agent 适配器：{type(error).__name__}") from None
    if not isinstance(adapter, AgentAdapter) or adapter.adapter_protocol != ADAPTER_PROTOCOL:
        raise AdapterError("adapter must implement AgentAdapter / agent-adapter-1")
    if adapter.agent_id != agent_id or not adapter.label:
        raise AdapterError("adapter agent_id must match --agent and provide a label")
    if not all(isinstance(value, str) and value for value in (
            adapter.version, adapter.worker_protocol, adapter.prompt_protocol, adapter.task_anchor)):
        raise AdapterError("adapter must declare version, worker protocol, prompt protocol and task visibility")
    if Path(adapter.worker_filename).name != adapter.worker_filename or not adapter.worker_filename.endswith(".py"):
        raise AdapterError("adapter worker_filename must be a Python filename")
    return adapter


def adapter_identity(adapter, factory=None):
    modules = {type(adapter).__module__}
    if factory:
        modules.add(factory.partition(":")[0])
    sources = {}
    for name in sorted(modules):
        path = inspect.getsourcefile(importlib.import_module(name))
        if path is None:
            raise AdapterError("adapter must provide inspectable Python source for reproducibility")
        sources[name] = sha256(Path(path).read_bytes()).hexdigest()
    return {"protocol": ADAPTER_PROTOCOL, "agent_id": adapter.agent_id,
            "version": adapter.version, "factory": factory, "sources": sources,
            "worker_protocol": adapter.worker_protocol, "worker_filename": adapter.worker_filename}


def available_adapters():
    return [{"agent": "ga", "status": "ready", "native_memory": True},
            {"agent": "hermes", "status": "tool_bridge_only", "native_memory": None}]
