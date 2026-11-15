"""Distinguish physical failures, affected RPCs and preserved abandoned attempts."""

from collections import Counter
import json
from pathlib import Path


def transport_costs(run):
    failures = Counter()
    failed, completed, historical = set(), set(), set()
    usage_unknown = 0
    reported = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
    abandoned_successful_responses = 0
    ledgers = list((Path(run) / "sessions").glob("*/transport-attempts.jsonl"))
    ledgers += list((Path(run) / "failed-attempts").glob("*/transport-attempts.jsonl"))
    for ledger in ledgers:
        abandoned = ledger.parent.parent.name == "failed-attempts"
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            key = (str(ledger.parent), event.get("call"), event.get("request_sha256"))
            if event.get("kind") == "request_failed":
                failures[event["reason"]] += 1
                failed.add(key)
                if abandoned:
                    historical.add(key)
                usage_unknown += not bool(event.get("reported_usage"))
            elif event.get("kind") == "request_completed":
                completed.add(key)
                if abandoned:
                    abandoned_successful_responses += 1
                    usage = event.get("reported_usage") or {}
                    for field in ("input_tokens", "output_tokens"):
                        if isinstance(usage.get(field), int):
                            reported[field] += usage[field]
                    reasoning = (usage.get("output_tokens_details") or {}).get(
                        "reasoning_tokens"
                    )
                    if isinstance(reasoning, int):
                        reported["reasoning_tokens"] += reasoning
    return {
        "failure_events": sum(failures.values()),
        "reasons": dict(failures),
        "affected_rpcs": len(failed),
        "recovered_affected_rpcs": len(failed & completed),
        "active_pending_rpcs": len(failed - completed - historical),
        "historical_unrecovered_rpcs": len((failed - completed) & historical),
        "failure_events_without_reported_usage": usage_unknown,
        "abandoned_attempt_successful_responses": abandoned_successful_responses,
        "abandoned_attempt_reported_tokens": reported,
        "unreported_usage_is_unknown": True,
        "reasoning_tokens_are_output_subset": True,
    }
