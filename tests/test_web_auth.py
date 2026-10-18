from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from memorybenchmark.server import make_server
from memorybenchmark.web_auth import SESSION_SECONDS, save_pin


class WebAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "web-auth.json"
        self.pin = "031479"
        save_pin(self.config, self.pin)
        self.server = make_server(port=0, log_root=self.root / "logs", auth_file=self.config)
        self.clock = 1000
        self.server.auth.clock = lambda: self.clock
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ""

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", data=None, headers=None, cookie=None):
        values = dict(headers or {})
        if cookie is not None:
            values["Cookie"] = cookie
        body = None
        if data is not None:
            values.setdefault("Content-Type", "application/json")
            body = json.dumps(data) if values["Content-Type"] == "application/json" else data
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def login(self):
        status, headers, body = self.request("/login", "POST", {"pin": self.pin})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]
        return headers

    def test_unauthenticated_requests_cannot_read_or_change_games(self):
        for path in ("/", "/watch", "/play", "/watch.js", "/app.js", "/watch.css", "/style.css", "/maps.js", "/loch-ness.svg"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 303, path)
            self.assertTrue(headers["Location"].startswith("/login"))
            self.assertEqual(body, b"")
        for path in ("/health", "/api/watch/runs", "/api/watch/run?id=anything", "/api/tasks", "/api/observation", "/api/atlas?instance_id=anything"):
            status, _, body = self.request(path)
            self.assertEqual(status, 401, path)
            self.assertEqual(json.loads(body)["error"], "authentication_required")
        for path in ("/api/start", "/api/action"):
            status, _, _ = self.request(path, "POST", {"task_id": "T1"})
            self.assertEqual(status, 401)
        self.assertEqual(self.server.service.games, {})
        status, headers, body = self.request("/login?next=//untrusted.example/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"untrusted.example", body)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertNotIn(self.pin, self.config.read_text(encoding="utf-8"))

    def test_login_allows_real_game_requests_and_logout_revokes_cookie(self):
        headers = self.login()
        for attribute in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(attribute, headers["Set-Cookie"])
        for path in ("/", "/watch", "/play", "/watch.js", "/api/watch/runs", "/health"):
            self.assertEqual(self.request(path, cookie=self.cookie)[0], 200, path)
        status, _, body = self.request("/api/start", "POST", {"task_id": "T1"}, cookie=self.cookie)
        self.assertEqual(status, 200)
        initial = json.loads(body)
        instance = initial["instance_id"]
        status, _, body = self.request("/api/action", "POST", {
            "instance_id": instance, "request_id": "authenticated-move",
            "expected_revision": initial["observation"]["revision"],
            "action": {"type": "move", "target": "J"}
        }, cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["observation"]["location"]["id"], "J")
        status, headers, _ = self.request("/logout", "POST", cookie=self.cookie)
        self.assertEqual(status, 303)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request("/api/watch/runs", cookie=self.cookie)[0], 401)

    def test_wrong_pin_is_rate_limited_globally_and_success_preserves_leading_zero(self):
        for _ in range(4):
            self.assertEqual(self.request("/login", "POST", {"pin": "111111"})[0], 401)
        status, headers, _ = self.request("/login", "POST", {"pin": "111111"})
        self.assertEqual(status, 429)
        self.assertIn("Retry-After", headers)
        status, _, _ = self.request("/login", "POST", {"pin": self.pin}, headers={"X-Forwarded-For": "new-client"})
        self.assertEqual(status, 429)
        self.clock += 61
        self.login()

    def test_expired_forged_and_restarted_sessions_are_rejected(self):
        self.login()
        self.assertEqual(self.request("/health", cookie=self.cookie + "forged")[0], 401)
        self.clock += SESSION_SECONDS
        self.assertEqual(self.request("/health", cookie=self.cookie)[0], 401)
        self.login()
        self.server.auth.sessions.clear()  # A process restart drops the in-memory session registry.
        self.assertEqual(self.request("/health", cookie=self.cookie)[0], 401)

    def test_cross_site_login_actions_and_logout_are_rejected(self):
        self.login()
        hostile = {"Origin": "https://untrusted.example"}
        for path, data in (("/login", {"pin": self.pin}), ("/api/start", {"task_id": "T1"}), ("/logout", {})):
            self.assertEqual(self.request(path, "POST", data, hostile, self.cookie)[0], 403)
        self.assertEqual(self.request("/health", cookie=self.cookie)[0], 200)
        self.assertEqual(self.server.service.games, {})
        origin = f"https://127.0.0.1:{self.server.server_port}"
        body = urlencode({"pin": self.pin, "next": "/play"})
        status, headers, _ = self.request("/login", "POST", body, {
            "Origin": origin, "Content-Type": "application/x-www-form-urlencoded"
        })
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/play")

    def test_opaque_origin_needs_browser_same_origin_metadata(self):
        for metadata in ({}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            headers = {"Origin": "null", **metadata}
            self.assertEqual(self.request("/login", "POST", {"pin": self.pin}, headers)[0], 403)
        status, _, _ = self.request("/login", "POST", {"pin": self.pin}, {
            "Origin": "null", "Sec-Fetch-Site": "same-origin"
        })
        self.assertEqual(status, 200)

    def test_missing_or_invalid_auth_configuration_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            make_server(port=0, auth_file=self.root / "missing.json")
        self.config.write_text('{"scheme":"unknown"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            make_server(port=0, auth_file=self.config)


if __name__ == "__main__":
    unittest.main()
