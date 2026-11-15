"""Request-level recovery: keep the native worker blocked on the same RPC.

This module owns transport only. It never reconstructs conversation history,
changes a prompt, executes a tool, or repeats a delivered game action.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import http.client
import json
from pathlib import Path
import random
import re
import socket
import ssl
import threading
import time
import tempfile
from urllib.parse import urlsplit
from uuid import uuid4

from .errors import InfrastructureError
from .model_gateway import GatewayModel
from .watch import atomic_json
from .ga_runtime import filesystem_path
from .response_stream import SpoolLines
from .transport_status import publish_status


WEEK = 7 * 24 * 3600
PROTOCOL = "same-request-recovery-1"


def utc():
    return datetime.now(timezone.utc).isoformat()


def durable_json(path, value):
    """DrvFS readers can briefly deny Windows ReplaceFile/delete sharing."""
    deadline = time.monotonic() + 5
    while True:
        try:
            return atomic_json(path, value)
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.03)


class RequestFailure(InfrastructureError):
    def __init__(self, reason, *, retryable=False, retry_after=0, **detail):
        super().__init__(reason)
        self.retryable, self.retry_after = retryable, retry_after
        self.detail = {"reason": reason, **detail}


class ActiveClock:
    """Successful computation consumes the task budget; outages do not."""
    def __init__(self, monotonic=time.monotonic):
        self.real = monotonic
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.origin = self.real()
            self.excluded = 0.0
            self.paused_at = None

    def monotonic(self):
        with self.lock:
            return (self.paused_at if self.paused_at is not None else self.real()) - self.excluded

    def elapsed(self):
        return self.monotonic() - self.origin

    def infrastructure_seconds(self):
        with self.lock:
            return self.excluded + (self.real() - self.paused_at if self.paused_at is not None else 0)

    @contextmanager
    def model_wait(self):
        with self.lock:
            if self.paused_at is not None:
                raise RuntimeError("Concurrent model RPCs are not supported")
            self.paused_at = self.real()
        try:
            yield
        finally:
            with self.lock:
                self.excluded += self.real() - self.paused_at
                self.paused_at = None

    def charge_success(self, seconds):
        with self.lock:
            self.excluded -= seconds


class _RoutedHTTPS(http.client.HTTPSConnection):
    """Change the TCP destination; preserve Host, SNI and certificate checks."""
    def __init__(self, host, port, connect_host, **kwargs):
        self.connect_host = connect_host
        super().__init__(host, port, **kwargs)

    def connect(self):
        self.sock = socket.create_connection((self.connect_host or self.host, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)
            self.sock.settimeout(120)
        except BaseException:
            self.sock.close()
            raise


class RecoveringGatewayModel(GatewayModel):
    def __init__(self, *args, status_path=None, connect_host=None, retry_window=WEEK,
                 clock=None, sleep=time.sleep, monotonic=time.monotonic,
                 jitter=random.uniform, **kwargs):
        super().__init__(*args, **kwargs)
        if not 0 < retry_window <= WEEK:
            raise ValueError("Request recovery must be within one week")
        self.status_path = Path(status_path) if status_path else None
        self.connect_host, self.retry_window = connect_host, retry_window
        self.clock = clock or ActiveClock(monotonic)
        self.sleep, self.monotonic, self.jitter = sleep, monotonic, jitter
        self.output = None
        self.alive = lambda: True

    def _record(self, kind, **fields):
        event = {"protocol": PROTOCOL, "utc": utc(), "kind": kind, **fields}
        if self.output:
            with (self.output / "transport-attempts.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        if self.status_path:
            publish_status(self.status_path, event)

    def _clean(self, text):
        text = str(text).replace(self.api_key, "[redacted]")
        return re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [redacted]", text)[:2000]

    def _body(self, payload):
        if not isinstance(payload, dict) or "input" not in payload:
            raise InfrastructureError("invalid native model payload")
        if any(t.get("type") != "function" for t in (payload.get("tools") or [])):
            raise InfrastructureError("unregistered remote tool")
        # Identical forwarding policy to GatewayModel; only transport changes.
        payload = {k: v for k, v in payload.items() if k in
                   ("input", "instructions", "tools", "reasoning", "include", "tool_choice", "parallel_tool_calls")
                   and v is not None}
        payload.update(model=self.model, stream=True, store=False)
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        return json.dumps(payload).encode("utf-8")

    def _attempt(self, body):
        url = urlsplit(self.endpoint)
        connection = _RoutedHTTPS(url.hostname, url.port or 443, self.connect_host,
                                 timeout=15, context=ssl.create_default_context())
        total, line_count, spool, spool_path, owner = 0, 0, None, None, None
        stream_digest = sha256()
        deadline = self.monotonic() + 900
        def evidence():
            if spool_path is None:
                return {}
            return {"path":str(spool_path),"bytes":total,"sha256":stream_digest.hexdigest()}
        def archive(raw):
            nonlocal total, line_count
            try:
                spool.write(raw)
            except OSError as error:
                raise RequestFailure("response_archive_io_error", archive_type=type(error).__name__,
                                     errno=error.errno) from None
            total += len(raw)
            line_count += 1
            stream_digest.update(raw)
        try:
            connection.request("POST", url.path, body=body, headers={
                "Authorization": "Bearer " + self.api_key, "Content-Type": "application/json",
                "Accept": "text/event-stream"})
            response = connection.getresponse()
            headers = {key: value for key, value in response.getheaders()
                       if key.lower() in ("retry-after", "x-request-id", "request-id", "cf-ray")}
            if response.status != 200:
                text = self._clean(response.read(4096).decode("utf-8", errors="replace"))
                retry_value = response.getheader("Retry-After", "0")
                try:
                    retry_after = max(0, float(retry_value))
                except ValueError:
                    try:
                        retry_after = max(0, parsedate_to_datetime(retry_value).timestamp()-time.time())
                    except (ValueError, TypeError, OverflowError):
                        retry_after = 0
                raise RequestFailure("gateway_http_" + str(response.status),
                    retryable=response.status in (408, 425, 429) or 500 <= response.status < 600,
                    retry_after=retry_after, http_status=response.status, headers=headers, body=text)
            content_type = response.getheader("Content-Type", "")
            if content_type and not content_type.lower().startswith("text/event-stream"):
                raise RequestFailure("gateway_unexpected_content_type", content_type=content_type)
            try:
                directory = filesystem_path(self.output / "model-streams") if self.output else None
                if directory is None:
                    owner = tempfile.TemporaryDirectory(prefix="memorybenchmark-sse-")
                    directory = Path(owner.name)
                directory.mkdir(parents=True, exist_ok=True)
                spool_path = directory / (uuid4().hex + ".sse")
                spool = spool_path.open("wb")
            except OSError as error:
                raise RequestFailure("response_archive_io_error", archive_type=type(error).__name__,
                                     errno=error.errno) from None
            while True:
                raw = response.readline(-1)
                if not raw:
                    raise RequestFailure("incomplete_model_stream", retryable=True, headers=headers)
                archive(raw)
                if self.monotonic() > deadline:
                    raise RequestFailure("model_stream_timeout", retryable=True, bytes=total)
                line = raw.decode("utf-8").rstrip("\r\n")
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                try: event = json.loads(line[5:])
                except ValueError: continue
                if event.get("type") in ("error", "response.failed", "response.incomplete"):
                    error = event.get("error") or event.get("response", {}).get("error") or {}
                    code = str(error.get("code", ""))
                    # Output/context limits and invalid requests need attention,
                    # not a week of silently repeating the same bad request.
                    transient = code in ("server_error", "rate_limit_exceeded", "overloaded", "server_is_overloaded", "temporarily_unavailable")
                    raise RequestFailure("model_response_failed", retryable=transient,
                        upstream_error=self._clean(json.dumps(event)),
                        reported_usage=event.get("response", {}).get("usage"))
                if event.get("type") == "response.completed":
                    usage = event.get("response", {}).get("usage")
                    if isinstance(usage, dict):
                        usage = {key: value for key, value in usage.items() if key in
                                 ("input_tokens", "output_tokens", "total_tokens", "input_tokens_details", "output_tokens_details")}
                    try:
                        spool.flush()
                    except OSError as error:
                        raise RequestFailure("response_archive_io_error", archive_type=type(error).__name__,
                                             errno=error.errno) from None
                    return {"lines": SpoolLines(spool_path, size=total, digest=stream_digest.hexdigest(),
                                                 line_count=line_count, owner=owner)}, usage
        except RequestFailure as error:
            if spool_path is not None:
                error.detail["response_stream_evidence"] = evidence()
            raise
        except ssl.SSLCertVerificationError:
            raise RequestFailure("gateway_certificate_invalid") from None
        except (OSError, http.client.HTTPException) as error:
            raise RequestFailure("gateway_transport_error", retryable=True,
                                 transport_type=type(error).__name__, detail=self._clean(error),
                                 response_stream_evidence=evidence()) from None
        finally:
            try:
                if spool is not None:
                    try:
                        spool.close()
                    except OSError as error:
                        raise RequestFailure("response_archive_io_error", archive_type=type(error).__name__,
                                             errno=error.errno,response_stream_evidence=evidence()) from None
            finally:
                connection.close()

    def __call__(self, payload):
        body = self._body(payload)  # One immutable byte string for every retry.
        request_id = sha256(body).hexdigest()
        call = len(list((self.output / "model").glob("*-request.json"))) if self.output else None
        remaining = self.retry_window - self.clock.infrastructure_seconds()
        deadline = self.monotonic() + max(0, remaining)
        attempt = 0
        with self.clock.model_wait():
            while True:
                if not self.alive():
                    raise InfrastructureError("native_worker_died_during_request_recovery")
                if self.monotonic() >= deadline:
                    self._record("needs_attention", call=call, request_sha256=request_id,
                                 reason="request_recovery_week_exhausted")
                    raise InfrastructureError("request_recovery_week_exhausted")
                attempt += 1
                start = self.monotonic()
                self._record("request_started", call=call, attempt=attempt, request_sha256=request_id,
                             state="running", task=self.output.name if self.output else None)
                try:
                    result, usage = self._attempt(body)
                except RequestFailure as error:
                    self._record("request_failed", call=call, attempt=attempt, request_sha256=request_id,
                        elapsed_seconds=round(self.monotonic()-start, 3), retryable=error.retryable,
                        provider_usage_unknown=not error.detail.get("reported_usage"), **error.detail)
                    if not error.retryable:
                        self._record("needs_attention", call=call, request_sha256=request_id,
                                     reason=error.detail["reason"])
                        raise InfrastructureError("nonretryable_model_request: " + str(error)) from None
                    delay = min(max(error.retry_after, self.jitter(.8, 1.2) * min(300, 2 ** min(attempt, 9))),
                                max(0, deadline-self.monotonic()))
                    self._record("network_retry", call=call, attempt=attempt, request_sha256=request_id,
                        reason=error.detail["reason"], retry_in_seconds=round(delay, 2),
                        task=self.output.name if self.output else None, state="network_retry")
                    # Short sleeps also notice a dead native worker promptly.
                    until = self.monotonic() + delay
                    while self.monotonic() < until:
                        if not self.alive():
                            raise InfrastructureError("native_worker_died_during_request_recovery")
                        self.sleep(min(2, until-self.monotonic()))
                    continue
                elapsed = self.monotonic() - start
                self.clock.charge_success(elapsed)
                self._record("request_completed", call=call, attempt=attempt, request_sha256=request_id,
                             elapsed_seconds=round(elapsed, 3), reported_usage=usage, state="running",
                             **({"response_stream_evidence":{"path":str(result["lines"].path),
                                 "bytes":result["lines"].size,"sha256":result["lines"].digest}}
                                if isinstance(result.get("lines"),SpoolLines) else {}))
                return result
