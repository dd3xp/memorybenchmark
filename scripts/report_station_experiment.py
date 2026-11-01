"""Audit and summarize a single independent run, without consulting another run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_independent import PROTOCOL, read
from memorybenchmark.watch import atomic_json as save_json
from scripts.audit_station_native import audit


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
            **analyze_trace(design, events, graph["task_run_id"], exact_references=False)})
    result = {"status": "completed_and_audited", "protocol": PROTOCOL,
        "experiment_id": pilot["experiment_id"], "agent": pilot["agent"], "condition": pilot["memory_condition"],
        "tasks": len(rows), "successes": sum(r["success"] is True for r in rows),
        "totals": {key: sum(r[key] for r in rows) for key in ("distance", "moves", "operations", "llm_calls", "query_count", "unsupported_processing_count")},
        "replay": replay, "rows": rows}
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
