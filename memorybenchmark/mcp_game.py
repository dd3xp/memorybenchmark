"""One task-scoped MCP game service; no agent, memory or evaluator tools.

The stdio service and the runner's memory transport use the same official SDK
server. SDK imports are optional so the human game remains standard-library only.
"""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sys
import threading

from .agent_bridge import GAME_TOOL, GameTool
from .game_session import validate_request


GAME_TRANSPORT = "cartography-mcp-1"
SDK_VERSION = "1.30.0"
ACTION_META = "memorybenchmark/action"


def require_mcp():
    try:
        installed = version("mcp")
    except PackageNotFoundError:
        raise RuntimeError('MCP 接入需要安装依赖：python -m pip install -e ".[mcp]"') from None
    if installed != SDK_VERSION:
        raise RuntimeError(f"MCP SDK 版本应为 {SDK_VERSION}，实际为 {installed}；请使用项目的 mcp 安装选项。")
    return installed


def transport_identity():
    return {"game_transport": GAME_TRANSPORT, "mcp_sdk_version": require_mcp(),
            "game_tool_sha256": sha256(json.dumps(GAME_TOOL, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "mcp_implementation": {name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ("mcp_game.py", "game_session.py")}}


def create_server(rpc):
    """rpc accepts only the bound current task's public read/action requests."""
    require_mcp()
    import anyio
    from mcp.server import Server
    from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

    server = Server("cartographers-notebook", version=GAME_TRANSPORT)
    lock = anyio.Lock()

    @server.list_tools()
    async def list_tools():
        return [Tool(name=GAME_TOOL["name"], description=GAME_TOOL["description"],
                     inputSchema=deepcopy(GAME_TOOL["parameters"]),
                     annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                 idempotentHint=False, openWorldHint=False))]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name != "game_action":
            result = {"error": "unknown_tool", "message": "只提供 game_action。"}
        else:
            # Optional action metadata preserves native request IDs/revisions
            # across the GA bridge. Ordinary MCP clients can omit it entirely.
            meta = server.request_context.meta
            fields = meta.model_dump().get(ACTION_META, {}) if meta is not None else {}
            if not isinstance(fields, dict) or set(fields) - {"request_id", "expected_revision"}:
                result = {"error": "invalid_request", "message": "动作元数据无效。"}
            else:
                def bound(request):
                    return rpc({**request, **fields} if request["command"] == "action" else request)
                async with lock:
                    result = GameTool(bound)(arguments)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                              structuredContent=result, isError="error" in result)

    return server


@asynccontextmanager
async def connect_memory(rpc):
    """Full MCP initialization/discovery/calls without a public network port."""
    import anyio
    from mcp import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    server = create_server(rpc)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(server.run, *server_streams, server.create_initialization_options())
            async with ClientSession(*client_streams, read_timeout_seconds=timedelta(seconds=30)) as client:
                initialized = await client.initialize()
                tools = await client.list_tools()
                if len(tools.tools) != 1 or tools.tools[0].name != "game_action":
                    raise RuntimeError("unexpected game MCP tool list")
                if tools.tools[0].inputSchema != GAME_TOOL["parameters"]:
                    raise RuntimeError("unexpected game MCP input schema")
                yield client, {**transport_identity(), "mcp_protocol": initialized.protocolVersion}
            tasks.cancel_scope.cancel()


class MCPGameClient:
    """Synchronous thin bridge for native agents without an MCP client.

    The client/server exchange uses real MCP messages through the SDK. Only the
    game protocol changes; native agent loops and memory tools remain native.
    """
    def __init__(self, rpc):
        self.rpc = rpc
        self.lock = threading.RLock()

    def __enter__(self):
        require_mcp()
        from anyio.from_thread import start_blocking_portal
        self._portal_context = start_blocking_portal(name="game-mcp")
        self._portal = self._portal_context.__enter__()
        try:
            self._session_context = self._portal.wrap_async_context_manager(connect_memory(self.rpc))
            self.client, self.identity = self._session_context.__enter__()
        except BaseException:
            self._portal_context.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *exc):
        try:
            return self._session_context.__exit__(*exc)
        finally:
            self._portal_context.__exit__(*exc)

    def __call__(self, request):
        error = validate_request(request)
        if error:
            return error
        if request["command"] == "read":
            arguments, meta = {"action": "read"}, None
        else:
            action = request.get("action")
            if not isinstance(action, dict) or set(action) - {"type", "target"}:
                return {"error": "invalid_request", "message": "动作格式无效。"}
            arguments = {"action": action.get("type")}
            if "target" in action:
                arguments["target"] = action["target"]
            meta = {ACTION_META: {k: request[k] for k in ("request_id", "expected_revision") if k in request}}

        async def call():
            return await self.client.call_tool("game_action", arguments, meta=meta)

        with self.lock:
            result = self._portal.call(call)
        if result.structuredContent is not None:
            return result.structuredContent
        if result.isError:
            return {"error": "invalid_arguments", "message": "；".join(
                item.text for item in result.content if item.type == "text")}
        raise RuntimeError("game MCP returned no structured public observation")
