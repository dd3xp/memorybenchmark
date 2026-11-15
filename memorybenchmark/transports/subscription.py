"""Narrow, evidence-backed exceptions; genuine authentication failures stop."""

import json

CONCURRENCY_PREFIX = (
    "ChatGPT request failed: upstream_error: authentication failed (status=503): "
)
QUOTA_MESSAGE = "The ChatGPT user has reached their Subscription Sharing usage limit. Ask the user to try again after their usage limit resets or use an API key instead."


def classification(error):
    detail = error.detail
    try:
        if (
            detail.get("reason") == "gateway_http_401"
            and detail.get("http_status") == 401
        ):
            outer = json.loads(detail.get("body", ""))
            item = outer.get("error", {})
            message = item.get("message", "")
            if (
                outer.get("type") == "error"
                and item.get("type") == "api_error"
                and item.get("code") in (None, "")
                and message.startswith(CONCURRENCY_PREFIX)
                and json.loads(message[len(CONCURRENCY_PREFIX) :])
                == {"error": "Too many concurrent requests"}
            ):
                return "wrapped-auth-service-concurrency-1"
        if detail.get("reason") == "model_response_failed":
            outer = json.loads(detail.get("upstream_error", ""))
            item = outer.get("error", {})
            if (
                outer.get("type") == "error"
                and item.get("code") == "subscription_sharing_usage_limit_exceeded"
                and item.get("type") == "invalid_request_error"
                and item.get("param") is None
                and item.get("message") == QUOTA_MESSAGE
            ):
                return "subscription-sharing-quota-wait-1"
    except (ValueError, TypeError, AttributeError):
        pass
    return None


def install():
    from ..request_recovery import RecoveringGatewayModel, RequestFailure

    if getattr(RecoveringGatewayModel, "_subscription_envelopes_v1", False):
        return
    original = RecoveringGatewayModel._attempt

    def attempt(self, body):
        try:
            return original(self, body)
        except RequestFailure as error:
            policy = classification(error)
            if policy:
                error.retryable = True
                error.detail["retry_classification"] = policy
                if policy == "subscription-sharing-quota-wait-1":
                    error.retry_after = max(300, error.retry_after)
            raise

    RecoveringGatewayModel._attempt = attempt
    RecoveringGatewayModel._subscription_envelopes_v1 = True
