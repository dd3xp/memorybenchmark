"""Public operations bound to one runner-owned task, shared by transports."""
from copy import deepcopy

from .game import ProtocolError


def validate_request(request):
    if not isinstance(request, dict) or request.get("command") not in ("read", "action"):
        return {"error": "invalid_request", "message": "只能操作当前任务。"}
    if set(request) - {"command", "request_id", "action", "expected_revision"}:
        return {"error": "invalid_request", "message": "未知请求参数。"}
    return None


def dispatch_current(adapter, request):
    """Never expose task creation, selection, checkpoints or evaluator data."""
    error = validate_request(request)
    if error:
        return error
    if request["command"] == "action" and adapter.game.done:
        return adapter._public({"observation": adapter.game.observation(),
                                "feedback": "任务已结束。", "outcome": "closed"})
    request = deepcopy(request)
    if request["command"] == "action" and "expected_revision" not in request:
        request_id = request.get("request_id")
        if isinstance(request_id, str) and 0 < len(request_id) <= 128:
            if not hasattr(adapter, "_native_revisions"):
                adapter._native_revisions = {}
            request["expected_revision"] = adapter._native_revisions.setdefault(request_id, adapter.game.revision)
    try:
        return adapter.dispatch(request)
    except ProtocolError as error:
        return {"error": "protocol_error", "message": str(error)}
