"""Audit reviewed station facts through native memory and actual game decisions.

Requires private evidence. Exports only game facts, counts, event references and
hashes. Literal fact patterns are a manual review input, not a general semantic
parser. Action compatibility is not proof of internal memory causality.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

from memorybenchmark.prototypes.station_choice import station_decisions
from scripts.audit_station_decisions import align_tools


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def match_facts(text, specification):
    """All pieces of an alternative must occur within one memory entry."""
    blocks = re.split(r"\n§\n", text)
    result = {}
    for fact in specification["facts"]:
        matches = []
        for pieces in fact["alternatives"]:
            for block in blocks:
                if pieces and all(piece in block for piece in pieces):
                    matches.append({"pieces": pieces, "entry_sha256": sha256(block.encode()).hexdigest()})
        if matches:
            result[fact["station"]] = {"capability": fact["capability"], "matches": matches}
    return result


def in_payload(fact, payload):
    forwarded = json.dumps(payload, ensure_ascii=False)
    return any(all(json.dumps(p, ensure_ascii=False)[1:-1] in forwarded for p in match["pieces"])
               for match in fact["matches"])


def parsed_outputs(payload):
    calls = {x.get("call_id"): x for x in payload.get("input", []) if x.get("type") == "function_call"}
    for item in payload.get("input", []):
        if item.get("type") != "function_call_output":
            continue
        raw = item.get("output", "")
        if not isinstance(raw, str):
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        yield item.get("call_id"), calls.get(item.get("call_id"), {}), value, raw


def game_outputs(value):
    if isinstance(value, dict):
        if isinstance(value.get("observation"), dict) and isinstance(value.get("feedback"), dict):
            yield value
        else:
            for nested in value.values():
                yield from game_outputs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from game_outputs(nested)


def fact_key(feedback, steps):
    return (steps, feedback.get("station"), feedback.get("capability"), feedback.get("result"))


def response_game_actions(response):
    """Read function calls only, without inspecting model reasoning or prose."""
    items = {}
    for line in response["lines"]:
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except ValueError:
            continue
        candidates = ([event.get("item", {})] if event.get("type") == "response.output_item.done" else
                      event.get("response", {}).get("output", []) if event.get("type") == "response.completed" else [])
        for item in candidates:
            if item.get("type") == "function_call":
                items[item.get("call_id") or item.get("id")] = item
    result = []
    for item in items.values():
        arguments = json.loads(item.get("arguments", "{}"))
        if item.get("name") == "game_action":
            result.append(arguments)
        elif item.get("name") == "tool_call":
            dispatched = arguments.get("calls", [arguments])
            result.extend(c["arguments"] for c in dispatched if c.get("name") == "game_action")
    return result


def action_request_numbers(events, run_id, messages):
    current = [e for e in events if e["task_run_id"] == run_id and e["kind"] == "action"]
    start = next(e for e in events if e["task_run_id"] == run_id and e["kind"] == "task_started")
    available, cursor, number, result = start["delivered"]["observation"]["available_actions"], 0, 0, {}
    for message in messages:
        if message.get("kind") != "request":
            continue
        if message.get("method") == "model":
            number += 1
        elif message.get("method") == "task_end":
            break
        elif message.get("method") == "game" and message.get("params", {}).get("command") == "action":
            action = message["params"]["action"]
            if action not in available:
                continue
            assert current[cursor]["action"] == action
            event = current[cursor]
            result[event["event_id"]] = number
            available = event["delivered"]["observation"]["available_actions"]
            cursor += 1
    assert cursor == len(current)
    return result


def audit(root, patterns):
    pilot, design = read(root/"pilot.json"), read(root/"design.json")
    assert pilot["status"] == "completed" and pilot["agent"] == "hermes"
    truth = design["private_worlds"][pilot["world"]]
    assert {f["station"]: f["capability"] for f in patterns["facts"]} == truth
    snapshots, decisions, failures, native, supports = [], [], [], [], defaultdict(list)
    previous, ever_saved = root/"baseline", set()
    for session in pilot["sessions"]:
        if session["condition"] == "clear":
            continue
        folder = root/"sessions"/session["name"]
        incoming_file = previous/"memories/MEMORY.md"
        incoming_text = incoming_file.read_text(encoding="utf-8") if incoming_file.exists() else ""
        outgoing_file = folder/"memory-after/memories/MEMORY.md"
        outgoing_text = outgoing_file.read_text(encoding="utf-8")
        incoming, outgoing = match_facts(incoming_text, patterns), match_facts(outgoing_text, patterns)
        messages = [json.loads(s) for s in (folder/"audit.jsonl").read_text(encoding="utf-8").splitlines()]
        events = [json.loads(s) for s in (folder/"events.jsonl").read_text(encoding="utf-8").splitlines()]
        graph = read(folder/"graph.json")
        summary = read(folder/"summary.json")
        current = [e for e in events if e["task_run_id"] == graph["task_run_id"]]
        prior = [e for e in events if e["event_id"] < current[0]["event_id"]]
        prior_facts = {e["delivered"]["feedback"]["station"]: e["delivered"]["feedback"]["capability"]
                       for e in prior if e["delivered"]["feedback"].get("kind") == "station_information"}
        branch_data = station_decisions(design, events, graph["task_run_id"])
        windows = align_tools(events, graph["task_run_id"], messages, branch_data)
        action_requests = action_request_numbers(events, graph["task_run_id"], messages)
        request_files = sorted((folder/"model").glob("*-request.json"))
        relevant_numbers = {1, *action_requests.values()}
        payloads, delivery, memory_results, game_result_lengths, compactions = {}, {}, {}, {}, set()
        for path in request_files:
            number = int(path.name.split("-")[0])
            payload = read(path)
            if number in relevant_numbers:
                payloads[number] = payload
            for item in payload.get("input", []):
                if item.get("role") == "user" and isinstance(item.get("content"), str) and item["content"].startswith("[CONTEXT COMPACTION"):
                    compactions.add(sha256(item["content"].encode()).hexdigest())
            for call_id, call, value, raw in parsed_outputs(payload):
                if call.get("name") == "memory" and call_id not in memory_results:
                    error = value.get("error", "") if isinstance(value, dict) else ""
                    error_kind = ("capacity" if re.search(r"exceed the limit|put memory at|limit by", error, re.I)
                                  else "missing_target" if "Missing required target" in error
                                  else "entry_match" if "No entry matched" in error else "other" if error else None)
                    memory_results[call_id] = {"first_request": number, "request_sha256": digest(path),
                        "success": value.get("success") if isinstance(value, dict) else None,
                        "error_kind": error_kind, "usage": value.get("usage") if isinstance(value, dict) else None}
                for output in game_outputs(value):
                    game_result_lengths.setdefault(call_id, len(raw))
                    feedback, observation = output["feedback"], output["observation"]
                    if feedback.get("kind") == "station_information":
                        delivery.setdefault(fact_key(feedback, observation["steps"]),
                                            {"request": number, "request_sha256": digest(path)})
        first_payload = payloads[1]
        local_facts, local_deliveries = {}, defaultdict(list)
        for event in current:
            feedback = event["delivered"]["feedback"]
            if feedback.get("kind") != "station_information":
                continue
            station, capability = feedback["station"], feedback["capability"]
            assert capability == truth[station]
            key = fact_key(feedback, event["delivered"]["observation"]["steps"])
            assert key in delivery, (session["name"], event["event_id"], "feedback not present in an actual forwarded tool output")
            supports[station].append({"task": session["task_id"], "event_id": event["event_id"],
                                      "native_delivery": delivery[key], "source_events_sha256": digest(folder/"events.jsonl")})
            if feedback.get("result") == "unsupported":
                number = action_requests[event["event_id"]]
                emitted = response_game_actions(read(folder/"model"/f"{number:03d}-response.json"))
                assert any(a.get("action") == "process" for a in emitted), (session["name"], event["event_id"], number, emitted)
                fact = incoming.get(station)
                visible_keys = {fact_key(g["feedback"], g["observation"]["steps"])
                    for _, _, value, _ in parsed_outputs(payloads[number]) for g in game_outputs(value)
                    if g["feedback"].get("kind") == "station_information"}
                failures.append({"task": session["task_id"], "event_id": event["event_id"],
                    "station": station, "capability": capability,
                    "same_task_previous_station_feedback_event": station in local_facts,
                    "same_task_feedback_delivered_before_process_decision": any(x["request"] <= number for x in local_deliveries[station]),
                    "same_task_original_feedback_still_in_process_input": any(x["key"] in visible_keys for x in local_deliveries[station]),
                    "prior_task_already_delivered_station_capability": station in prior_facts,
                    "specific_station_fact_in_incoming_memory": fact is not None,
                    "specific_station_fact_in_actual_process_request": bool(fact and in_payload(fact, payloads[number])),
                    "model_request": number})
            local_facts[station] = capability
            local_deliveries[station].append({"key": key, "request": delivery[key]["request"]})
        for stage, window in zip(branch_data["stages"], windows["stages"]):
            branch = stage["first_postcollection_branch_choice"]
            assert branch is not None
            number = window["before_first_postcollection_branch_choice"]["model_request_count"]
            assert number == action_requests[branch["event_id"]]
            branch_action = next(e["action"] for e in current if e["event_id"] == branch["event_id"])
            response_file = folder/"model"/f"{number:03d}-response.json"
            assert {"action": branch_action["type"], "target": branch_action["target"]} in response_game_actions(read(response_file))
            chosen, required = branch["station"], stage["required_kind"]
            group = next(g for g in design["public"]["capability_groups"].values() if chosen in g["stations"])
            group_stations = set(group["stations"])
            known = {s:k for s,k in prior_facts.items() if s in group_stations}
            stored = {s:f for s,f in incoming.items() if s in known}
            matching = [s for s,k in known.items() if k == required]
            chosen_excluded = chosen in known and known[chosen] != required
            relevant = {s:f for s,f in stored.items() if f["capability"] == required or s == chosen and chosen_excluded}
            delivered = {s:f for s,f in relevant.items() if in_payload(f, payloads[number])}
            chosen_delivered = chosen in delivered and chosen_excluded
            matches_delivered = [s for s,f in delivered.items() if f["capability"] == required]
            missing = [s for s in matching if s not in stored]
            current_facts = {e["delivered"]["feedback"]["station"]: e["delivered"]["feedback"]["capability"]
                for e in current if e["event_id"] < branch["event_id"] and e["delivered"]["feedback"].get("kind") == "station_information"
                and delivery[fact_key(e["delivered"]["feedback"], e["delivered"]["observation"]["steps"])]["request"] <= number}
            visible_states = [g["observation"] for _, _, value, _ in parsed_outputs(payloads[number])
                              for g in game_outputs(value)]
            latest_state = max(visible_states, key=lambda o:o["steps"]) if visible_states else None
            decisions.append({"task": session["task_id"], "stage": stage["stage_index"]+1,
                "required_kind": required, "chosen": chosen, "actual_match": truth[chosen] == required,
                "nearest": branch["pre_task_history"]["selected_is_geographically_nearest"],
                "nearest_candidates": branch["pre_task_history"]["nearest_candidates"],
                "all_nearest_stations_actually_nonmatching": all(truth[s] != required for s in branch["pre_task_history"]["nearest_candidates"]),
                "prior_direct_station_facts": known, "prior_direct_matching_stations": matching,
                "chosen_excluded_by_prior_direct_feedback": chosen_excluded,
                "incoming_saved_group_facts": {s:f["capability"] for s,f in stored.items()},
                "missing_prior_matching_facts": missing,
                "missing_matching_facts_never_saved": [s for s in missing if s not in ever_saved],
                "missing_matching_facts_saved_then_lost": [s for s in missing if s in ever_saved],
                "saved_relevant_fact_in_first_request": [s for s,f in relevant.items() if in_payload(f, first_payload)],
                "saved_relevant_fact_in_decision_request": list(delivered),
                "saved_relevant_fact_absent_from_decision_request": [s for s in relevant if s not in delivered],
                "saved_matching_fact_in_decision_request": matches_delivered,
                "specific_exclusion_fact_in_decision_request": chosen_delivered,
                "same_task_station_facts_before_branch": current_facts,
                "latest_structured_public_state_in_decision_input": ({
                    **{k: latest_state.get(k) for k in ("location", "steps", "stage_index", "raw", "processed")},
                    "required_kind": latest_state["task"]["required_kind"]} if latest_state else None),
                "model_request": number, "request_sha256": digest(folder/"model"/f"{number:03d}-request.json"),
                "actual_branch_action_present_in_corresponding_model_response": True,
                "response_sha256": digest(response_file),
                "incoming_memory_sha256": digest(incoming_file) if incoming_file.exists() else None,
                "literal_fact_support": {s:f["matches"] for s,f in relevant.items()},
                "branch_event_id": branch["event_id"]})
        newly_observed = {e["delivered"]["feedback"]["station"] for e in current
                          if e["delivered"]["feedback"].get("kind") == "station_information"} - prior_facts.keys()
        completed = [e["delivered"]["feedback"]["station"] for e in current
                     if e["delivered"]["feedback"].get("result") == "processed"]
        snapshots.append({"task": session["task_id"], "characters": len(outgoing_text),
            "saved_facts": {s:f["capability"] for s,f in outgoing.items()},
            "source_memory_sha256": digest(outgoing_file),
            "literal_support": {s:f["matches"] for s,f in outgoing.items()},
            "newly_observed_stations": sorted(newly_observed),
            "new_facts_saved_immediately": sorted(newly_observed & outgoing.keys()),
            "new_facts_missing_after_task": sorted(newly_observed - outgoing.keys()),
            "successful_stage_stations": [{"stage": i+1, "station": station,
                                           "capability_saved_at_task_end": station in outgoing}
                                          for i,station in enumerate(completed)],
            "facts_removed_since_previous": sorted(incoming.keys() - outgoing.keys()),
            "changed_persistent_content": summary["content_changed"]})
        native.append({"task": session["task_id"], "model_calls": len(request_files),
            "distinct_forwarded_compaction_summaries": len(compactions),
            "memory_tool_results": list(memory_results.values()),
            "game_tool_result_characters": {"count": len(game_result_lengths),
                "mean": sum(game_result_lengths.values())/len(game_result_lengths),
                "max": max(game_result_lengths.values())},
            "source_audit_sha256": digest(folder/"audit.jsonl")})
        ever_saved.update(outgoing)
        previous = folder/"memory-after"
    fact_rows = []
    for station, capability in truth.items():
        exposure = supports[station]
        saved = [s["task"] for s in snapshots if station in s["saved_facts"]]
        fact_rows.append({"station": station, "capability": capability,
            "directly_observed": bool(exposure), "first_observed_task": exposure[0]["task"] if exposure else None,
            "observations": exposure, "first_saved_task": saved[0] if saved else None,
            "saved_at_task_ends": saved, "saved_in_final_memory": station in snapshots[-1]["saved_facts"]})
    matching_opportunities = [d for d in decisions if d["prior_direct_matching_stations"]]
    wrong = [d for d in decisions if not d["actual_match"]]
    contradictory = [d for d in wrong if d["chosen_excluded_by_prior_direct_feedback"]]
    total = {
        "main_tasks": len(snapshots), "first_branches": len(decisions),
        "directly_observed_facts": sum(f["directly_observed"] for f in fact_rows),
        "immediately_saved_on_first_observation": sum(len(s["new_facts_saved_immediately"]) for s in snapshots),
        "ever_saved_facts": len(ever_saved), "final_saved_facts": len(snapshots[-1]["saved_facts"]),
        "observed_but_never_saved": [f["station"] for f in fact_rows if f["directly_observed"] and not f["saved_at_task_ends"]],
        "prior_direct_matching_opportunities": len(matching_opportunities),
        "matching_opportunity_with_saved_matching_fact": sum(bool(d["saved_matching_fact_in_decision_request"]) for d in matching_opportunities),
        "matching_opportunity_without_saved_matching_fact": sum(not d["saved_matching_fact_in_decision_request"] for d in matching_opportunities),
        "saved_matching_fact_but_wrong_first_branch": sum(bool(d["saved_matching_fact_in_decision_request"]) and not d["actual_match"] for d in decisions),
        "saved_matching_fact_and_matching_first_branch": sum(bool(d["saved_matching_fact_in_decision_request"]) and d["actual_match"] for d in decisions),
        "wrong_first_branches": len(wrong), "prior_directly_excluded_first_branches": len(contradictory),
        "excluded_first_branch_specific_fact_delivered": sum(d["specific_exclusion_fact_in_decision_request"] for d in contradictory),
        "excluded_first_branch_only_matching_alternative_delivered": sum(not d["specific_exclusion_fact_in_decision_request"] and bool(d["saved_matching_fact_in_decision_request"]) for d in contradictory),
        "excluded_first_branch_no_relevant_saved_fact_delivered": sum(not d["saved_relevant_fact_in_decision_request"] for d in contradictory),
        "saved_relevant_fact_absent_from_decision_input": sum(bool(d["literal_fact_support"]) and not d["saved_relevant_fact_in_decision_request"] for d in decisions),
        "individual_saved_relevant_facts_absent_from_decision_input": sum(len(d["saved_relevant_fact_absent_from_decision_request"]) for d in decisions),
        "unsupported_processes": len(failures),
        "unsupported_after_previous_same_task_feedback_event": sum(f["same_task_previous_station_feedback_event"] for f in failures),
        "unsupported_after_same_task_fact_delivered_to_model": sum(f["same_task_feedback_delivered_before_process_decision"] for f in failures),
        "unsupported_with_original_same_task_feedback_still_in_input": sum(f["same_task_original_feedback_still_in_process_input"] for f in failures),
        "unsupported_with_specific_incoming_fact_in_process_input": sum(f["specific_station_fact_in_actual_process_request"] for f in failures),
        "memory_tool_errors": dict(Counter(m["error_kind"] for n in native for m in n["memory_tool_results"] if m["error_kind"])),
        "distinct_forwarded_compaction_summaries": sum(n["distinct_forwarded_compaction_summaries"] for n in native),
    }
    total["saved_matching_fact_by_stage"] = {}
    for stage in (1,2):
        cases = [d for d in decisions if d["stage"] == stage and d["saved_matching_fact_in_decision_request"]]
        hard = [d for d in cases if d["all_nearest_stations_actually_nonmatching"]]
        total["saved_matching_fact_by_stage"][str(stage)] = {
            "opportunities": len(cases), "matching_first_choices": sum(d["actual_match"] for d in cases),
            "all_nearest_actually_nonmatching": len(hard),
            "matching_choices_when_all_nearest_nonmatching": sum(d["actual_match"] for d in hard)}
    informative_wrong = [d for d in wrong if d["saved_relevant_fact_in_decision_request"]]
    total["wrong_choices_with_saved_relevant_fact_and_correct_visible_task_type"] = sum(
        d["latest_structured_public_state_in_decision_input"] is not None and
        d["latest_structured_public_state_in_decision_input"]["required_kind"] == d["required_kind"] and
        d["latest_structured_public_state_in_decision_input"]["stage_index"] == d["stage"]-1
        for d in informative_wrong)
    limits = {int(match.group(1).replace(",", "")) for n in native for m in n["memory_tool_results"]
              for match in [re.search(r"/([\d,]+)", m["usage"] or "")] if match}
    total["observed_native_memory_character_limits"] = sorted(limits)
    return {"kind": "reviewed_all_retained_station_fact_pipeline_not_internal_memory_causality",
        "source_pilot_sha256": digest(root/"pilot.json"), "world": pilot["world"],
        "source_patterns_sha256": sha256(json.dumps(patterns, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "analysis_sha256": digest(Path(__file__)), "scope": patterns["scope"], "totals": total,
        "facts": fact_rows, "snapshots": snapshots, "decisions": decisions,
        "unsupported_processing": failures, "native_context_and_memory_tools": native,
        "limitations": ["All 20 main tasks only; clear probes have no inherited generated memory.",
            "Manual semantic review encoded as literal patterns; counts are not a proposed general metric.",
            "Absent means no unambiguous capability fact in the reviewed persistent snapshots, not no internal latent knowledge.",
            "A compatible choice can be coincidental. An incompatible choice does not reveal internal causal reasoning.",
            "Native tool-error counts cover parseable results visible in later model requests, not every terminal tool result.",
            "Current-task feedback, capacity errors, and compaction are reported separately; their causal effects are not experimentally isolated."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--patterns", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.run, read(args.patterns))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result["totals"], ensure_ascii=False))


if __name__ == "__main__":
    main()
