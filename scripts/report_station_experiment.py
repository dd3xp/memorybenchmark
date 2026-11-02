"""Audit and summarize a single independent run, without consulting another run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.agent_sessions import MODEL_REQUEST_KINDS, native_model_request_kind, observed_reasoning_effort
from memorybenchmark.prototypes.station_independent import PROTOCOL, read
from memorybenchmark.watch import atomic_json as save_json
from scripts.audit_station_native import audit


def model_usage(folder, reasoning_effort=None, agent=None):
    """Count provider acknowledgements, never estimate missing usage as zero."""
    totals = {key: 0 for key in ("input_tokens", "output_tokens", "reasoning_tokens")}
    calls = usage_calls = effort_calls = 0
    kinds = dict.fromkeys(MODEL_REQUEST_KINDS, 0)
    request_efforts, provider_efforts = {}, {}
    for path in sorted((folder / "model").glob("*-response.json")):
        calls += 1
        request_path = path.with_name(path.name.replace("-response.json", "-request.json"))
        protocol = "hermes-session-1" if agent == "hermes" else "ga-session-1"
        request = read(request_path) if request_path.exists() else {}
        kind = native_model_request_kind(request, protocol)
        kinds[kind] += 1
        if request_path.exists():
            effort = observed_reasoning_effort(request)
            request_efforts[effort] = request_efforts.get(effort, 0) + 1
        completed = []
        for line in read(path).get("lines", []):
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            event = json.loads(line[5:])
            if event.get("type") == "response.completed":
                completed.append(event["response"])
        if len(completed) != 1:
            raise ValueError("Expected exactly one completed provider response")
        response = completed[0]
        effort = observed_reasoning_effort(response)
        provider_efforts[effort] = provider_efforts.get(effort, 0) + 1
        if effort != "unspecified":
            effort_calls += 1
        usage = response.get("usage") or {}
        if all(isinstance(usage.get(k), int) for k in ("input_tokens", "output_tokens")):
            usage_calls += 1
            totals["input_tokens"] += usage["input_tokens"]
            totals["output_tokens"] += usage["output_tokens"]
            totals["reasoning_tokens"] += (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0
    return {"calls": calls, "calls_with_usage": usage_calls, "calls_with_effort_acknowledgement": effort_calls,
            "request_kinds": kinds,
            "configured_reasoning_effort": reasoning_effort, "reasoning_policy": "native",
            "request_reasoning_efforts": request_efforts, "provider_reasoning_efforts": provider_efforts,
            "reported_tokens": totals, "usage_complete": calls == usage_calls,
            "reasoning_tokens_included_in_output_tokens": True}


def report(run, *, native_archive=None, source_commit=None, source_newlines=None):
    run = Path(run).resolve()
    pilot = read(run / "pilot.json")
    if pilot.get("protocol") != PROTOCOL or pilot["status"] != "completed":
        raise ValueError("A completed independent experiment is required")
    source_newlines = source_newlines or pilot.get("source_newlines", "raw")
    if source_newlines not in ("raw", "crlf"):
        raise ValueError("Source newline convention must be raw or crlf")
    replay = audit(run, native_archive=native_archive, source_commit=source_commit,
                   source_newlines=source_newlines)
    design = read(run / "design.json")
    rows = []
    for session in pilot["sessions"]:
        folder = run / "sessions" / session["name"]
        events = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        graph = read(folder / "graph.json")
        rows.append({"name": session["name"], "condition": pilot["memory_condition"],
            "llm_calls": session["llm_calls"],
            "worker_elapsed_seconds": session.get("worker_elapsed_seconds"),
            "model_usage": model_usage(folder, pilot.get("reasoning_effort"), pilot["agent"]),
            **analyze_trace(design, events, graph["task_run_id"], exact_references=False)})
    result = {"status": "completed_and_audited", "protocol": PROTOCOL,
        "experiment_id": pilot["experiment_id"], "agent": pilot["agent"], "condition": pilot["memory_condition"],
        "reasoning_effort": pilot.get("reasoning_effort", "low"),
        "tasks": len(rows), "successes": sum(r["success"] is True for r in rows),
        "totals": {key: sum(r[key] for r in rows) for key in ("distance", "moves", "operations", "llm_calls", "query_count", "unsupported_processing_count")},
        "replay": replay, "rows": rows}
    result["model_usage"] = {key: sum(row["model_usage"][key] for row in rows)
        for key in ("calls", "calls_with_usage", "calls_with_effort_acknowledgement")}
    result["model_usage"]["reported_tokens"] = {key: sum(row["model_usage"]["reported_tokens"][key] for row in rows)
        for key in ("input_tokens", "output_tokens", "reasoning_tokens")}
    result["model_usage"]["usage_complete"] = all(row["model_usage"]["usage_complete"] for row in rows)
    result["model_usage"]["request_kinds"] = {key: sum(row["model_usage"]["request_kinds"][key] for row in rows)
        for key in MODEL_REQUEST_KINDS}
    for field in ("request_reasoning_efforts", "provider_reasoning_efforts"):
        observed = {}
        for row in rows:
            for effort, count in row["model_usage"][field].items():
                observed[effort] = observed.get(effort, 0) + count
        result["model_usage"][field] = observed
    result["model_usage"]["reasoning_policy"] = "native"
    save_json(run / "analysis.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-archive", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-newlines", choices=("raw", "crlf"),
                        help="explicit Git export newline conversion; defaults to the frozen run's recorded convention")
    args = parser.parse_args()
    result = report(args.run, native_archive=args.native_archive, source_commit=args.source_commit,
                    source_newlines=args.source_newlines)
    save_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "replay")}))


if __name__ == "__main__":
    main()
