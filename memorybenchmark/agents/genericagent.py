"""GenericAgent-specific preparation and native worker selection only."""
from ..agent_adapters import AgentAdapter, PreparedAgent
from ..ga_runtime import copy_memory, extract_native, make_support
from ..ga_worker import PROMPT_PROTOCOL


class GenericAgentAdapter(AgentAdapter):
    agent_id = "ga"
    label = "bundled_GenericAgent"
    prompt_protocol = PROMPT_PROTOCOL
    task_anchor = "public_current_task_on_every_model_call"
    worker_protocol = "ga-session-1"
    worker_filename = "ga_worker.py"

    def prepare(self, archive, root):
        source = extract_native(archive, root / "source")
        baseline = root / "baseline"
        copy_memory(source / "memory", baseline)
        return PreparedAgent(source, make_support(root / "support"), baseline)

    def create_sessions(self, prepared, jail, report, observer=None):
        from ..ga_experiment import NativeGASessions
        return NativeGASessions(prepared.source, prepared.support, jail,
            model_alias=report["model_alias"], max_turns=report["max_turns"],
            final_turns=report["final_turns"], seed=report["seed"], observer=observer,
            prompt_protocol=report.get("prompt_protocol", "optional-memory-1"),
            game_transport=report.get("game_transport", "legacy-rpc"))
