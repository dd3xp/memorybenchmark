"""Native Hermes session in the common jail; only curated storage survives.

HTTP interception changes transport only. Hermes still builds prompts, selects
tools, updates memory, manages skills and parses the native Responses stream.
"""
import json
from copy import deepcopy
import os
from pathlib import Path
import random
import sys
import threading
import time
from uuid import uuid4

from ga_worker import (Wire, LogSink, probe, pin_task_reminder, build_task_reminder,
                       ModelBudgetExhausted, run_environment_task, exhaust_native_loop,
                       FINAL_OPPORTUNITY, GUIDE, EXECUTION_PROTOCOL, PROMPT_PROTOCOL)

PROTOCOL = "hermes-session-1"


def main():
    wire = Wire()
    config = json.loads(wire.input.readline())
    if config.get("protocol") != PROTOCOL:
        raise RuntimeError("protocol mismatch")
    sys.stdout = sys.stderr = LogSink(wire)
    random.seed(config["seed"])
    isolation = probe()
    if config.get("probe_only"):
        wire.emit("finished", isolation=isolation)
        return

    # Session databases, logs, caches, configuration and transcript recall are
    # recreated in tmpfs. Native curated memory and skill contents alone persist.
    native_home = Path("/tmp/hermes")
    native_home.mkdir()
    workspace = Path("/tmp/workspace")
    workspace.mkdir()
    Path("/tmp/memory").symlink_to("/agent/memory", target_is_directory=True)
    os.chdir(workspace)
    for name in ("memories", "skills", ".curator_backups"):
        (native_home / name).symlink_to(Path("/agent/memory") / name, target_is_directory=True)
    Path("/agent/temp/memory").symlink_to("/agent/memory", target_is_directory=True)
    os.environ.update(HERMES_HOME=str(native_home), OPENAI_API_KEY="runner-managed",
                      OPENAI_BASE_URL="https://model.invalid/v1", TERMINAL_CWD=str(workspace))
    native_config = {
        "model": {"default": config["model"], "provider": "custom",
                  "base_url": "https://model.invalid/v1", "context_length": 64000},
        "terminal": {"backend": "local", "cwd": str(workspace)},
    }
    # JSON is valid YAML; no config library or model-written configuration needed.
    (native_home / "config.yaml").write_text(json.dumps(native_config), encoding="utf-8")
    reminder = config.get("task_reminder") or build_task_reminder(config["task_observation"])
    finalizing = False
    in_final_opportunity = False
    phase_calls = {"main": 0, "final": 0}
    transport_lock = threading.RLock()
    import httpx
    original_send = httpx.Client.send

    def send(client, request, *args, **kwargs):
        if str(request.url) != "https://model.invalid/v1/responses":
            # The jail blocks all external networking. Never redirect arbitrary
            # native requests to the authenticated model gateway.
            return original_send(client, request, *args, **kwargs)
        with transport_lock:
            phase = "final" if in_final_opportunity else "main"
            limit = config["final_turns"] if in_final_opportunity else config["max_turns"]
            if phase_calls[phase] >= limit:
                raise ModelBudgetExhausted()
            phase_calls[phase] += 1
            payload = pin_task_reminder(json.loads(request.content), reminder, finalizing=finalizing)
            result = wire.call("model", payload)
            content = "\n".join(result["lines"]) + "\n\n"
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  content=content.encode("utf-8"), request=request)

    httpx.Client.send = send
    from agent_bridge import GameTool, register_hermes
    from tools.registry import registry
    from toolsets import create_custom_toolset

    def game_request(request):
        nonlocal finalizing
        result = wire.call("game", request)
        if result.get("observation", {}).get("done"):
            finalizing = True
        return result

    register_hermes(registry, create_custom_toolset, GameTool(game_request,
        definition=config.get("game_tool"), target_actions=config.get("game_target_actions", ("move", "take"))))

    # Wait for native review writes before changing phases or taking snapshots;
    # review calls share the same host budgets and audited model transport.
    from agent import background_review
    original_spawn = background_review.spawn_background_review_thread
    reviews = []
    reviews_lock = threading.Lock()

    def spawn(*args, **kwargs):
        target, prompt = original_spawn(*args, **kwargs)
        finished = threading.Event()
        with reviews_lock:
            reviews.append(finished)
        def tracked():
            try:
                target()
            except ModelBudgetExhausted:
                wire.emit("review_budget_exhausted", phase="final" if in_final_opportunity else "main")
            finally:
                finished.set()
        return tracked, prompt

    background_review.spawn_background_review_thread = spawn

    def drain_reviews():
        deadline = time.monotonic() + 100
        while True:
            with reviews_lock:
                pending = [event for event in reviews if not event.is_set()]
            if not pending:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("native background review did not finish")
            pending[0].wait(timeout=0.2)

    from run_agent import AIAgent
    from hermes_state import SessionDB
    session_db = SessionDB(db_path=native_home / "state.db")
    session_id = "memorybenchmark-" + uuid4().hex

    def tool_started(call_id, name, args=None, *unused, **kwargs):
        wire.emit("tool", name=str(name), args=args if isinstance(args, dict) else {}, response_text="")

    agent = AIAgent(base_url="https://model.invalid/v1", api_key="runner-managed", provider="custom",
        api_mode="codex_responses", model=config["model"], max_iterations=100000,
        enabled_toolsets=["terminal", "file", "memory", "skills", "session_search", "todo", "cartography"],
        quiet_mode=True, verbose_logging=False, session_id=session_id, session_db=session_db,
        platform="benchmark", skip_context_files=False, skip_memory=False, skip_background_review=False,
        load_soul_identity=False, pass_session_id=True, reasoning_config={"effort": "low"},
        tool_start_callback=tool_started, cwd=str(workspace))
    # Avoid SDK retries hiding unrecorded provider attempts; transport failures
    # are infrastructure errors, never task scores.
    # Hermes counts total attempts here (zero means do not call the provider).
    agent._api_max_retries = 1
    history = []
    latest_native_history = []
    native_build = agent._build_api_kwargs
    def build_api_kwargs(api_messages, *args, **kwargs):
        nonlocal latest_native_history
        latest_native_history = deepcopy(api_messages)
        return native_build(api_messages, *args, **kwargs)
    agent._build_api_kwargs = build_api_kwargs
    guide = config.get("game_guide", GUIDE)
    wire.emit("session", protocol=PROTOCOL, isolation=isolation, execution_protocol=EXECUTION_PROTOCOL,
              prompt_protocol=config.get("prompt_protocol", PROMPT_PROTOCOL), task_reminder=reminder,
              initial_history_size=len(session_db.get_messages(session_id)),
              initial_backend_history_size=len(getattr(agent, "_session_messages", [])), current_task_history_size=0, working={},
              native_tools=sorted(agent.valid_tool_names), native_session_id=session_id,
              game_tool_registered=registry.get_entry("game_action") is not None,
              native_memory_enabled=agent._memory_enabled,
              native_context_configuration={"model_context_length": 64000},
              persistence={"curated_memory": "/agent/memory/memories", "skills": "/agent/memory/skills",
                           "skill_rollback_blobs": "/agent/memory/.curator_backups",
                           "session_database": str(native_home / "state.db"), "session_database_persistent": False},
              system_prompt=agent._build_system_prompt(guide))

    def run_loop(prompt, remaining):
        nonlocal history
        if False:
            yield None
        try:
            result = agent.run_conversation(prompt, system_message=guide, conversation_history=history)
            history = result.get("messages", history)
            drain_reviews()
            return {"result": "CURRENT_TASK_DONE", "native_failed": result.get("failed"),
                    "native_interrupted": result.get("interrupted")}
        except ModelBudgetExhausted:
            # Native finalizers have not run when the host budget signal escapes.
            # Preserve the main agent's exact last native chat context for the
            # same-session final opportunity, including the most recent feedback.
            history = [message for message in latest_native_history if message.get("role") != "system"]
            wire.emit("budget_context_preserved", native_message_count=len(history))
            drain_reviews()
            raise

    result = run_environment_task(run_loop, lambda: game_request({"command": "read"}),
        lambda: phase_calls["main"], wire.emit, initial_text=config["initial_text"], max_turns=config["max_turns"])
    drain_reviews()
    terminal = wire.call("task_end", {"native_result": result})
    finalizing = in_final_opportunity = True
    final_result = exhaust_native_loop(run_loop(terminal["text"] + "\n" + FINAL_OPPORTUNITY,
                                               config["final_turns"]), wire.emit)
    drain_reviews()
    agent.close()
    drain_reviews()
    session_db.close()
    wire.emit("finished", native_result=result, finalization_result=final_result, isolation=isolation,
              execution_protocol=EXECUTION_PROTOCOL, phase_calls=phase_calls)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.__stdout__.write(json.dumps({"kind": "worker_error", "error_type": type(error).__name__,
                                       "message": str(error)[:300]}) + "\n")
        sys.__stdout__.flush()
        raise SystemExit(2)
