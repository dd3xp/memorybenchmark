"""Native Hermes lifecycle; curated memory and self-authored skills persist."""
from pathlib import Path
import shutil

from ..agent_adapters import AgentAdapter, PreparedAgent
from ..ga_runtime import extract_native, copy_memory


class HermesAdapter(AgentAdapter):
    agent_id = "hermes"
    label = "native_Hermes"
    prompt_protocol = "cartography-native-memory-3"
    task_anchor = "public_current_task_on_every_model_call"
    worker_protocol = "hermes-session-1"
    worker_filename = "hermes_worker.py"

    def prepare(self, archive, root):
        source = extract_native(archive, root / "source", native="hermes")
        baseline = root / "baseline"
        baseline.mkdir()
        # Native curated stores start empty; preserve the shipped skill library
        # as normal first-install defaults, without any game-specific knowledge.
        (baseline / "memories").mkdir()
        (baseline / ".curator_backups").mkdir()
        if (source / "skills").is_dir():
            copy_memory(source / "skills", baseline / "skills")
        else:
            (baseline / "skills").mkdir()
        support = root / "support"
        support.mkdir()
        for name in ("hermes_worker.py", "ga_worker.py", "agent_bridge.py"):
            shutil.copyfile(Path(__file__).parents[1] / name, support / name)
        return PreparedAgent(source, support, baseline)
