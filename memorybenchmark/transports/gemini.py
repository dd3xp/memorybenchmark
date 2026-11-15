"""Loopback-only Gemini Chat transport; native Hermes owns messages/tools/signatures."""

from hashlib import sha256
import http.client
import json
from pathlib import Path
import socket
import tempfile
import time
from uuid import uuid4

from memorybenchmark.request_recovery import RecoveringGatewayModel, RequestFailure
from memorybenchmark.response_stream import SpoolLines
from memorybenchmark.ga_runtime import filesystem_path


def usage_record(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for source, target in (
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        if isinstance(value.get(source), int):
            result[target] = value[source]
    if isinstance(value.get("completion_tokens_details"), dict):
        result["output_tokens_details"] = value["completion_tokens_details"]
    if isinstance(value.get("prompt_tokens_details"), dict):
        result["input_tokens_details"] = value["prompt_tokens_details"]
    return result or None


class GeminiGateway(RecoveringGatewayModel):
    def __init__(self, base_url, api_key, model, max_output_tokens=None, **kwargs):
        if base_url != "http://127.0.0.1:14172/v1":
            raise ValueError(
                "Only the authorized local Gemini loopback endpoint is permitted"
            )
        if model not in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
            raise ValueError("Unexpected pilot model")
        # The inherited recovery loop/clock needs no changes; only the protocol
        # endpoint and payload differ from the older Responses-only transport.
        super().__init__(
            "https://loopback.invalid/v1", api_key, model, max_output_tokens, **kwargs
        )
        self.endpoint = base_url + "/chat/completions"

    def _body(self, payload):
        if not isinstance(payload, dict) or not isinstance(
            payload.get("messages"), list
        ):
            raise ValueError("Expected native Hermes Chat messages")
        if any(t.get("type") != "function" for t in payload.get("tools") or []):
            raise ValueError("Only jail-owned function tools are allowed")
        if payload.get("model") != self.model:
            raise ValueError("Native model identity changed")
        # No prompt, signature, sampling, thinking or tool schema conversion.
        return json.dumps(payload, ensure_ascii=True).encode("utf-8")

    def _attempt(self, body):
        connection = http.client.HTTPConnection("127.0.0.1", 14172, timeout=120)
        owner = None
        directory = (
            filesystem_path(self.output / "model-streams") if self.output else None
        )
        if directory is None:
            owner = tempfile.TemporaryDirectory(prefix="gemini-pilot-")
            directory = Path(owner.name)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid4().hex + ".raw")
        size = lines = 0
        digest = sha256()
        started = self.monotonic()

        def evidence():
            return {"path": str(path), "bytes": size, "sha256": digest.hexdigest()}

        try:
            connection.request(
                "POST",
                "/v1/chat/completions",
                body=body,
                headers={
                    "Authorization": "Bearer " + self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "Memorybenchmark-Gemini-Easy-Hermes/1",
                    "Accept": "text/event-stream, application/json",
                },
            )
            response = connection.getresponse()
            headers = {
                k.lower(): v
                for k, v in response.getheaders()
                if k.lower()
                in (
                    "retry-after",
                    "x-gateway-request-id",
                    "x-gateway-project",
                    "x-gateway-attempts",
                )
            }
            if response.status != 200:
                raw = response.read()
                path.write_bytes(raw)
                size = len(raw)
                digest.update(raw)
                try:
                    retry = float(response.getheader("Retry-After", "0"))
                except ValueError:
                    retry = 0
                raise RequestFailure(
                    "gateway_http_" + str(response.status),
                    retryable=response.status in (408, 425, 429)
                    or 500 <= response.status < 600,
                    retry_after=max(0, retry),
                    http_status=response.status,
                    headers=headers,
                    body=self._clean(raw.decode("utf-8", errors="replace")),
                )
            requested_stream = json.loads(body).get("stream", False)
            if requested_stream:
                if not response.getheader("Content-Type", "").startswith(
                    "text/event-stream"
                ):
                    raise RequestFailure("gateway_unexpected_content_type")
                usage = None
                finished = False
                candidate_seen = False
                with path.open("wb") as output:
                    while True:
                        raw = response.readline()
                        if not raw:
                            raise RequestFailure(
                                "incomplete_model_stream", retryable=True
                            )
                        output.write(raw)
                        size += len(raw)
                        lines += 1
                        digest.update(raw)
                        if self.monotonic() - started > 900:
                            raise RequestFailure("model_stream_timeout", retryable=True)
                        if not raw.startswith(b"data:"):
                            continue
                        event = raw[5:].strip()
                        if event == b"[DONE]":
                            if not finished and not candidate_seen:
                                raise RequestFailure(
                                    "chat_stream_without_finish", retryable=True
                                )
                            break
                        value = json.loads(event)
                        if value.get("error"):
                            # Unknown structured SSE errors are not blindly retried.
                            error = value["error"]
                            code = (
                                str(error.get("code", ""))
                                if isinstance(error, dict)
                                else ""
                            )
                            raise RequestFailure(
                                "gemini_stream_error",
                                retryable=code
                                in (
                                    "429",
                                    "500",
                                    "502",
                                    "503",
                                    "504",
                                    "RESOURCE_EXHAUSTED",
                                    "UNAVAILABLE",
                                ),
                                upstream_error=self._clean(json.dumps(error)),
                            )
                        candidate_seen |= bool(value.get("choices"))
                        finished |= any(
                            c.get("finish_reason") for c in value.get("choices") or []
                        )
                        usage = usage_record(value.get("usage")) or usage
                return {
                    "lines": SpoolLines(
                        path,
                        size=size,
                        digest=digest.hexdigest(),
                        line_count=lines,
                        owner=owner,
                    )
                }, usage
            raw = response.read()
            path.write_bytes(raw)
            size = len(raw)
            digest.update(raw)
            value = json.loads(raw)
            if value.get("error") or not value.get("choices"):
                raise RequestFailure("invalid_gemini_completion")
            return {
                "chat": value,
                "provider_evidence": evidence(),
                "gateway_headers": headers,
            }, usage_record(value.get("usage"))
        except RequestFailure as error:
            error.detail["response_stream_evidence"] = evidence()
            raise
        except (OSError, http.client.HTTPException) as error:
            raise RequestFailure(
                "gateway_transport_error",
                retryable=True,
                transport_type=type(error).__name__,
                response_stream_evidence=evidence(),
            ) from None
        finally:
            connection.close()
