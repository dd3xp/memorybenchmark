"""Provider-only usage; accept unchanged DONE-terminated Chat streams, no invented effort."""

import json
from collections import Counter
from pathlib import Path


def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def stream_events(raw):
    if raw.get("chat"):
        return [raw["chat"]]
    events = []
    for line in raw.get("lines", []):
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            events.append(json.loads(line[5:]))
    assert any(
        line.startswith("data:") and line[5:].strip() == "[DONE]"
        for line in raw.get("lines", [])
    ), "Chat stream lacks DONE"
    assert any(e.get("choices") for e in events), "No native Chat candidate"
    return events


def model_usage(folder, reasoning_effort=None, agent=None):
    from memorybenchmark.agent_sessions import (
        MODEL_REQUEST_KINDS,
        native_model_request_kind,
        observed_reasoning_effort,
    )

    calls = usage_calls = reasoning_calls = 0
    totals = dict.fromkeys(("input_tokens", "output_tokens", "reasoning_tokens"), 0)
    kinds = dict.fromkeys(MODEL_REQUEST_KINDS, 0)
    efforts = Counter()
    for response in sorted((folder / "model").glob("*-response.json")):
        calls += 1
        request = read(
            response.with_name(response.name.replace("-response.json", "-request.json"))
        )
        kinds[native_model_request_kind(request, "hermes-session-1")] += 1
        efforts[observed_reasoning_effort(request)] += 1
        events = stream_events(read(response))
        usages = [e["usage"] for e in events if isinstance(e.get("usage"), dict)]
        usage = usages[-1] if usages else {}
        if all(
            isinstance(usage.get(k), int)
            for k in ("prompt_tokens", "completion_tokens")
        ):
            usage_calls += 1
            totals["input_tokens"] += usage["prompt_tokens"]
            totals["output_tokens"] += usage["completion_tokens"]
        detail = usage.get("completion_tokens_details") or {}
        if isinstance(detail.get("reasoning_tokens"), int):
            reasoning_calls += 1
            totals["reasoning_tokens"] += detail["reasoning_tokens"]
    return {
        "calls": calls,
        "calls_with_usage": usage_calls,
        "calls_with_effort_acknowledgement": 0,
        "request_kinds": kinds,
        "configured_reasoning_effort": reasoning_effort,
        "reasoning_policy": "native",
        "request_reasoning_efforts": dict(efforts),
        "provider_reasoning_efforts": {"unspecified": calls},
        "reported_tokens": totals,
        "usage_complete": calls == usage_calls,
        "reasoning_tokens_included_in_output_tokens": True,
        "reasoning_usage_reported_calls": reasoning_calls,
        "reasoning_usage_unknown_calls": calls - reasoning_calls,
    }


def install():
    import scripts.report_station_experiment as module

    module.model_usage = model_usage
