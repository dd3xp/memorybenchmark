from http.client import HTTPSConnection
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest

from memorybenchmark.server import make_server
from memorybenchmark.web_auth import save_pin


class HTTPSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        openssl = shutil.which("openssl")
        if openssl is None:
            bundled = Path("C:/Program Files/Git/usr/bin/openssl.exe")
            openssl = str(bundled) if bundled.exists() else None
        if openssl is None:
            raise unittest.SkipTest("OpenSSL is needed only to generate temporary test certificates")
        cls.fixtures = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixtures.name)
        for name in ("first", "renewed"):
            result = subprocess.run([
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "3",
                "-keyout", str(cls.fixture_root / f"{name}.key"),
                "-out", str(cls.fixture_root / f"{name}.crt"),
                "-subj", f"/CN=memorybenchmark-test-{name}",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,digitalSignature,keyEncipherment",
                "-addext", "extendedKeyUsage=serverAuth"
            ], capture_output=True, timeout=15)
            if result.returncode:
                cls.fixtures.cleanup()
                raise RuntimeError("Failed to generate temporary TLS test certificates")

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cert = self.root / "cert.pem"
        self.key = self.root / "key.pem"
        shutil.copyfile(self.fixture_root / "first.crt", self.cert)
        shutil.copyfile(self.fixture_root / "first.key", self.key)
        self.auth_file = self.root / "web-auth.json"
        self.pin = "041258"
        save_pin(self.auth_file, self.pin)
        self.server = make_server(port=0, log_root=self.root / "logs", auth_file=self.auth_file,
                                  tls_cert=self.cert, tls_key=self.key, tls_reload_interval=0.05)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True)
        self.thread.start()
        bundle = "".join((self.fixture_root / f"{name}.crt").read_text() for name in ("first", "renewed"))
        self.client_context = ssl.create_default_context(cadata=bundle)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path="/login", method="GET", body=None, cookie=None):
        connection = HTTPSConnection("127.0.0.1", self.server.server_port, timeout=3, context=self.client_context)
        headers = {}
        if body is not None:
            body = json.dumps(body)
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        try:
            connection.connect()
            certificate = connection.sock.getpeercert(binary_form=True)
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read(), certificate
        finally:
            connection.close()

    def test_native_https_preserves_pin_login_and_secure_cookie(self):
        self.assertEqual(self.request("/api/watch/runs")[0], 401)
        status, headers, body, _ = self.request("/login", "POST", {"pin": self.pin})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertIn("Secure", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("/api/watch/runs", cookie=cookie)[0], 200)
        self.assertEqual(self.request("/logout", "POST", cookie=cookie)[0], 303)
        self.assertEqual(self.request("/health", cookie=cookie)[0], 401)

    def test_silent_and_plaintext_clients_do_not_block_https(self):
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=3) as idle:
            with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=3) as plaintext:
                plaintext.sendall(b"GET /login HTTP/1.1\r\nHost: localhost\r\n\r\n")
                self.assertEqual(self.request()[0], 200)

    def test_incomplete_certificate_update_keeps_last_valid_certificate(self):
        before = self.request()[3]
        shutil.copyfile(self.fixture_root / "renewed.key", self.key)
        with self.assertLogs("memorybenchmark.tls", level="WARNING"):
            self.assertFalse(self.server.tls.reload_if_changed())
        self.assertEqual(self.request()[3], before)
        self.cert.write_text("partial certificate", encoding="utf-8")
        with self.assertLogs("memorybenchmark.tls", level="WARNING"):
            self.assertFalse(self.server.tls.reload_if_changed())
        self.assertEqual(self.request()[3], before)

    def test_renewed_certificate_is_loaded_automatically_without_losing_session(self):
        _, headers, _, before = self.request("/login", "POST", {"pin": self.pin})
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        target = ssl.PEM_cert_to_DER_cert((self.fixture_root / "renewed.crt").read_text())
        self.assertNotEqual(before, target)
        shutil.copyfile(self.fixture_root / "renewed.key", self.key)
        temporary = self.root / "next-cert.pem"
        shutil.copyfile(self.fixture_root / "renewed.crt", temporary)
        os.replace(temporary, self.cert)
        deadline = time.monotonic() + 3
        while True:
            status, _, _, actual = self.request("/health", cookie=cookie)
            self.assertEqual(status, 200)
            if actual == target:
                break
            if time.monotonic() >= deadline:
                self.fail("The HTTPS server did not reload the renewed certificate")
            time.sleep(0.02)

    def test_invalid_tls_startup_fails_without_plaintext_fallback(self):
        for options in ({"tls_cert": self.cert}, {"tls_key": self.key},
                        {"tls_cert": self.cert, "tls_key": self.key, "secure_cookie": False}):
            with self.assertRaises(ValueError):
                make_server(port=0, **options)
        with self.assertRaises(OSError):
            make_server(port=0, tls_cert=self.root / "missing.pem", tls_key=self.key)
        with self.assertRaises(ssl.SSLError):
            make_server(port=0, tls_cert=self.cert, tls_key=self.fixture_root / "renewed.key")


if __name__ == "__main__":
    unittest.main()
