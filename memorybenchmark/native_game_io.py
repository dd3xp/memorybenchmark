"""Task-local IPC for native code tools and a native MCP stdio client.

Only the runner owns the callback. The agent-facing client and MCP facade
can request public actions or the public tool schema; no evaluator is mounted.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import socketserver
import threading


GAME_ACCESS_PROTOCOLS = {"bridge": "native-tool-bridge-1", "native": "native-game-access-1"}


class GameBroker:
    def __init__(self, tool, *, endpoint="unix:/tmp/memorybenchmark-game.sock"):
        self.tool, self.endpoint = tool, endpoint
        self.calls = 0
        self.failures = []
        self._lock = threading.RLock()
        broker = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(30)
                raw = self.rfile.readline(65537)
                if len(raw) > 65536 or not raw.endswith(b"\n"):
                    result = {"error": "invalid_request", "message": "游戏请求过长或不完整。"}
                else:
                    try:
                        request = json.loads(raw)
                    except (ValueError, UnicodeError):
                        request = None
                    result = broker.dispatch(request)
                try:
                    self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8") + b"\n")
                except OSError as error:
                    # A lost delivery can leave an action's outcome unknown to
                    # the agent; the runner must reject the infrastructure attempt.
                    with broker._lock:
                        broker.failures.append(type(error).__name__)

        if endpoint.startswith("unix:"):
            self._socket_path = Path(endpoint[5:])
            # Never replace an endpoint belonging to another live task.
            if self._socket_path.exists():
                raise FileExistsError("game endpoint already exists")
            server_class = socketserver.ThreadingUnixStreamServer
            address = str(self._socket_path)
        elif endpoint == "tcp:127.0.0.1:0":
            # Portable integration-test transport; production uses private Unix IPC.
            self._socket_path = None
            server_class = socketserver.ThreadingTCPServer
            address = ("127.0.0.1", 0)
        else:
            raise ValueError("unsupported broker endpoint")
        self.server = server_class(address, Handler)
        self.server.daemon_threads = True
        if self._socket_path is None:
            self.endpoint = "tcp:127.0.0.1:" + str(self.server.server_address[1])
        else:
            os.chmod(self._socket_path, 0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def dispatch(self, request):
        if not isinstance(request, dict) or set(request) != {"method", "params"}:
            return {"error": "invalid_request", "message": "只接受当前游戏的公开请求。"}
        if request["method"] == "describe" and request["params"] == {}:
            return deepcopy(self.tool.definition)
        if request["method"] != "call" or not isinstance(request["params"], dict):
            return {"error": "invalid_request", "message": "只接受公开工具查询和调用。"}
        with self._lock:
            try:
                result = self.tool(request["params"])
                self.calls += 1
                return result
            except Exception as error:
                self.failures.append(type(error).__name__)
                return {"error": "game_transport_error", "message": "游戏传输失败，运行器必须核查。"}

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self._socket_path is not None:
            self._socket_path.unlink(missing_ok=True)
        if self.failures:
            raise RuntimeError("task-local game transport failed: " + self.failures[0])

    def __enter__(self):
        return self.start()

    def __exit__(self, *unused):
        self.close()
