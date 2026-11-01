"""Verify and summarize archived GA routing probes without calling a model."""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def response_tools(response):
    """Use streamed completed items: a gateway may leave final output empty."""
    calls = {}
    final = None
    for line in response["lines"]:
        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
            continue
        event = json.loads(line[5:])
        if event.get("type") == "response.output_item.done":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                calls[item["call_id"]] = {"name": item["name"], "arguments": json.loads(item["arguments"])}
        elif event.get("type") == "response.completed":
            final = event["response"]
    if final is None:
        raise ValueError("Incomplete provider response")
    return list(calls.values()), final


def lookup_flags(tools, own_file):
    body = listing = False
    for tool in tools:
        args = tool["arguments"]
        if tool["name"] == "file_read":
            body |= PurePosixPath(str(args.get("path", "")).replace("\\", "/")).name == own_file
        elif tool["name"] == "code_run":
            script = str(args.get("script", args.get("code", "")))
            memory = "memory" in script or own_file in script
            enumerates = memory and any(x in script for x in ("glob", "listdir", "scandir", "ls "))
            listing |= enumerates
            body |= memory and (own_file in script or enumerates) and any(x in script for x in ("open(", "read_text", "read_bytes", "cat "))
    return {"body_read_requested": body, "directory_lookup_requested": listing,
            "memory_lookup_started": body or listing}


def verify_effort_pair(low, high):
    if low.get("reasoning") != {"effort": "low"} or high.get("reasoning") != {"effort": "high"}:
        raise ValueError("Unexpected effort configuration")
    control = deepcopy(high)
    control["reasoning"] = low["reasoning"]
    if control != low:
        raise ValueError("Effort comparison changed another input field")


