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
from .prototypes.field_service import FieldService
from .pilot_watch import PilotStore
from .map_catalog import CURRENT_MAP, MAPS, map_detail, map_listing, station_design
from .web_assets import WEB_ASSETS, CONTENT_TYPES

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
                game = Game(
                    log_path=self.log_root / token / "events.jsonl",
                    scenario=request.get("scenario", self.scenario),
                )
                adapter = GameAdapter(game)
                response = adapter.dispatch(
                    {"command": "start", "task_id": request.get("task_id", "T1")}
                )
                self.games[token] = adapter
            else:
                response = self.adapter(token).dispatch(
                    {"command": "start", "task_id": request.get("task_id", "T1")}
                )
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


def make_server(
    host="127.0.0.1",
    port=8765,
    log_root=Path(".runs"),
    watch_root=None,
    auth_file=None,
    secure_cookie=True,
    tls_cert=None,
    tls_key=None,
    tls_reload_interval=60,
    scenario="valley",
    pilot_root=None,
    experiment_service=None,
):
    if (tls_cert is None) != (tls_key is None):
        raise ValueError("HTTPS requires both a certificate and a private key.")
    if tls_cert is not None and not secure_cookie:
        raise ValueError("HTTPS sessions require Secure cookies.")
    if experiment_service is None:
        from .experiments.config import RuntimeConfig
        from .experiments.scheduler import WindowsScheduler
        from .experiments.service import ExperimentService
        import os

        configuration = Path(
            os.environ.get(
                "MEMORYBENCH_RUNTIME_CONFIG",
                Path(__file__).resolve().parents[1] / "config/experiment-runtime.json",
            )
        )
        try:
            experiment_service = ExperimentService(
                RuntimeConfig.load(configuration), WindowsScheduler()
            )
        except (OSError, ValueError):
            experiment_service = None
    service = GameService(log_root, scenario)
    from .prototypes.station_capability import load_design

    field = FieldService(
        log_root,
        load_design(station_design(CURRENT_MAP)),
        display_name=map_detail(CURRENT_MAP)["name"],
    )
    fields = {CURRENT_MAP: field}
    fields_lock = threading.RLock()
    pilots = PilotStore(log_root, pilot_root)
    watch = (
        WatchStore(
            Path(log_root) / "agent-cross-session", Path(log_root) / "ga-cross-session"
        )
        if watch_root is None
        else WatchStore(watch_root)
    )
    auth = (
        PinAuth(auth_file, secure_cookie=secure_cookie)
        if auth_file is not None
        else None
    )

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
            self.send_header(
                "Cache-Control", (extra or {}).get("Cache-Control", "no-store")
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            for name, value in (extra or {}).items():
                if name != "Cache-Control":
                    self.send_header(name, value)
            self.end_headers()

        def reply(self, data, status=200, extra=None):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.response_headers(
                status, "application/json; charset=utf-8", len(body), extra
            )
            self.wfile.write(body)

        def redirect(self, location, extra=None):
            self.response_headers(
                303,
                "text/plain; charset=utf-8",
                extra={"Location": location, **(extra or {})},
            )

        @staticmethod
        def destination(value):
            return (
                value
                if value
                in (
                    "/",
                    "/watch",
                    "/experiments",
                    "/experiments/new",
                    "/play",
                    "/maps",
                    "/design",
                    "/easy20",
                )
                else "/watch"
            )

        def field_service(self):
            map_id = parse_qs(urlsplit(self.path).query).get("map", [CURRENT_MAP])[0]
            with fields_lock:
                if map_id not in fields:
                    try:
                        path = station_design(map_id)
                    except ValueError as error:
                        raise ProtocolError(str(error)) from None
                    from .prototypes.station_capability import (
                        capability_groups,
                        load_design,
                    )

                    design = load_design(path)
                    # Old prototypes lack presentation metadata. Supply it only
                    # in this human instance; frozen agent designs stay untouched.
                    design["public"].setdefault("name", MAPS[map_id][0])
                    if not design["public"].get("station_types"):
                        design["public"].setdefault(
                            "capability_groups", capability_groups(design)
                        )
                    design["public"].setdefault(
                        "view_box", map_detail(map_id)["map"]["view_box"]
                    )
                    fields[map_id] = FieldService(
                        Path(log_root) / map_id,
                        design,
                        display_name=map_detail(map_id)["name"],
                    )
                return fields[map_id]

        def login_page(self, message="", status=200, destination="/watch", extra=None):
            body = (STATIC / "login.html").read_text(encoding="utf-8")
            body = body.replace(
                "{{NEXT}}", html.escape(self.destination(destination), quote=True)
            )
            body = body.replace("{{MESSAGE}}", html.escape(message)).encode("utf-8")
            self.response_headers(status, "text/html; charset=utf-8", len(body), extra)
            self.wfile.write(body)

        def require_login(self, path):
            if auth is None or auth.authorized(self.headers.get("Cookie")):
                return True
            if path.startswith("/api/") or path == "/health":
                self.reply(
                    {"error": "authentication_required", "message": "请先登录。"}, 401
                )
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
                    return parsed.scheme in (
                        "http",
                        "https",
                    ) and parsed.netloc == self.headers.get("Host")
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
                elif (
                    self.headers.get_content_type()
                    == "application/x-www-form-urlencoded"
                ):
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
                message = (
                    "尝试次数过多，请稍后再试。"
                    if retry_after
                    else "PIN 不正确，请重试。"
                )
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
                destination = self.destination(
                    parse_qs(url.query).get("next", [None])[0]
                )
                if auth is None or auth.authorized(self.headers.get("Cookie")):
                    self.redirect(destination)
                else:
                    self.login_page(destination=destination)
                return
            # The login page uses this credential-free loading helper.
            if url.path != "/ui-state.js" and not self.require_login(url.path):
                return
            if url.path == "/health":
                self.reply({"ok": True, "watch": True})
            elif url.path in ("/api/experiments/options", "/api/experiments/managed"):
                if experiment_service is None:
                    self.reply(
                        {
                            "error": "runtime_unavailable",
                            "message": "服务器尚未启用实验创建配置。",
                        },
                        503,
                    )
                else:
                    try:
                        self.reply(
                            experiment_service.options()
                            if url.path.endswith("/options")
                            else {"pairs": experiment_service.listing()}
                        )
                    except (OSError, ValueError, KeyError):
                        self.reply(
                            {
                                "error": "runtime_unavailable",
                                "message": "实验服务配置不可用，请检查服务器配置。",
                            },
                            503,
                        )
            elif url.path == "/api/experiments/runs":
                self.reply({"runs": pilots.listing()})
            elif url.path == "/api/experiments/run":
                try:
                    query = parse_qs(url.query)
                    self.reply(
                        pilots.snapshot(
                            query.get("id", [None])[0], query.get("session", [None])[0]
                        )
                    )
                except (OSError, ValueError, KeyError, TypeError):
                    self.reply(
                        {"error": "not_found", "message": "实验记录尚未准备好。"}, 404
                    )
            elif url.path == "/api/maps":
                self.reply({"maps": map_listing()})
            elif url.path == "/api/maps/detail":
                try:
                    self.reply(
                        map_detail(parse_qs(url.query).get("id", [CURRENT_MAP])[0])
                    )
                except ValueError as error:
                    self.reply({"error": "not_found", "message": str(error)}, 404)
            elif url.path == "/api/watch/runs":
                self.reply({"runs": watch.listing()})
            elif url.path == "/api/watch/run":
                try:
                    self.reply(watch.snapshot(parse_qs(url.query).get("id", [None])[0]))
                except (OSError, ValueError, KeyError, TypeError):
                    self.reply(
                        {
                            "error": "not_found",
                            "message": "实验记录不存在或尚未准备好。",
                        },
                        404,
                    )
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
                    self.reply(
                        {
                            "scenario": world.get("public_id", name),
                            "name": world.get("name", name),
                            "difficulty": world.get("difficulty"),
                            "tasks": [
                                {
                                    "id": key,
                                    "name": t["name"],
                                    "instruction": t["instruction"],
                                }
                                for key, t in tasks.items()
                            ],
                        }
                    )
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
            elif url.path in ("/api/field/observation", "/api/field/design"):
                token = parse_qs(url.query).get("instance_id", [None])[0]
                try:
                    current_field = self.field_service()
                    self.reply(
                        current_field.design_view(token)
                        if url.path.endswith("/design")
                        else current_field.read(token)
                    )
                except ProtocolError as e:
                    self.reply({"error": "protocol_error", "message": str(e)}, 400)
            elif (
                url.path == "/play"
                and parse_qs(url.query).get("map", [CURRENT_MAP])[0] not in MAPS
            ):
                self.reply({"error": "not_found", "message": "地图不存在。"}, 404)
            elif url.path == "/design":
                self.redirect("/maps")
            elif url.path in WEB_ASSETS:
                name = WEB_ASSETS[url.path]
                asset = STATIC / name
                extra = None
                if name.startswith("atlas-geo-") and name.endswith(".geojson"):
                    extra = {
                        "Cache-Control": "private, max-age=31536000, immutable",
                        "Vary": "Accept-Encoding",
                    }
                    if (
                        "gzip" in self.headers.get("Accept-Encoding", "")
                        and asset.with_suffix(".geojson.gz").is_file()
                    ):
                        asset = asset.with_suffix(".geojson.gz")
                        extra["Content-Encoding"] = "gzip"
                body = asset.read_bytes()
                self.response_headers(
                    200,
                    CONTENT_TYPES[Path(name).suffix] + "; charset=utf-8",
                    len(body),
                    extra,
                )
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
                self.reply(
                    {"error": "protocol_error", "message": "请求长度无效或读取超时。"},
                    400,
                )
                return
            if auth is not None and not self.same_origin():
                self.reply(
                    {
                        "error": "cross_origin_request",
                        "message": "请在本站页面执行操作。",
                    },
                    403,
                )
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
            if urlsplit(self.path).path not in (
                "/api/start",
                "/api/action",
                "/api/field/start",
                "/api/field/action",
                "/api/field/next",
                "/api/experiments/preview",
                "/api/experiments/create",
            ):
                self.reply({"error": "not_found"}, 404)
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ProtocolError("请求需使用 application/json。")
                request = json.loads(self.read_body())
                if not isinstance(request, dict):
                    raise ProtocolError("请求必须是对象。")
                route = urlsplit(self.path).path
                if route in ("/api/experiments/preview", "/api/experiments/create"):
                    if not self.same_origin():
                        self.reply(
                            {
                                "error": "cross_origin_request",
                                "message": "请在本站页面启动实验。",
                            },
                            403,
                        )
                        return
                    if experiment_service is None:
                        self.reply(
                            {
                                "error": "runtime_unavailable",
                                "message": "服务器尚未启用实验创建配置。",
                            },
                            503,
                        )
                        return
                    result = (
                        experiment_service.preview(request)
                        if route.endswith("/preview")
                        else experiment_service.create(request)
                    )
                elif route.startswith("/api/field/"):
                    current_field = self.field_service()
                    result = {
                        "/api/field/start": current_field.start,
                        "/api/field/action": current_field.action,
                        "/api/field/next": current_field.advance,
                    }[route](request)
                elif self.path == "/api/start":
                    result = service.start(request)
                else:
                    result = service.dispatch(
                        request.get("instance_id"), {**request, "command": "action"}
                    )
                self.reply(result)
            except (ValueError, UnicodeError, TypeError) as e:
                self.reply({"error": "protocol_error", "message": str(e)}, 400)
            except (OSError, RuntimeError):
                self.reply(
                    {
                        "error": "runtime_error",
                        "message": "实验尚未完成启动。请查看实验列表；重试同一提交不会重复创建。",
                    },
                    503,
                )

    if tls_cert is not None:
        server = HTTPSGameServer(
            (host, port),
            Handler,
            certificate=tls_cert,
            private_key=tls_key,
            reload_interval=tls_reload_interval,
        )
    else:
        server = ThreadingHTTPServer((host, port), Handler)
    server.service = service
    server.field = field
    server.watch = watch
    server.pilots = pilots
    server.auth = auth
    return server
