"""Local HTTP transport for human play and external agent tool bridges."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

from .adapters import GameAdapter
from .game import Game, ProtocolError
from .worlds import load_scenario
from .watch import WatchStore
from .web_auth import PinAuth
from .tls import HTTPSGameServer
from .map_design import map_design

STATIC = Path(__file__).parent / "static"


class GameService:
    def __init__(self, log_root=Path(".runs"), scenario="valley"):
        self.log_root = log_root
        self.scenario = scenario
        self.games = {}
        self.lock = threading.RLock()

    def start(self, request):
        with self.lock:
            token = request.get("instance_id")
            if token is None:
                token = uuid4().hex
                game = Game(log_path=self.log_root / token / "events.jsonl", scenario=request.get("scenario", self.scenario))
                adapter = GameAdapter(game)
                response = adapter.dispatch({"command": "start", "task_id": request.get("task_id", "T1")})
                self.games[token] = adapter
            else:
                response = self.adapter(token).dispatch({"command": "start", "task_id": request.get("task_id", "T1")})
            return {**response, "instance_id": token}

    def atlas(self, token):
        with self.lock:
            return self.adapter(token).game.observer_atlas()

    def adapter(self, token):
        if not isinstance(token, str) or token not in self.games:
            raise ProtocolError("游戏实例不存在，请创建一次新探索。")
        return self.games[token]

    def dispatch(self, token, request):
        with self.lock:
            return {**self.adapter(token).dispatch(request), "instance_id": token}


def make_server(host="127.0.0.1", port=8765, log_root=Path(".runs"),watch_root=None,
                auth_file=None, secure_cookie=True, tls_cert=None, tls_key=None,
                tls_reload_interval=60, scenario="valley"):
    if (tls_cert is None) != (tls_key is None):
        raise ValueError("HTTPS requires both a certificate and a private key.")
    if tls_cert is not None and not secure_cookie:
        raise ValueError("HTTPS sessions require Secure cookies.")
    service = GameService(log_root, scenario)
    watch=(WatchStore(Path(log_root)/"agent-cross-session",Path(log_root)/"ga-cross-session")
           if watch_root is None else WatchStore(watch_root))
    auth = PinAuth(auth_file, secure_cookie=secure_cookie) if auth_file is not None else None

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            pass

        def response_headers(self, status, mime, size=0, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()

        def reply(self, data, status=200, extra=None):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.response_headers(status, "application/json; charset=utf-8", len(body), extra)
            self.wfile.write(body)

        def redirect(self, location, extra=None):
            self.response_headers(303, "text/plain; charset=utf-8", extra={"Location": location, **(extra or {})})

        @staticmethod
        def destination(value):
            return value if value in ("/", "/watch", "/play", "/design") else "/watch"

        def login_page(self, message="", status=200, destination="/watch", extra=None):
            body = (STATIC / "login.html").read_text(encoding="utf-8")
            body = body.replace("{{NEXT}}", html.escape(self.destination(destination), quote=True))
            body = body.replace("{{MESSAGE}}", html.escape(message)).encode("utf-8")
            self.response_headers(status, "text/html; charset=utf-8", len(body), extra)
            self.wfile.write(body)

        def require_login(self, path):
            if auth is None or auth.authorized(self.headers.get("Cookie")):
                return True
            if path.startswith("/api/") or path == "/health":
                self.reply({"error": "authentication_required", "message": "请先登录。"}, 401)
            else:
                self.redirect("/login?next=" + self.destination(path))
            return False

        def same_origin(self):
            origin = self.headers.get("Origin")
            fetch_site = self.headers.get("Sec-Fetch-Site")
            if fetch_site == "cross-site":
                return False
            # Accept an opaque Origin only with browser-controlled Fetch
            # Metadata proving that the request came from the same origin.
            if origin == "null":
                return fetch_site == "same-origin"
            if origin:
                try:
                    parsed = urlsplit(origin)
                    return parsed.scheme in ("http", "https") and parsed.netloc == self.headers.get("Host")
                except ValueError:
                    return False
            return True

        def read_body(self):
            if hasattr(self, "request_body"):
                if not self.request_body:
                    raise ProtocolError("请求长度无效。")
                return self.request_body
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ProtocolError("请求长度无效。")
            return self.rfile.read(size)

        def login(self):
            json_request = self.headers.get_content_type() == "application/json"
            destination = "/watch"
            try:
                body = self.read_body()
                if json_request:
                    value = json.loads(body)
                elif self.headers.get_content_type() == "application/x-www-form-urlencoded":
                    value = {k: v[0] for k, v in parse_qs(body.decode("utf-8")).items()}
                else:
                    raise ProtocolError("登录请求格式无效。")
                if not isinstance(value, dict):
                    raise ProtocolError("登录请求必须是对象。")
                destination = self.destination(value.get("next"))
                token, retry_after = auth.login(value.get("pin"))
                if token:
                    extra = {"Set-Cookie": auth.cookie(token)}
                    if json_request:
                        self.reply({"ok": True, "next": destination}, extra=extra)
                    else:
                        self.redirect(destination, extra)
                    return
                message = "尝试次数过多，请稍后再试。" if retry_after else "PIN 不正确，请重试。"
                status = 429 if retry_after else 401
                extra = {"Retry-After": str(retry_after)} if retry_after else None
            except (ValueError, UnicodeError, TypeError) as error:
                message, status, extra = str(error), 400, None
            if json_request:
                self.reply({"error": "login_failed", "message": message}, status, extra)
            else:
                self.login_page(message, status, destination, extra)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == "/login":
                destination = self.destination(parse_qs(url.query).get("next", [None])[0])
                if auth is None or auth.authorized(self.headers.get("Cookie")):
                    self.redirect(destination)
                else:
                    self.login_page(destination=destination)
                return
            if not self.require_login(url.path):
                return
            if url.path == "/health":
                self.reply({"ok": True,"watch":True})
            elif url.path == "/api/watch/runs":
                self.reply({"runs":watch.listing()})
            elif url.path == "/api/watch/run":
                try:
                    self.reply(watch.snapshot(parse_qs(url.query).get("id",[None])[0]))
                except (OSError,ValueError,KeyError,TypeError):
                    self.reply({"error":"not_found","message":"实验记录不存在或尚未准备好。"},404)
            elif url.path == "/api/design":
                try:
                    name = parse_qs(url.query).get("scenario", [service.scenario])[0]
                    self.reply(map_design(name))
                except ValueError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif url.path == "/api/tasks":
                try:
                    name = parse_qs(url.query).get("scenario", [service.scenario])[0]
                    world, tasks = load_scenario(name)
                    self.reply({"scenario": world.get("public_id", name), "name": world.get("name", name), "difficulty": world.get("difficulty"),
                                "tasks": [{"id": key, "name": t["name"], "instruction": t["instruction"]}
                                          for key, t in tasks.items()]})
                except ValueError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif url.path == "/api/atlas":
                token = parse_qs(url.query).get("instance_id", [None])[0]
                try:
                    self.reply(service.atlas(token))
                except ProtocolError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif url.path == "/api/observation":
                token = parse_qs(url.query).get("instance_id", [None])[0]
                try:
                    self.reply(service.dispatch(token, {"command": "read"}))
                except ProtocolError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif url.path in ("/", "/play", "/watch", "/design", "/design.js", "/design.css", "/app.js", "/style.css", "/play.css", "/scene.js", "/terrain-ground.png", "/watch.js", "/watch.css", "/maps.js", "/lake.svg"):
                name = {"/": "watch.html", "/play":"index.html", "/watch":"watch.html", "/app.js": "app.js", "/style.css": "style.css",
                        "/design": "design.html", "/design.js": "design.js", "/design.css": "design.css", "/play.css": "play.css",
                        "/scene.js":"scene.js", "/terrain-ground.png":"terrain-ground.png",
                        "/watch.js":"watch.js","/watch.css":"watch.css", "/maps.js":"maps.js", "/lake.svg":"lake.svg"}[url.path]
                mime = "image/png" if name.endswith(".png") else ("image/svg+xml" if name.endswith(".svg") else ("text/html" if name.endswith(".html") else ("text/javascript" if name.endswith(".js") else "text/css")))
                body = (STATIC / name).read_bytes()
                self.response_headers(200, mime if name.endswith('.png') else mime + "; charset=utf-8", len(body))
                self.wfile.write(body)
            else:
                self.reply({"error": "not_found"}, 404)

        def do_POST(self):
            # Consume bounded request bytes before an early rejection. Closing
            # with unread POST data can discard the response via a Windows TCP
            # reset. JSON is still parsed only after the access checks below.
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 16384:
                    raise ProtocolError("请求长度无效。")
                self.request_body = self.rfile.read(size)
                if len(self.request_body) != size:
                    raise ProtocolError("请求不完整。")
            except (OSError, ValueError):
                self.reply({"error": "protocol_error", "message": "请求长度无效或读取超时。"}, 400)
                return
            if auth is not None and not self.same_origin():
                self.reply({"error": "cross_origin_request", "message": "请在本站页面执行操作。"}, 403)
                return
            if self.path == "/login" and auth is not None:
                self.login()
                return
            if not self.require_login(urlsplit(self.path).path):
                return
            if self.path == "/logout":
                if auth is not None:
                    auth.logout(self.headers.get("Cookie"))
                self.redirect("/login", {"Set-Cookie": auth.cookie()} if auth else None)
                return
            if self.path not in ("/api/start", "/api/action"):
                self.reply({"error": "not_found"}, 404)
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ProtocolError("请求需使用 application/json。")
                request = json.loads(self.read_body())
                if not isinstance(request, dict):
                    raise ProtocolError("请求必须是对象。")
                if self.path == "/api/start":
                    result = service.start(request)
                else:
                    result = service.dispatch(request.get("instance_id"), {**request, "command": "action"})
                self.reply(result)
            except (ValueError, UnicodeError, TypeError) as e:
                self.reply({"error": "protocol_error", "message": str(e)}, 400)

    if tls_cert is not None:
        server = HTTPSGameServer((host, port), Handler, certificate=tls_cert,
                                 private_key=tls_key, reload_interval=tls_reload_interval)
    else:
        server = ThreadingHTTPServer((host, port), Handler)
    server.service = service
    server.watch = watch
    server.auth = auth
    return server
