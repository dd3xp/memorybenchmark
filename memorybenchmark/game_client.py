"""Public game client for native code tools; contains no game rules or memory.

Python: ``from game_client import action; print(action('move', target='J'))``.
CLI: ``python -m game_client move J`` (or ``read``, ``inspect``, ``process``, ...).
The endpoint is task-scoped and supplied by the isolated runner.
"""
import argparse
import json
import os
import socket
import sys


ENDPOINT_ENV = "MEMORYBENCH_GAME_ENDPOINT"
DEFAULT_ENDPOINT = "unix:/tmp/memorybenchmark-game.sock"
MAX_MESSAGE = 4 * 1024**2


class DecisionBoundaryReached(BaseException):
    """End the current script while preserving feedback from its accepted step."""
    def __init__(self, response):
        self.response = response
        super().__init__(json.dumps(response, ensure_ascii=False))


def request(method, params=None, *, endpoint=None):
    endpoint = endpoint or os.environ.get(ENDPOINT_ENV, DEFAULT_ENDPOINT)
    if endpoint.startswith("unix:"):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        address = endpoint[5:]
    elif endpoint.startswith("tcp:127.0.0.1:"):
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        address = ("127.0.0.1", int(endpoint.rsplit(":", 1)[1]))
    else:
        raise ValueError("unsupported local game endpoint")
    with connection:
        # Model/background-review RPCs share the runner pipe. Do not time out
        # before a preceding bounded model request can release that pipe.
        connection.settimeout(300)
        connection.connect(address)
        payload = json.dumps({"method": method, "params": params or {}}, ensure_ascii=False)
        connection.sendall(payload.encode("utf-8") + b"\n")
        with connection.makefile("rb") as stream:
            line = stream.readline(MAX_MESSAGE + 1)
    if not line or len(line) > MAX_MESSAGE or not line.endswith(b"\n"):
        raise RuntimeError("incomplete game response")
    return json.loads(line)


def action(action, target=None, *, endpoint=None):
    """Execute exactly the requested public operation; never plan or retrieve."""
    args = {"action": action}
    if target is not None:
        args["target"] = target
    result = request("call", args, endpoint=endpoint)
    if result.get("error") == "decision_boundary":
        raise DecisionBoundaryReached(result)
    return result


def describe(*, endpoint=None):
    """Return only the public tool definition, for native MCP discovery."""
    return request("describe", endpoint=endpoint)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action")
    parser.add_argument("target", nargs="?")
    args = parser.parse_args()
    try:
        result = action(args.action, args.target)
    except DecisionBoundaryReached as stopped:
        print(json.dumps(stopped.response, ensure_ascii=False))
        raise SystemExit(75)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
