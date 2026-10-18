"""Native HTTPS with certificate renewal independent of the game state."""
from http.server import ThreadingHTTPServer
import logging
from pathlib import Path
import ssl
import tempfile
import time


log = logging.getLogger(__name__)


class CertificateContext:
    def __init__(self, certificate, private_key):
        self.certificate = Path(certificate)
        self.private_key = Path(private_key)
        self.signature = self._signature()
        self.failed_signature = ()
        # Initial failures are fatal: never silently fall back to plain HTTP.
        self.context = self._load()

    def _signature(self):
        result = []
        for path in (self.certificate, self.private_key):
            stat = path.stat()
            result.extend((stat.st_mtime_ns, stat.st_size, stat.st_ino))
        return tuple(result)

    def _load(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["http/1.1"])
        # An encrypted or broken key must fail rather than opening a prompt.
        # OpenSSL can hold Windows file handles while parsing a certificate.
        # Parse private temporary snapshots so renewal can replace the sources.
        certificate = self.certificate.read_bytes()
        private_key = self.private_key.read_bytes()
        with tempfile.TemporaryDirectory(prefix="memorybenchmark-tls-") as directory:
            cert_snapshot = Path(directory) / "cert.pem"
            key_snapshot = Path(directory) / "key.pem"
            cert_snapshot.write_bytes(certificate)
            key_snapshot.write_bytes(private_key)
            key_snapshot.chmod(0o600)
            context.load_cert_chain(cert_snapshot, key_snapshot, password=lambda: "")
        return context

    def reload_if_changed(self):
        signature = None
        try:
            signature = self._signature()
            if signature == self.signature:
                return False
            context = self._load()
        except (OSError, ValueError):
            if signature != self.failed_signature:
                log.warning("TLS certificate update is not ready; keeping the last valid certificate.")
            self.failed_signature = signature
            return False
        # A new context is installed only after both files load successfully.
        # Existing connections keep their original context and game session.
        self.context = context
        self.signature = signature
        self.failed_signature = ()
        log.info("TLS certificate reloaded.")
        return True


class HTTPSGameServer(ThreadingHTTPServer):
    def __init__(self, address, handler, *, certificate, private_key, reload_interval=60):
        if reload_interval <= 0:
            raise ValueError("TLS reload interval must be positive.")
        self.tls = CertificateContext(certificate, private_key)
        self.reload_interval = reload_interval
        self.next_reload = time.monotonic() + reload_interval
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(10)
        try:
            # Handshakes happen in the request thread, so an idle or malformed
            # connection cannot block the listener from accepting other users.
            connection = self.tls.context.wrap_socket(
                connection, server_side=True, do_handshake_on_connect=False
            )
        except Exception:
            connection.close()
            raise
        return connection, address

    def finish_request(self, request, client_address):
        try:
            request.do_handshake()
        except (OSError, ValueError):
            return
        super().finish_request(request, client_address)

    def service_actions(self):
        if time.monotonic() >= self.next_reload:
            self.next_reload = time.monotonic() + self.reload_interval
            self.tls.reload_if_changed()
