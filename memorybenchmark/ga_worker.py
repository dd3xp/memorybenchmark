"""Standalone GA session worker; copy with agent_bridge.py, never the evaluator.

Only JSON messages use stdout. The host owns game rules and authenticated model
transport. No gateway secret, hidden world configuration or previous conversation enters here.
"""
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import random
import sys
import threading


PROTOCOL = "ga-session-1"
PROMPT_PROTOCOL = "cartography-native-memory-3"
EXECUTION_PROTOCOL = "environment-gated-1"
GUIDE = """
你正在完成一个制图游戏任务。使用 game_action 操作游戏；move 的 target
只传地点 ID，take 传工具 ID。到达自动测绘，满足目标后提交地理记录。
同一个世界会有多个独立任务，但你现在只获得当前任务。每个任务启动新会话，
历史对话、工作记忆和临时文件均不保留。你自主保存的经验只从 ../memory/ 跨会话传递。
当前观察可能提供共享的已提交地理图，可查看地点、连接和距离；
地图不会自动保存历史风险、工具库存位置或应对经验。携带工具在新任务重置。
开始委托前，请检查自己已有的相关经验，并结合当前公开观察判断是否适用。
任务结束后，请复盘实际经历；如果有可迁移经验，应使用原生工具保存或修正记忆。
经验内容、粒度和保存方式由你决定，不必为了写记忆而新增没有价值的条目。
普通回复中说“记住了”不等于持久保存。收到 done=true 后停止游戏操作，完成复盘再结束。
每步游戏反馈都会提供当前委托、目标进度和提交要求；每次模型调用也会附上简短的委托要求。
进度、位置和工具以最新公开观察为准，不确定时使用 game_action 的 read。
这里没有人工问答、网页或真实桌面；不要等待人工输入。游戏仅通过 game_action 访问。
"""
FINAL_OPPORTUNITY = """当前委托已经结束，不要继续游戏操作。
请回顾本次实际观察、行动及结果：什么尝试有效，什么失败或浪费了代价？
哪些规律、事实或教训可能帮助以后类似的委托？已有经验是否需要修正？
如果能提炼出可迁移经验，请现在通过你原生的记忆或文件工具完成保存、更新或纠正。
普通文字回复不会跨会话保留，不能代替实际保存。内容和组织方式由你决定。
只有确认没有值得保留或修正的经验时，才回复 noop；不必强行新增条目。
"""


def build_task_reminder(observation):
    """Short public requirements, with no task file or historical experience."""
    return (f"当前委托：{observation['task_id']} · {observation['task_name']}\n"
            f"要求：{observation['instruction']}")


def pin_task_reminder(payload, reminder, *, finalizing=False):
    """Add the current task after native history trimming, without editing it."""
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), list):
        raise RuntimeError("expected native Responses input list")
    phase = ("委托已结束，只能复盘并整理经验；禁止继续游戏操作。" if finalizing else
             "请按最新反馈中的进度和状态行动。")
    anchor = {"role": "developer", "content": [{"type": "input_text", "text":
        f"{reminder}\n当前阶段：{phase}"}]}
    return {**payload, "input": [anchor, *payload["input"]]}


class ModelBudgetExhausted(BaseException):
    """Host-controlled stop, not a retryable native tool/transport exception."""


def exhaust_native_loop(loop, emit):
    try:
        while True:
            emit("log", text=str(next(loop)))
    except StopIteration as ended:
        return ended.value
    except ModelBudgetExhausted:
        return {"result": "MAX_TURNS_EXCEEDED"}


def run_environment_task(run_loop, read_current, calls_used, emit, *, initial_text, max_turns):
    """Resume native responses in the same context until the environment ends.

    Public read calls do not move the agent or add graph actions. A continuation
    contains only current public state; it supplies no solution or memory facts.
    Actual model requests, including calls inside native tools, share one budget.
    """
    prompt = initial_text
    while calls_used() < max_turns:
        before = calls_used()
        result = exhaust_native_loop(run_loop(prompt, max_turns - before), emit)
        current = read_current()
        if current["observation"]["done"]:
            return result
        if calls_used() >= max_turns:
            return {"result": "MAX_TURNS_EXCEEDED"}
        if calls_used() <= before:
            raise RuntimeError("native loop returned without a model request")
        emit("continuation", execution_protocol=EXECUTION_PROTOCOL,
             main_calls=calls_used(), remaining_calls=max_turns - calls_used(),
             native_result=(result or {}).get("result"))
        prompt = current["text"] + "\n当前委托尚未结束，请根据当前公开状态继续操作；普通文字回复不算提交。"
    return {"result": "MAX_TURNS_EXCEEDED"}


