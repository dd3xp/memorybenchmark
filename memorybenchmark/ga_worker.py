"""Standalone GA session worker; copy with agent_bridge.py, never the evaluator.

Only JSON messages use stdout. The host owns game rules and authenticated model
transport. No gateway secret, complete map or previous conversation enters here.
"""
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import random
import sys
import threading
import types


PROTOCOL = "ga-session-1"
GUIDE = """
你正在完成一个制图游戏任务。使用 game_action 操作游戏；move 的 target
只传地点 ID，take 传工具 ID。到达自动测绘，满足目标后提交地理记录。
同一个世界会有多个独立任务，但你现在只获得当前任务。每个任务启动新会话，
历史对话、工作记忆和临时文件均不保留。只有 ../memory/ 中的内容跨会话保留。
你可以使用原生工具，自行决定是否将本次实际经历整理到长期记忆中。
收到 done=true 后停止游戏操作，可以继续整理记忆，然后自然结束回复。
这里没有人工问答、网页或真实桌面；不要等待人工输入。游戏仅通过 game_action 访问。
"""
FINAL_OPPORTUNITY = "当前游戏任务已经结束。你可以自行判断是否有值得长期保留的实际经历，并使用原生工具整理；也可以直接结束。不要继续游戏操作。"


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
    isolation = probe()
    if config.get("probe_only"):
        wire.emit("finished", isolation=isolation)
        return
    # Virtual configuration contains only a dummy credential. Native serialization
    # and SSE parsing remain unchanged; authenticated HTTPS runs in the parent.
    credentials = types.ModuleType("mykey")
    credentials.proxy = None
    credentials.native_oai_config = {"apikey": "runner-managed", "apibase": "https://model.invalid",
        "model": config["model"], "api_mode": "responses", "reasoning_effort": "low",
        "max_retries": 0, "connect_timeout": 5, "read_timeout": 45, "context_win": 50000, "proxy": None}
    sys.modules["mykey"] = credentials
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
        return ProxiedResponse(wire.call("model", kwargs["json"]))
    requests.post = post
    import agentmain
    from agent_loop import StepOutcome
    from agent_bridge import GameTool, register_genericagent
    agent = agentmain.GeneraticAgent()
    agent.next_llm(0)
    agent.task_dir = "/agent/temp"
    agent.verbose = False
    initial_history_size = len(agent.history)
    initial_backend_size = len(getattr(agent.llmclient.backend,"history",[]))
    # Match GeneraticAgent.run()'s native task preparation and anchor history.
    agent.history.append("[USER]: " + agentmain.smart_format(config["initial_text"].replace("\n"," "),max_str_len=200))
    handler = agentmain.GenericAgentHandler(agent, agent.history, "/agent/temp")
    agent.handler = handler
    register_genericagent(agentmain, agent, StepOutcome, GameTool(lambda request: wire.call("game", request)))
    original_before = handler.tool_before_callback
    def before(name, args, response):
        wire.emit("tool", name=name, args={k:v for k,v in args.items() if not k.startswith("_")},
                  response_text=response.content)
        return original_before(name, args, response)
    handler.tool_before_callback = before
    system = agentmain.get_system_prompt() + GUIDE
    wire.emit("session", protocol=PROTOCOL, isolation=isolation,
              system_prompt=system, initial_history_size=initial_history_size,
              initial_backend_history_size=initial_backend_size,
              current_task_history_size=len(handler.history_info),
              runtime={"python":sys.version,"packages":{name:version(name) for name in
                       ("requests","beautifulsoup4","bottle","simple-websocket-server")}},
              working=handler.working, native_tools=[t["function"]["name"] for t in agentmain.TOOLS_SCHEMA])
    loop = agentmain.agent_runner_loop(agent.llmclient, system, config["initial_text"], handler,
                                      agentmain.TOOLS_SCHEMA, max_turns=config["max_turns"], verbose=False)
    try:
        while True:
            wire.emit("log", text=str(next(loop)))
    except StopIteration as ended:
        result = ended.value
    # Preserve the old runner's final opportunity, with identical wording and
    # budgets for both conditions. Retain this task's native backend history.
    terminal = wire.call("task_end", {"native_result":result})
    final_loop = agentmain.agent_runner_loop(agent.llmclient, system,
        terminal["text"] + "\n" + FINAL_OPPORTUNITY, handler, agentmain.TOOLS_SCHEMA,
        max_turns=config["final_turns"], verbose=False)
    try:
        while True:
            wire.emit("log", text=str(next(final_loop)))
    except StopIteration as ended:
        final_result = ended.value
    # Exiting the PID namespace also terminates tool subprocesses. No writable
    # directory except memory survives, and the host snapshots only after exit.
    wire.emit("finished", native_result=result, finalization_result=final_result, isolation=isolation)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # The parent treats worker failure separately from game failure.
        sys.__stdout__.write(json.dumps({"kind":"worker_error", "error_type":type(error).__name__,
                                       "message":str(error)[:300]}) + "\n")
        sys.__stdout__.flush()
        raise SystemExit(2)
