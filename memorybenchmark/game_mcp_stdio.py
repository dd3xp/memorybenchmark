"""Public MCP stdio facade for the task-bound game, without evaluator imports."""
import json

try:  # Standalone copies in /runner, or package invocation during tests.
    from game_client import request, describe
except ImportError:
    from .game_client import request, describe


def main():
    import anyio
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

    definition = describe()
    async def list_tools():
        return [Tool(name=definition["name"], description=definition["description"],
                     inputSchema=definition["parameters"],
                     annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                                 idempotentHint=False, openWorldHint=False))]

    async def call_tool(name, arguments):
        if name != definition["name"]:
            result = {"error": "unknown_tool", "message": "只提供当前游戏工具。"}
        else:
            # Keep caller arguments inside the public action object. In
            # particular, an extra 'endpoint' must never redirect the client.
            result = await anyio.to_thread.run_sync(lambda: request("call", arguments))
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
                              structuredContent=result, isError="error" in result)

    if hasattr(Server, "list_tools"):  # Python MCP SDK 1.x.
        server = Server("cartographers-notebook-native", version="native-game-access-1")
        server.list_tools()(list_tools)
        server.call_tool()(call_tool)
    else:  # Hermes' upstream lock currently selects the SDK 2.x callback API.
        from mcp.types import ListToolsResult

        async def on_list_tools(context, params):
            return ListToolsResult(tools=await list_tools())

        async def on_call_tool(context, params):
            return await call_tool(params.name, params.arguments or {})

        server = Server("cartographers-notebook-native", version="native-game-access-1",
                        on_list_tools=on_list_tools, on_call_tool=on_call_tool,
                        get_tool_input_schema=lambda name: definition["parameters"] if name == definition["name"] else None)

    async def serve():
        async with stdio_server() as streams:
            await server.run(*streams, server.create_initialization_options())
    anyio.run(serve)


if __name__ == "__main__":
    main()