class Wire:
    def __init__(self):
        self.input, self.output = sys.stdin, sys.stdout
        self.lock = threading.RLock()
        self.sequence = 0

    def emit(self, kind, **fields):
        with self.lock:
            self.output.write(json.dumps({"kind": kind, **fields}, ensure_ascii=False, default=str) + "\n")
            self.output.flush()

    def call(self, method, params):
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.emit("request", id=request_id, method=method, params=params)
            line = self.input.readline()
            if not line:
                raise RuntimeError("runner disconnected")
            result = json.loads(line)
            if result.get("id") != request_id:
                raise RuntimeError("RPC response mismatch")
            if "error" in result:
                raise RuntimeError(result["error"])
            return result["result"]


class LogSink(io.TextIOBase):
    def __init__(self, wire):
        self.wire = wire
    def write(self, value):
        if value:
            self.wire.emit("log", text=value)
        return len(value)
    def flush(self):
        pass


def probe():
    import socket
    results = {"pid": os.getpid(), "host_mount_hidden": not Path("/mnt/c").exists(),
               "evaluator_hidden": not Path("/agent/memorybenchmark").exists(),
               "secret_absent": not any("KEY" in k or "TOKEN" in k for k in os.environ),
               "network_blocked": False, "source_readonly": False}
    sock = socket.socket()
    sock.settimeout(1)
    try:
        results["network_blocked"] = sock.connect_ex(("1.1.1.1", 443)) != 0
    finally:
        sock.close()
    try:
        Path("/agent/.probe-write").write_text("x")
    except OSError:
        results["source_readonly"] = True
    if not all(v for k,v in results.items() if k != "pid"):
        raise RuntimeError("isolation preflight failed: " + str(results))
    return results