def summarize(root):
    root = Path(root)
    observed = read(root / "cases/diagnosis.json")
    pilot = read(root / "cases/independent/pilot.json")
    native_plan = read(root / "native/run-plan.json")
    if native_plan["native_archive_sha256"] != pilot["archive_sha256"]:
        raise ValueError("Native source plan belongs to another archive")
    rows = [r for r in observed["rows"] if r["mode"] == "independent"]
    later = [r for r in rows if r["task"] != "T1"]
    if len(rows) != 20 or len(later) != 19:
        raise ValueError("Expected the completed independent 20-task GA run")
    contexts = {c["task"]: c for c in observed["cases"] if c["mode"] == "independent"}
    trials, groups = [], defaultdict(list)
    attempt_count = 0
    evidence_hashes = {}
    for batch, expected in (("counterfactual-v1", 63), ("counterfactual-v2", 27), ("counterfactual-effort", 18)):
        folder = root / "evidence" / batch
        path = folder / "result.json"
        result = read(path)
        evidence_hashes[batch] = sha256(path.read_bytes()).hexdigest()
        if result["completed"] != expected or len(result["rows"]) != expected:
            raise ValueError("Diagnostic batch incomplete")
        attempt_count += result["provider_attempts"]
        for trial in result["rows"]:
            if not trial["infrastructure_ok"] or trial["transport_failures"]:
                raise ValueError("Failed attempts require separate review")
            source = root / "cases/independent" / trial["task"] / f'{trial["source_call"]:03d}-request.json'
            if sha256(source.read_bytes()).hexdigest() != trial["source_request_sha256"]:
                raise ValueError("Source request fingerprint differs")
            body = contexts[trial["task"]]["input_documents"][trial["own_memory_file"]]
            if sha256(body.encode()).hexdigest() != trial["own_memory_sha256"]:
                raise ValueError("Supplied memory is not the recorded self-generated file")
            request = read(folder / (trial["name"] + "-request.json"))
            tools, final = response_tools(read(folder / (trial["name"] + "-response.json")))
            if tools != trial["tools"] or final.get("model") != "gpt-5.6-luna":
                raise ValueError("Stored result differs from actual provider output")
            effort = request["reasoning"]["effort"]
            if final.get("reasoning", {}).get("effort") != effort:
                raise ValueError("Provider did not acknowledge the requested effort")
            if trial["variant"] in ("own_full_body", "own_fact_section"):
                supplied = request["input"][-1]["content"][0]["text"].split("<self_generated_memory>\n", 1)[1].split("\n</self_generated_memory>", 1)[0]
                if supplied not in body:
                    raise ValueError("Intervention added memory content beyond the agent's own record")
            flags = lookup_flags(tools, trial["own_memory_file"])
            item = {"batch": batch, "task": trial["task"], "phase": trial["phase"],
                    "variant": trial["variant"], "repetition": trial["repetition"], "reasoning_effort": effort,
                    "source_request_sha256": trial["source_request_sha256"],
                    "probe_request_sha256": sha256((folder / (trial["name"] + "-request.json")).read_bytes()).hexdigest(),
                    "own_memory_file": trial["own_memory_file"], "own_memory_sha256": trial["own_memory_sha256"],
                    **flags, "next_move_targets": trial["move_targets"],
                    "direct_matching_route_step": trial["direct_known_matching_route_step"],
                    "working_checkpoint_requested": bool(trial["working_checkpoint_requested"]),
                    "tool_names": [t["name"] for t in tools], "usage": trial["usage"]}
            trials.append(item)
            groups[batch, trial["phase"], trial["variant"]].append(item)
    effort_folder = root / "evidence/counterfactual-effort"
    for task in ("T3", "T13", "T18"):
        for repetition in range(1, 4):
            verify_effort_pair(*(read(effort_folder / f"opening-{task}-{v}_reasoning_effort-{repetition}-request.json") for v in ("low", "high")))
    totals = [{"batch": batch, "phase": phase, "variant": variant, "trials": len(chosen),
               **{key: sum(r[key] for r in chosen) for key in
                  ("memory_lookup_started", "body_read_requested", "directory_lookup_requested", "direct_matching_route_step", "working_checkpoint_requested")}}
              for (batch, phase, variant), chosen in sorted(groups.items())]
    own_reads = {phase: [] for phase in ("before", "after")}
    for row in later:
        for tool in row["tools"]:
            if tool["name"] == "file_read" and PurePosixPath(tool["args"].get("path", "")).name in row["own_documents"]:
                own_reads["before" if tool["before_game_done"] else "after"].append(row["task"])
    checks = read(root / "native-function-check.json")
    native_hashes = {name: sha256((root / "native" / name).read_bytes()).hexdigest()
                     for name in ("ga.py", "agentmain.py", "agent_loop.py", "llmcore.py")}
    if checks["native_ga_sha256"] != native_hashes["ga.py"] or not checks["passed"]:
        raise ValueError("Native function verification belongs to different source")
    last = later[-1]
    unindexed = [n for n in last["own_documents"] if n not in last["index"] and Path(n).stem not in last["index"]]
    return {"kind": "verified_ga_memory_routing_diagnosis_not_full_task_ablation", "date": "2026-11-01",
            "configuration": {"agent": "GA", "native_commit": native_plan["native_commit"],
                              "native_archive_sha256": pilot["archive_sha256"],
                              "model": "gpt-5.6-luna", "formal_run_reasoning_effort": "low",
                              "executed_native_source_sha256": native_hashes},
            "formal_run_observation": {"tasks": 20, "successes": sum(r["success"] for r in rows),
              "tasks_writing_game_markdown": sum(any(n.endswith(".md") and "lanting" in n for n in s["content_changed"]) for s in pilot["sessions"]),
              "later_tasks": 19, "index_delivered": sum(r["index_delivered"] for r in later),
              "own_body_read_before_game_end_tasks": sorted(set(own_reads["before"])),
              "own_body_read_only_for_closeout_tasks": sorted(set(own_reads["after"])),
              "working_checkpoint_used_tasks": [r["task"] for r in later if any(t["name"] == "update_working_checkpoint" and t["before_game_done"] for t in r["tools"])],
              "unindexed_extra_game_documents_at_T20": unindexed,
              "core_game_document_is_indexed": "lanting_easy20_fixed_types_v5_t1.md" in last["index"]},
            "native_function_execution_checks": checks, "provider_attempts": attempt_count,
            "valid_counterfactual_responses": len(trials), "same_batch_effort_pairs_verified": 9,
            "case_tasks": ["T3", "T13", "T18"], "repetitions_per_condition_per_case": 3,
            "condition_totals": totals, "trials": trials, "evidence_result_sha256": evidence_hashes,
            "scope": "Next-response tool selection at fixed real inputs; no tools or full games executed by probes. Formal experiment data and agent code were not changed. These are mechanism diagnostics, not full-task distance improvements.",
            "finding": "The low-effort configuration suppresses self-initiated retrieval in GA's index-only automatic loading design. A same-batch effort intervention restores most initial body-read requests; providing the agent's own facts also corrects most immediate route choices."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.evidence_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"responses": result["valid_counterfactual_responses"], "attempts": result["provider_attempts"],
                      "effort_pairs_verified": result["same_batch_effort_pairs_verified"]}))


if __name__ == "__main__":
    main()
