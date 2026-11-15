"""Bounded, authenticated model transport shared by agent adapters."""
import json
import time
import tempfile
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import InfrastructureError
from .ga_runtime import filesystem_path
from .response_stream import SpoolLines


class GatewayModel:
    """Forward native SSE payloads only to the configured endpoint, with TLS."""
    def __init__(self, base_url, api_key, model, max_output_tokens=2048):
        if not base_url.startswith("https://"):
            raise ValueError("model gateway must use HTTPS")
        self.endpoint = base_url.rstrip("/")
        self.endpoint += "/responses" if self.endpoint.endswith("/v1") else "/v1/responses"
        self.api_key, self.model = api_key, model
        self.max_output_tokens = max_output_tokens
        self.output = None

    def __call__(self, payload):
        if not isinstance(payload, dict) or "input" not in payload:
            raise InfrastructureError("invalid native model payload")
        # No caller URL/header forwarding, server-side stored conversation, or
        # unmanaged built-in tools. Native file/memory tools run in the jail.
        if any(t.get("type") != "function" for t in (payload.get("tools") or [])):
            raise InfrastructureError("unregistered remote tool")
        payload = {k:v for k,v in payload.items() if k in
                   ("input", "instructions", "tools", "reasoning", "include", "tool_choice", "parallel_tool_calls")
                   and v is not None}
        payload.update(model=self.model, stream=True, store=False)
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        request = Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization":"Bearer " + self.api_key, "Content-Type":"application/json", "Accept":"text/event-stream"})
        total, completed, line_count = 0, False, 0
        digest = sha256()
        owner = None
        directory = filesystem_path(self.output / "model-streams") if self.output else None
        if directory is None:
            owner = tempfile.TemporaryDirectory(prefix="memorybenchmark-sse-")
            directory = Path(owner.name)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid4().hex + ".sse")
        deadline = time.monotonic() + 100
        try:
            with path.open("wb") as captured, urlopen(request, timeout=45) as response:
                for raw in response:
                    total += len(raw)
                    captured.write(raw); digest.update(raw); line_count += 1
                    if time.monotonic() > deadline:
                        raise InfrastructureError("model stream budget exceeded")
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if line.startswith("data:") and line[5:].strip() != "[DONE]":
                        try: event = json.loads(line[5:])
                        except ValueError: continue
                        if event.get("type") in ("error", "response.failed", "response.incomplete"):
                            raise InfrastructureError("model response did not complete")
                        completed |= event.get("type") == "response.completed"
                        if completed:
                            break
        except HTTPError as error:
            raise InfrastructureError("gateway_http_" + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise InfrastructureError("gateway_transport_error") from None
        if not completed:
            raise InfrastructureError("incomplete model stream")
        return {"lines":SpoolLines(path,size=total,digest=digest.hexdigest(),line_count=line_count,owner=owner)}