def main():
    wire = Wire()
    config = json.loads(wire.input.readline())
    if config.get("protocol") != PROTOCOL:
        raise RuntimeError("protocol mismatch")
    sys.stdout = sys.stderr = LogSink(wire)
    random.seed(config["seed"])
    # Keep the experiment language stable across old and current GA releases.
    os.environ["GA_LANG"] = "zh"
    isolation = probe()
    if config.get("probe_only"):
        wire.emit("finished", isolation=isolation)
        return
    reminder = config.get("task_reminder") or build_task_reminder(config["task_observation"])
    # Native GA's long-term-update tool reads ./memory, while its file tools
    # and system prompt also support ../memory from the temporary working dir.
    # Both names must reach the same native persistent directory.
    Path("/agent/temp/memory").symlink_to("/agent/memory", target_is_directory=True)
    finalizing = False
    in_final_opportunity = False
    phase_calls = {"main": 0, "final": 0}
    # Virtual configuration contains only a dummy credential. Native serialization
    # and SSE parsing remain unchanged; authenticated HTTPS runs in the parent.
    native_config = {"apikey": "runner-managed", "apibase": "https://model.invalid",
        "model": config["model"], "api_mode": "responses", "reasoning_effort": "low",
        "max_retries": 0, "connect_timeout": 5, "read_timeout": 45, "context_win": 50000, "proxy": None}
    # Current GA reloads mykey using find_spec and an on-disk timestamp. A
    # per-session dummy file supports that native loader without any real key.
    Path("/agent/temp/mykey.py").write_text("proxy = None\nnative_oai_config = " + repr(native_config), encoding="utf-8")
    sys.path.insert(0, "/agent/temp")
    import requests

    class ProxiedResponse:
        def __init__(self, result):
            self.status_code = 200
            self.headers = {"content-type": "text/event-stream"}
            self.lines = result["lines"]
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_lines(self): return (line.encode("utf-8") for line in self.lines)

    def post(url, **kwargs):
        if url != "https://model.invalid/v1/responses":
            raise RuntimeError("unregistered model transport")
        phase = "final" if in_final_opportunity else "main"
        budget = config["final_turns"] if in_final_opportunity else config["max_turns"]
        if phase_calls[phase] >= budget:
            raise ModelBudgetExhausted()
        phase_calls[phase] += 1
        payload = pin_task_reminder(kwargs["json"], reminder, finalizing=finalizing)
        return ProxiedResponse(wire.call("model", payload))
    requests.post = post
    import agentmain
    from agent_loop import StepOutcome
    from agent_bridge import GameTool, register_genericagent
    agent_class = getattr(agentmain, "GenericAgent", None) or agentmain.GeneraticAgent
    agent = agent_class()
    agent.next_llm(0)
    native_tools_before_game = [t["function"]["name"] for t in agentmain.TOOLS_SCHEMA]
    agent.task_dir = "/agent/temp"
    agent.verbose = False
    initial_history_size = len(agent.history)
    initial_backend_size = len(getattr(agent.llmclient.backend,"history",[]))
    # Match GeneraticAgent.run()'s native task preparation and anchor history.
    agent.history.append("[USER]: " + agentmain.smart_format(config["initial_text"].replace("\n"," "),max_str_len=200))
    handler = agentmain.GenericAgentHandler(agent, agent.history, "/agent/temp")
    agent.handler = handler
    def game_request(request):
        nonlocal finalizing
        result = wire.call("game", request)
        if result.get("observation", {}).get("done"):
            finalizing = True
        return result
    broker = None
    game_access = config.get("game_access", "bridge")
    if game_access == "native":
        from native_game_io import GameBroker
        broker = GameBroker(GameTool(game_request, definition=config.get("game_tool"),
                                    target_actions=config.get("game_target_actions", ("move", "take")))).start()
        os.environ["MEMORYBENCH_GAME_ENDPOINT"] = broker.endpoint
    elif game_access == "bridge":
        register_genericagent(agentmain, agent, StepOutcome, GameTool(game_request,
            definition=config.get("game_tool"), target_actions=config.get("game_target_actions", ("move", "take"))))
    else:
        raise RuntimeError("unsupported game access mode")
    # Current GA replaced tool_before_callback with plugin hooks. Observe the
    # shared dispatch boundary without replacing native tool or memory logic.
    original_dispatch = handler.dispatch
    def dispatch(name, args, response, *args_, **kwargs):
        wire.emit("tool", name=name, args={k:v for k,v in args.items() if not k.startswith("_")},
                  response_text=response.content)
        return original_dispatch(name, args, response, *args_, **kwargs)
    handler.dispatch = dispatch
    system = agentmain.get_system_prompt() + config.get("game_guide", GUIDE)
    wire.emit("session", protocol=PROTOCOL, isolation=isolation, execution_protocol=EXECUTION_PROTOCOL,
              prompt_protocol=config.get("prompt_protocol", PROMPT_PROTOCOL), task_reminder=reminder,
              system_prompt=system, initial_history_size=initial_history_size,
              game_access=game_access, agent_game_interface=("ga-code-run-client-1" if broker else "native-tool-bridge-1"),
              native_tool_registry_unchanged=native_tools_before_game == [t["function"]["name"] for t in agentmain.TOOLS_SCHEMA],
              initial_backend_history_size=initial_backend_size,
              current_task_history_size=len(handler.history_info),
              runtime={"python":sys.version,"packages":{name:version(name) for name in
                       ("requests","beautifulsoup4","bottle","simple-websocket-server")}},
              working=handler.working, native_tools=[t["function"]["name"] for t in agentmain.TOOLS_SCHEMA])
    def run_loop(prompt, remaining):
        return agentmain.agent_runner_loop(agent.llmclient, system, prompt, handler,
                                          agentmain.TOOLS_SCHEMA, max_turns=remaining, verbose=False)
    result = run_environment_task(run_loop, lambda: game_request({"command": "read"}),
        lambda: phase_calls["main"], wire.emit, initial_text=config["initial_text"], max_turns=config["max_turns"])
    # Preserve the old runner's final opportunity, with identical wording and
    # budgets for both conditions. Retain this task's native backend history.
    terminal = wire.call("task_end", {"native_result":result})
    finalizing = True
    in_final_opportunity = True
    final_loop = agentmain.agent_runner_loop(agent.llmclient, system,
        terminal["text"] + "\n" + FINAL_OPPORTUNITY, handler, agentmain.TOOLS_SCHEMA,
        max_turns=config["final_turns"], verbose=False)
    final_result = exhaust_native_loop(final_loop, wire.emit)
    if broker is not None:
        broker.close()
    # Exiting the PID namespace also terminates tool subprocesses. No writable
    # directory except memory survives, and the host snapshots only after exit.
    wire.emit("finished", native_result=result, finalization_result=final_result, isolation=isolation,
              execution_protocol=EXECUTION_PROTOCOL, phase_calls=phase_calls,
              agent_game_interface=("ga-code-run-client-1" if broker else "native-tool-bridge-1"),
              native_game_client_calls=broker.calls if broker else None)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # The parent treats worker failure separately from game failure.
        sys.__stdout__.write(json.dumps({"kind":"worker_error", "error_type":type(error).__name__,
                                       "message":str(error)[:300]}) + "\n")
        sys.__stdout__.flush()
        raise SystemExit(2)
