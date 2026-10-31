"""Standalone native-tool bridge. Safe to copy without evaluator modules.

The RPC callable must live in the agent process and return only public game
responses. Production isolation belongs to the subprocess launcher; the local
HTTP client is a development convenience, not a sandbox.
"""
from copy import deepcopy
import json
import threading
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


GAME_TOOL = {
    "name": "game_action",
    "description": "操作当前制图任务。到达即自动测绘；工具在所在地取用、携带后自动生效。read 读取公开观察。submit 须满足当前委托的全部目标和提交地点要求。done=true 后停止游戏操作，复盘实际经历；有可迁移经验时使用原生工具保存或更新，再结束本任务。",
    "parameters": {
        "type": "object", "properties": {
            "action": {"type": "string", "enum": ["move", "take", "observe", "wait", "submit", "abandon", "read"]},
            "target": {"type": "string", "description": "move 只传地点标识，如 J，不能传中文名称；take 传工具 id。其他动作不传。"}},
        "required": ["action"], "additionalProperties": False,
    },
}


class GameTool:
    def __init__(self, rpc, *, definition=None, target_actions=("move", "take")):
        self.rpc = rpc
        self.definition = deepcopy(GAME_TOOL if definition is None else definition)
        self.target_actions = tuple(target_actions)
        self.lock = threading.RLock()

    def __call__(self, args):
        route_enabled = "path" in self.definition["parameters"]["properties"]
        allowed = {"action", "target", "path"} if route_enabled else {"action", "target"}
        if not isinstance(args, dict) or set(args) - allowed:
            return {"error": "invalid_arguments", "message": "需要 action 和可选的 target。"}
        if route_enabled and "path" in args:
            path = args["path"]
            # Strict gateways may materialize unused optional fields as null/empty.
            if path not in (None, []):
                if (args.get("action") != "move" or args.get("target") not in (None, "")
                        or not isinstance(path, list) or not 1 <= len(path) <= 32
                        or any(not isinstance(node, str) or not 1 <= len(node) <= 128 for node in path)):
                    return {"error": "invalid_arguments", "message": "move 的 path 为 1–32 个依次相邻的地点 ID，与 target 二选一。"}
                responses = []
                with self.lock:
                    for target in path:
                        result = self({"action": "move", "target": target})
                        responses.append(deepcopy(result))
                        if "error" in result or result.get("observation", {}).get("done"):
                            break
                return {**responses[-1], "batch": {"requested": len(path), "attempted": len(responses),
                        "executed": sum("error" not in response for response in responses),
                        "stopped": "error" if "error" in result else "task_done" if result.get("observation", {}).get("done") else "completed"},
                        "responses": responses}
            args = {key: value for key, value in args.items() if key != "path"}
        action = args.get("action")
        if action not in self.definition["parameters"]["properties"]["action"]["enum"]:
            return {"error": "invalid_arguments", "message": "未知动作。"}
        if action in self.target_actions and not isinstance(args.get("target"), str):
            return {"error": "invalid_arguments", "message": "移动／取用需要 target。"}
        # Some strict-schema gateways materialize an unused optional string as
        # empty/null. It carries no target and must not obstruct submit/read.
        if action not in self.target_actions and args.get("target", "") not in ("", None):
            return {"error": "invalid_arguments", "message": "该动作不接受 target。"}
        args = {k:v for k,v in args.items() if k != "target" or action in self.target_actions}
        with self.lock:
            request = {"command": "read"} if action == "read" else {
                "command": "action", "request_id": uuid4().hex,
                "action": {"type": action, **({"target": args["target"]} if "target" in args else {})}}
            return self.rpc(request)


class HTTPGameClient:
    """Development-only client bound to an existing, runner-created instance."""
    def __init__(self, base_url, instance_id, timeout=5):
        self.base_url = base_url.rstrip("/")
        self.instance_id = instance_id
        self.timeout = timeout
        self.revision = None

    def __call__(self, request):
        from urllib.parse import urlencode
        if request["command"] == "read":
            wire = Request(self.base_url + "/api/observation?" + urlencode({"instance_id": self.instance_id}))
        else:
            payload = {**request, "instance_id": self.instance_id}
            if self.revision is not None:
                payload["expected_revision"] = self.revision
            wire = Request(self.base_url + "/api/action", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        # Retrying this exact request preserves request_id and expected_revision.
        for attempt in range(2):
            try:
                with urlopen(wire, timeout=self.timeout) as response:
                    result = json.load(response)
                self.revision = result["observation"]["revision"]
                return result
            except HTTPError as error:
                return json.loads(error.read())
            except (URLError, TimeoutError):
                if attempt:
                    return {"error": "transport_error", "message": "游戏连接失败；需要运行器恢复或重试，不能计为游戏失败。"}


def register_hermes(registry, create_custom_toolset, game_tool):
    """Register through Hermes' existing tool registry; no memory replacement."""
    def handler(args, **kwargs):
        return json.dumps(game_tool(args), ensure_ascii=False)
    definition = deepcopy(getattr(game_tool, "definition", GAME_TOOL))
    registry.register(name="game_action", toolset="cartography", schema=definition,
                      handler=handler, description=definition["description"])
    create_custom_toolset("cartography", "Cartography game", tools=["game_action"], includes=[])
    return handler


def register_genericagent(agent_module, agent, step_outcome, game_tool):
    """Call after model selection: next_llm() can reload TOOLS_SCHEMA.

    Handler parent keeps the binding on its owning native agent. Each native
    agent must run in its own process, as in the old benchmark adapter.
    """
    agent._benchmark_game_tool = game_tool
    # The legacy bundle also exposes a submit tool. Keep its established
    # callback semantics, but route it to the current game instead of silently
    # ending the native loop without submitting the environment task.
    agent._submit_eval_cb = lambda answer: json.dumps(game_tool({"action": "submit"}), ensure_ascii=False)

    def do_game_action(self, args, response):
        # GenericAgent BaseHandler adds its own dispatch metadata to arguments.
        clean = {k: v for k, v in args.items() if k not in ("_index", "_tool_num")}
        result = self.parent._benchmark_game_tool(clean)
        return step_outcome(result, next_prompt="\n")

    agent_module.GenericAgentHandler.do_game_action = do_game_action
    agent_module.TOOLS_SCHEMA[:] = [t for t in agent_module.TOOLS_SCHEMA if t.get("function", {}).get("name") != "game_action"]
    agent_module.TOOLS_SCHEMA.append({"type": "function", "function": deepcopy(getattr(game_tool, "definition", GAME_TOOL))})
    for entry in agent_module.TOOLS_SCHEMA:
        if entry.get("function", {}).get("name") == "submit":
            entry["function"]["description"] = "提交当前游戏的地理记录；必须满足当前委托的全部目标和提交地点要求。answer 不用于修改游戏状态。"
