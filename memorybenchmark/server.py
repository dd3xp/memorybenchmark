"""Local HTTP transport for human play and external agent tool bridges."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

from .adapters import GameAdapter
from .game import Game, TASKS, ProtocolError

STATIC = Path(__file__).parent / "static"


class GameService:
    def __init__(self, log_root=Path(".runs")):
        self.log_root = log_root
        self.games = {}
        self.lock = threading.RLock()

    def start(self, request):
        with self.lock:
            token = request.get("instance_id")
            if token is None:
                token = uuid4().hex
                game = Game(log_path=self.log_root / token / "events.jsonl", scenario=request.get("scenario", "valley"))
                adapter = GameAdapter(game)
                response = adapter.dispatch({"command": "start", "task_id": request.get("task_id", "T1")})
                self.games[token] = adapter
            else:
                response = self.adapter(token).dispatch({"command": "start", "task_id": request.get("task_id", "T1")})
            return {**response, "instance_id": token}

    def adapter(self, token):
        if not isinstance(token, str) or token not in self.games:
            raise ProtocolError("游戏实例不存在，请创建一次新探索。")
        return self.games[token]

    def dispatch(self, token, request):
        with self.lock:
            return {**self.adapter(token).dispatch(request), "instance_id": token}


def make_server(host="127.0.0.1", port=8765, log_root=Path(".runs")):
    service = GameService(log_root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def reply(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/health":
                self.reply({"ok": True})
            elif url.path == "/api/tasks":
                self.reply({"tasks": [{"id": key, "name": t["name"], "instruction": t["instruction"]}
                                      for key, t in TASKS.items()]})
            elif url.path == "/api/observation":
                token = parse_qs(url.query).get("instance_id", [None])[0]
                try:
                    self.reply(service.dispatch(token, {"command": "read"}))
                except ProtocolError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif url.path in ("/", "/app.js", "/style.css"):
                name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[url.path]
                mime = {"/": "text/html", "/app.js": "text/javascript", "/style.css": "text/css"}[url.path]
                body = (STATIC / name).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime + "; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.reply({"error": "not_found"}, 404)

        def do_POST(self):
            if self.path not in ("/api/start", "/api/action"):
                self.reply({"error": "not_found"}, 404)
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ProtocolError("请求需使用 application/json。")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ProtocolError("请求长度无效。")
                request = json.loads(self.rfile.read(size))
                if not isinstance(request, dict):
                    raise ProtocolError("请求必须是对象。")
                if self.path == "/api/start":
                    result = service.start(request)
                else:
                    result = service.dispatch(request.get("instance_id"), {**request, "command": "action"})
                self.reply(result)
            except (ValueError, UnicodeError, TypeError) as e:
                self.reply({"error": "protocol_error", "message": str(e)}, 400)

    server = ThreadingHTTPServer((host, port), Handler)
    server.service = service
    return server
