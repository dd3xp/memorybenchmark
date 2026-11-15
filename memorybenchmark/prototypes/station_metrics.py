"""Offline, exploratory graph metrics for station-memory experiments.

Evidence means delivered environment feedback, never the agent's internal
knowledge. Full-world truth is used for grading and a physical route bound;
opportunity gates use only preceding feedback and the public candidate family.
No part of this module is called by the game or an agent runtime.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from math import log2
from statistics import mean

from .station_capability import compatible_worlds, map_world, task_stages, stage_signature, conditional_capabilities, experience_context, region_matches
from .station_knowledge import evidence_support, support_count, information_gain, matching_stations, historical_status, capability_options, supports, freeze_capability, report_world_ids, capability_for
from .station_routes import known_world_route, station_branches

VERSION = "station-graph-memory-metrics-exploratory-5"


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def feedback_events(events):
    return [e for e in events if e.get("delivered", {}).get("feedback", {}).get("kind") == "station_information"]


class Evidence:
    def __init__(self, design):
        self.design = design
        self.locations = design["public"]["locations"]
        self.stations = tuple(s for s, p in self.locations.items() if p["kind"] == "station")

    def signature(self, events):
        if not conditional_capabilities(self.design):
            return tuple(sorted({(e['delivered']['feedback']['station'], freeze_capability(e['delivered']['feedback']['capability']))
                                 for e in feedback_events(events)}))
        return tuple(sorted({(e["delivered"]["feedback"]["station"], e['delivered']['feedback'].get('requirement', ''), freeze_capability(e["delivered"]["feedback"]["capability"]))
                             for e in feedback_events(events)}))

    @lru_cache(maxsize=None)
    def worlds(self, signature):
        if not conditional_capabilities(self.design):
            return evidence_support(self.design, [{'delivered': {'feedback': {
                'kind': 'station_information', 'station': s, 'capability': k}}} for s, k in signature])
        return evidence_support(self.design, [{"delivered": {"feedback": {
            "kind": "station_information", "station": s, "capability": k,
            **({'requirement': r} if r else {})}}} for s, r, k in signature])

    def support(self, events):
        return self.worlds(self.signature(events))

    def matches(self, worlds, kind, requirement=None):
        return matching_stations(self.design, worlds, kind, requirement)

    def capabilities(self, worlds, station, requirement=None):
        return capability_options(self.design, worlds, station, requirement)


def _context(stage):
    return experience_context(stage)


def _progress(event):
    before, after = event.get("state_before", {}), event.get("state_after", {})
    return (after.get("stage", 0) > before.get("stage", 0)
            or (after.get("raw", False) and not before.get("raw", False))
            or (after.get("processed", False) and not before.get("processed", False)))


def score_stream(design, events, *, condition, metadata=None):
    """Retain all commissioned stages, including unobserved choices and failures."""
    if condition not in ("retain", "clear"):
        raise ValueError("Unknown memory condition")
    if [e["event_id"] for e in events] != list(range(len(events))):
        raise ValueError("Expected one canonical, ordered, cumulative event stream")
    evidence = Evidence(design)
    assignment = design["private_worlds"][map_world(design)]
    starts = [e for e in events if e["kind"] == "task_started"]
    if len({e["task_id"] for e in starts}) != len(starts):
        raise ValueError("This scorer expects unique task identities within a stream")
    run_index = {e["task_run_id"]: i for i, e in enumerate(starts)}
    events_by_run = defaultdict(list)
    for event in events:
        events_by_run[event["task_run_id"]].append(event)
    info = feedback_events(events)
    metadata = {r["task_id"]: r for r in (metadata or [])}
    branches = station_branches(design)
    departures = {(r["fork"], r["path"][1]): s for s, r in branches.items()}
    previous_signatures, previous_target_kinds, previous_kinds = {}, set(), set()
    context_encounters = defaultdict(int)
    tasks, stages, trips, error_sources, processing_attempts = [], [], [], [], []

    # A source needs actual negative feedback; an unqueried wrong visit is not a
    # delivered corrective experience. Selection and process-only definitions
    # are both retained, without combining their scores.
    for e in info:
        i = run_index[e["task_run_id"]]
        stage_index = e.get("state_before", {}).get("stage", 0)
        kind = task_stages(design["tasks"][e["task_id"]])[stage_index]["required_kind"]
        f = e["delivered"]["feedback"]
        if not supports(f["capability"], kind):
            error_sources.append({"task_id": e["task_id"], "task_index": i,
                "event_id": e["event_id"], "station": f["station"],
                "station_type": evidence.locations[f["station"]].get("station_type", f["station"]),
                "required_kind": kind, "actual_capability": f["capability"],
                **({'requirement': f['requirement']} if 'requirement' in f else {}),
                "operation": e["action"]["type"], "unsupported_process": f.get("result") == "unsupported"})

    for index, start in enumerate(starts):
        task_id, run_id = start["task_id"], start["task_run_id"]
        task = design["tasks"][task_id]
        itinerary = task_stages(task)
        current = events_by_run[run_id]
        actions = [e for e in current if e["kind"] == "action"]
        moves = [e for e in actions if e.get("moved")]
        prior = [e for e in info if e["event_id"] < start["event_id"]]
        prior_worlds = evidence.support(prior)
        visited = {e.get("to", e.get("position")) for e in events if e["event_id"] < start["event_id"]}
        entries = [e for e in moves if e["to"] in evidence.stations
                   and not e.get("state_before", {}).get("processed", False)]
        signature = tuple(stage_signature(s) for s in itinerary)
        exact_repeat_of = previous_signatures.get(signature)
        success = current[-1]["delivered"]["observation"]["success"]
        distance = sum(e["movement_cost"] for e in moves)
        reference = known_world_route(design, task_id, assignment)
        if success and distance < reference["distance"]:
            raise ValueError("Successful trace undercuts the physical route bound")
        meta = metadata.get(task_id, {})
        for key, value in (("distance", distance), ("operations", len(actions)), ("success", success)):
            if key in meta and meta[key] != value:
                raise ValueError("Audited metadata differs from canonical events: " + key)
        record = {"condition": condition, "task_id": task_id, "task_index": index,
            "task_run_id": run_id, "success": success, "distance": distance,
            "moves": len(moves), "operations": len(actions), "llm_calls": meta.get("llm_calls"),
            "exact_repeat_of": exact_repeat_of, "followup": index > 0,
            "relation": "exact_repeat" if exact_repeat_of else "new_combination",
            "physical_min_distance": reference["distance"],
            "physical_efficiency": int(success) * reference["distance"] / max(distance, reference["distance"]),
            "query_count": 0, "pre_task_known_queries": 0,
            "historically_repeated_queries": 0, "within_session_repeated_queries": 0,
            "processing_attempt_count": 0, "successful_processing_count": 0,
            "unsupported_processing_count": 0, "wrong_region_processing_count": 0, "historically_redundant_nonmatching_spur_distance": 0,
            "currently_redundant_nonmatching_spur_distance": 0, "novel_information_nonmatching_spur_distance": 0,
            "new_historical_bits": information_gain(prior_worlds, evidence.support(prior + feedback_events(current)))}
        for e in actions:
            f = e["delivered"]["feedback"]
            if e["action"]["type"] == "process":
                j = e.get("state_before", {}).get("stage", 0)
                station, kind = e["to"], itinerary[j]["required_kind"]
                requirement = itinerary[j].get('requirement')
                capability = capability_for(assignment[station], requirement)
                region_ok = region_matches(design, itinerary[j], station)
                supported = supports(capability, kind) and region_ok
                if region_ok:
                    valid = (f.get('kind') == 'station_information' and f.get('station') == station
                             and f.get('capability') == capability and f.get('requirement') == requirement
                             and f.get('result') == ('processed' if supported else 'unsupported'))
                else:
                    valid = (f.get('kind') == 'wrong_processing_region' and f.get('station') == station
                             and f.get('required_region') == itinerary[j]['required_region']
                             and f.get('station_region') == evidence.locations[station]['region_category']
                             and f.get('requirement') == requirement and f.get('result') == 'wrong_region'
                             and 'capability' not in f)
                if not valid:
                    raise ValueError("Processing outcome differs from the executed action or station capability")
                record["processing_attempt_count"] += 1
                record["successful_processing_count"] += supported
                processing_attempts.append({
                    "condition": condition, "task_id": task_id, "task_index": index,
                    "task_run_id": run_id, "stage_index": j, "event_id": e["event_id"],
                    "station": station, "required_kind": kind,
                    "actual_capability": capability, "result": f["result"],
                    **({'requirement': requirement} if requirement is not None else {}),
                    **({'required_region': itinerary[j]['required_region'], 'region_correct': region_ok,
                        'station_region': evidence.locations[station]['region_category']} if 'required_region' in itinerary[j] else {}),
                    "correct": supported, "task_progressed": _progress(e)})
            if e["action"]["type"] == "inspect":
                before = [x for x in current if x["event_id"] < e["event_id"]]
                record["query_count"] += 1
                record["pre_task_known_queries"] += evidence.capabilities(prior_worlds, f["station"], f.get('requirement')) == {freeze_capability(f["capability"])}
                record["historically_repeated_queries"] += evidence.support(prior + before) == evidence.support(prior + before + [e])
                record["within_session_repeated_queries"] += evidence.support(before) == evidence.support(before + [e])
            record["unsupported_processing_count"] += f.get("result") == "unsupported"
            record['wrong_region_processing_count'] += f.get('result') == 'wrong_region'
        record["processing_accuracy"] = fraction(
            record["successful_processing_count"], record["processing_attempt_count"])

        task_stage_records = []
        for j, stage in enumerate(itinerary):
            kind = stage["required_kind"]
            requirement = stage.get('requirement')
            selected = [e for e in entries if e.get("state_before", {}).get("stage", 0) == j]
            post = [e for e in selected if e["state_before"]["raw"]]
            processing = [e for e in actions if e.get("state_before", {}).get("stage", 0) == j
                          and e["action"]["type"] == "process"]
            first = selected[0] if selected else None
            cutoff = first["event_id"] if first else current[-1]["event_id"] + 1
            fresh = [e for e in current if e["event_id"] < cutoff]
            current_matches = [s for s in evidence.matches(evidence.support(fresh), kind, requirement) if region_matches(design, stage, s)]
            known = [s for s in evidence.matches(prior_worlds, kind, requirement) if region_matches(design, stage, s)]
            direct = [e for e in prior if e['delivered']['feedback'].get('requirement') == requirement
                      and supports(e["delivered"]["feedback"]["capability"], kind)]
            last_direct = max(direct, key=lambda e: e["event_id"]) if direct else None
            source_index = run_index[last_direct["task_run_id"]] if last_direct else None
            intervening = [e for e in prior if source_index is not None
                           and run_index[e["task_run_id"]] > source_index]
            interval_refresh = bool(evidence.matches(evidence.support(intervening), kind, requirement)) if source_index is not None else None
            old_errors = [e for e in error_sources if e["task_index"] < index and e["required_kind"] == kind and e.get('requirement') == requirement]
            def station_type(e):
                return evidence.locations[e["to"]].get("station_type", e["to"])
            def correct(e):
                return (region_matches(design, stage, e['to']) and supports(assignment[e["to"]], kind, requirement)) if e else None
            def detail(e):
                if not e:
                    return None
                return {"event_id": e["event_id"], "station": e["to"], "station_type": station_type(e),
                        "correct": correct(e), "collected_before_choice": e["state_before"]["raw"]}
            def repeat_error(errors):
                types = {e["station_type"] for e in errors}
                return {"has_prior_error_feedback": bool(types),
                        "prior_error_types": sorted(types),
                        "first_choice_repeats_error": first is not None and station_type(first) in types,
                        "any_entry_repeats_error": any(station_type(e) in types for e in selected),
                        "processing_observed": bool(processing),
                        "first_process_repeats_error": bool(processing)
                            and station_type(processing[0]) in types
                            and processing[0]["delivered"]["feedback"].get("result") == "unsupported",
                        "any_process_repeats_error": any(station_type(e) in types
                            and e["delivered"]["feedback"].get("result") == "unsupported" for e in processing)}
            same_type_sources = [e for e in prior if first and e['delivered']['feedback'].get('requirement') == requirement and
                evidence.locations[e["delivered"]["feedback"]["station"]].get("station_type", e["delivered"]["feedback"]["station"]) == station_type(first)]
            context_encounters[_context(stage)] += 1
            r = {"condition": condition, "task_id": task_id, "task_index": index,
                "stage_index": j, **stage, "followup": index > 0,
                'planned_encounter': context_encounters[_context(stage)],
                "exact_repeat_of": exact_repeat_of,
                "new_target_for_previously_required_kind": _context(stage) in previous_kinds and stage_signature(stage) not in previous_target_kinds,
                "same_target_kind_seen_before": stage_signature(stage) in previous_target_kinds,
                "prior_world_count": support_count(prior_worlds), "historical_matching_stations": known,
                "historical_matching_opportunity": bool(known), "direct_matching_evidence": bool(direct),
                "matching_known_only_by_inference": bool(known) and not direct,
                "prior_matching_source_event_ids": [e["event_id"] for e in direct],
                "choice_observed": first is not None, "first_any": detail(first),
                "first_postcollection": detail(post[0]) if post else None,
                "first_process_correct": processing[0]["delivered"]["feedback"].get("result") == "processed" if processing else None,
                "all_entries": [detail(e) for e in selected],
                "current_session_independently_determines_answer": bool(current_matches),
                "historical_unreacquired_first_match": bool(known) and first is not None and correct(first) and not current_matches,
                "last_direct_source_task": last_direct["task_id"] if last_direct else None,
                "last_direct_source_event_id": last_direct["event_id"] if last_direct else None,
                "environment_feedback_gap": index - source_index - 1 if source_index is not None else None,
                "intervening_feedback_independently_refreshes_answer": interval_refresh,
                "unrefreshed_direct_source_opportunity": bool(known) and source_index is not None and not interval_refresh,
                "has_unvisited_known_matching_instance": bool(set(known) - visited),
                "selected_previously_unvisited_station": first is not None and first["to"] not in visited,
                "selected_type_previously_observed": bool(same_type_sources),
                "selected_type_source_event_ids": [e["event_id"] for e in same_type_sources],
                "negative_selection_feedback": repeat_error(old_errors),
                "negative_process_feedback": repeat_error([e for e in old_errors if e["unsupported_process"]])}
            if 'required_region' in stage:
                cross_sources=[e for e in direct if evidence.locations[e['delivered']['feedback']['station']]['region_category']!=stage['required_region']]
                cross_types={evidence.locations[e['delivered']['feedback']['station']]['station_type'] for e in cross_sources}
                chosen=processing[0]['from'] if processing else None
                uses_type=bool(chosen and region_matches(design,stage,chosen) and evidence.locations[chosen]['station_type'] in cross_types)
                r.update(prior_matching_types_from_other_regions=sorted(cross_types),
                    cross_region_matching_opportunity=bool(cross_types),
                    first_process_uses_other_region_matching_type=uses_type,
                    first_process_at_unprocessed_station_of_other_region_known_type=uses_type and not any(
                        e['delivered']['feedback']['station']==chosen and e['delivered']['feedback'].get('requirement')==requirement for e in prior))
            stages.append(r)
            task_stage_records.append(r)

        # Keep the earlier visit-based strict rule as a diagnostic. Primary
        # submission accuracy above counts only explicit process actions.
        wrong_entries = [
            {"stage_index": s["stage_index"], "required_kind": s["required_kind"],
             "actual_capability": assignment[e["station"]], **e}
            for s in task_stage_records for e in s["all_entries"] if not e["correct"]]
        first_wrong = min(wrong_entries, key=lambda e: e["event_id"]) if wrong_entries else None
        all_choices_observed = all(s["choice_observed"] for s in task_stage_records)
        record.update(
            strict_success=bool(success and all_choices_observed and not wrong_entries),
            wrong_station_entry_count=len(wrong_entries),
            first_wrong_station_entry=first_wrong,
            strict_failure_reason=("wrong_station_entry" if wrong_entries else
                                   "task_not_completed" if not success else
                                   "missing_station_choice" if not all_choices_observed else None))

        used_edges = set()
        for i, move in enumerate(moves):
            station = departures.get((move["from"], move["to"]))
            if station is None:
                continue
            end = next((m for m in moves[i + 1:] if m["to"] == move["from"]), None)
            last = end["event_id"] if end else current[-1]["event_id"]
            segment = [e for e in actions if move["event_id"] <= e["event_id"] <= last]
            walked = [e for e in segment if e.get("moved")]
            before = [e for e in current if e["event_id"] < move["event_id"]]
            old, after = evidence.support(prior + before), evidence.support(prior + before + segment)
            current_old, current_after = evidence.support(before), evidence.support(before + segment)
            j = move.get("state_before", {}).get("stage", 0)
            kind = itinerary[j]["required_kind"]
            requirement = itinerary[j].get('requirement')
            prior_caps = evidence.capabilities(prior_worlds, station, requirement)
            current_caps = evidence.capabilities(current_old, station, requirement)
            progressed = any(_progress(e) for e in segment)
            region_ok = region_matches(design, itinerary[j], station)
            closed_nonmatching = end is not None and region_ok and not supports(assignment[station], kind, requirement) and not progressed
            historical = (closed_nonmatching and len(prior_caps) == 1 and kind not in prior_caps and old == after)
            within = (closed_nonmatching and not historical and len(current_caps) == 1
                      and kind not in current_caps and current_old == current_after)
            novel = closed_nonmatching and old != after
            edge_ids = [e["event_id"] for e in walked]
            if historical or within or novel:
                if used_edges.intersection(edge_ids):
                    raise ValueError("Excursion metrics would double-count graph edges")
                used_edges.update(edge_ids)
            cost = sum(e["movement_cost"] for e in walked)
            r = {"condition": condition, "task_id": task_id, "stage_index": j, "station": station,
                 "enter_event_id": move["event_id"], "exit_event_id": end["event_id"] if end else None,
                 "closed": end is not None, "distance": cost, "move_event_ids": edge_ids,
                 "matches_current_requirement": region_ok and supports(assignment[station], kind, requirement), "task_progressed": progressed,
                 **({'requirement': requirement} if requirement is not None else {}),
                 "historical_information_gain_bits": information_gain(old, after),
                 "historically_redundant_nonmatching": historical, "within_session_redundant_nonmatching": within,
                 "novel_information_nonmatching": novel}
            trips.append(r)
            record["historically_redundant_nonmatching_spur_distance"] += cost if historical else 0
            record["currently_redundant_nonmatching_spur_distance"] += cost if within else 0
            record["novel_information_nonmatching_spur_distance"] += cost if novel else 0
        record["other_distance_excess_over_physical_bound"] = (distance - reference["distance"]
            - record["historically_redundant_nonmatching_spur_distance"]) if success else None
        if success and record["other_distance_excess_over_physical_bound"] < -1e-9:
            raise ValueError("Removing supposedly redundant spurs undercuts a valid route bound")
        tasks.append(record)
        previous_signatures.setdefault(signature, task_id)
        previous_target_kinds.update(stage_signature(s) for s in itinerary)
        previous_kinds.update(_context(s) for s in itinerary)
    return {"protocol": VERSION, "condition": condition, "tasks": tasks, "stages": stages,
            "station_trips": trips, "negative_feedback_sources": error_sources,
            "processing_attempts": processing_attempts}


def summarize_stages(stages):
    n = len(stages)
    known = [s for s in stages if s["historical_matching_opportunity"]]
    result = {"requirements": n,
        "first_any_accuracy": fraction(sum(bool(s["first_any"] and s["first_any"]["correct"]) for s in stages), n),
        "first_postcollection_accuracy": fraction(sum(bool(s["first_postcollection"] and s["first_postcollection"]["correct"]) for s in stages), n),
        "first_process_accuracy": fraction(sum(s["first_process_correct"] is True for s in stages), n),
        "missing_first_choices": sum(not s["choice_observed"] for s in stages),
        "historical_opportunity_coverage": fraction(len(known), n),
        "historically_known_first_accuracy": fraction(sum(bool(s["first_any"] and s["first_any"]["correct"]) for s in known), len(known)),
        "historical_unreacquired_first_match": fraction(sum(s["historical_unreacquired_first_match"] for s in known), len(known)),
        "historical_unreacquired_first_match_unconditional": fraction(sum(s["historical_unreacquired_first_match"] for s in stages), n),
        "current_answer_reacquired_before_first_choice": sum(s["current_session_independently_determines_answer"] for s in known),
        "direct_matching_opportunities": sum(s["direct_matching_evidence"] for s in known),
        "inferred_matching_opportunities": sum(s["matching_known_only_by_inference"] for s in known),
        "unvisited_matching_instance_available": sum(s["has_unvisited_known_matching_instance"] for s in stages)}
    all_entries = [e for s in stages for e in s["all_entries"]]
    result["all_station_entry_accuracy"] = fraction(sum(e["correct"] for e in all_entries), len(all_entries))
    transfer = [s for s in stages if s["choice_observed"] and s["selected_previously_unvisited_station"]
                and s["selected_type_previously_observed"]]
    result["observed_new_instance_of_known_type_accuracy"] = fraction(
        sum(s["first_any"]["correct"] for s in transfer), len(transfer))
    result["observed_new_instance_scope"] = "Selected instances only; choice-conditioned diagnostic, not a controlled transfer score."
    for key in ("negative_selection_feedback", "negative_process_feedback"):
        eligible = [s for s in stages if s[key]["has_prior_error_feedback"]]
        reached = [s for s in eligible if s["choice_observed"]]
        processed = [s for s in eligible if s[key]["processing_observed"]]
        first_repeats = sum(s[key]["first_choice_repeats_error"] for s in eligible)
        any_repeats = sum(s[key]["any_entry_repeats_error"] for s in eligible)
        result[key] = {"opportunities": len(eligible), "reached": len(reached),
            "missing_choices": len(eligible) - len(reached),
            "first_repeat_error_rate": fraction(first_repeats, len(reached)),
            "any_repeat_error_rate": fraction(any_repeats, len(reached)),
            "process_observed_opportunities": len(processed),
            "first_process_repeat_error_rate": fraction(sum(s[key]["first_process_repeats_error"] for s in eligible), len(processed)),
            "any_process_repeat_error_rate": fraction(sum(s[key]["any_process_repeats_error"] for s in eligible), len(processed)),
            "first_repeat_errors_per_all_requirements": fraction(first_repeats, n),
            "correct_first_after_negative_feedback": fraction(
                sum(bool(s["first_any"] and s["first_any"]["correct"]) for s in eligible), len(eligible))}
    gap_groups = defaultdict(list)
    for s in stages:
        if s["unrefreshed_direct_source_opportunity"]:
            gap_groups[s["environment_feedback_gap"]].append(s)
    result["environment_unrefreshed_gap_curve"] = [
        {"gap": gap, "opportunities": len(items),
         "first_accuracy": fraction(sum(bool(s["first_any"] and s["first_any"]["correct"]) for s in items), len(items)),
         "historical_unreacquired_first_match": fraction(sum(s["historical_unreacquired_first_match"] for s in items), len(items)),
         "current_answer_reacquired": sum(s["current_session_independently_determines_answer"] for s in items)}
        for gap, items in sorted(gap_groups.items())]
    result["gap_curve_exclusions"] = {"without_historical_match": n - len(known),
        "inferred_without_direct_matching_source": sum(s["matching_known_only_by_inference"] for s in known),
        "independently_refreshed_in_intervening_sessions": sum(s["intervening_feedback_independently_refreshes_answer"] is True for s in known)}
    return result


def summarize_stream(scored):
    result = {}
    for name, chosen in (("all_tasks", scored["tasks"]),
                         ("followup", [t for t in scored["tasks"] if t["followup"]]),
                         ("exact_repeats", [t for t in scored["tasks"] if t["exact_repeat_of"]]),
                         ("new_combinations_followup", [t for t in scored["tasks"] if t["followup"] and not t["exact_repeat_of"]])):
        ids = {t["task_id"] for t in chosen}
        stages = [s for s in scored["stages"] if s["task_id"] in ids]
        result[name] = {"tasks": len(chosen), "successes": sum(t["success"] for t in chosen),
            "completion_rate": fraction(sum(t["success"] for t in chosen), len(chosen)),
            "processing_accuracy": fraction(sum(t["successful_processing_count"] for t in chosen),
                                            sum(t["processing_attempt_count"] for t in chosen)),
            "tasks_without_processing_attempts": sum(t["processing_attempt_count"] == 0 for t in chosen),
            "strict_successes": sum(t["strict_success"] for t in chosen),
            "strict_success_rate": fraction(sum(t["strict_success"] for t in chosen), len(chosen)),
            "strict_success_task_ids": [t["task_id"] for t in chosen if t["strict_success"]],
            "strict_failure_task_ids": [t["task_id"] for t in chosen if not t["strict_success"]],
            "task_ids": [t["task_id"] for t in chosen],
            "mean_physical_efficiency": mean(t["physical_efficiency"] for t in chosen) if chosen else None,
            "totals": {k: (sum(t[k] for t in chosen) if all(t[k] is not None for t in chosen) else None) for k in (
                "distance", "operations", "query_count", "pre_task_known_queries", "historically_repeated_queries", "within_session_repeated_queries",
                "processing_attempt_count", "successful_processing_count",
                "unsupported_processing_count", "wrong_region_processing_count", "historically_redundant_nonmatching_spur_distance",
                "currently_redundant_nonmatching_spur_distance", "novel_information_nonmatching_spur_distance",
                "physical_min_distance", "new_historical_bits")},
            "stages": summarize_stages(stages)}
    result["target_kind_relations_followup"] = {
        label: summarize_stages([s for s in scored["stages"] if s["followup"] and s[key]])
        for label, key in (("new_target_for_known_requirement", "new_target_for_previously_required_kind"),
                           ("same_target_and_kind", "same_target_kind_seen_before"))}
    result["by_required_kind_followup"] = {k: summarize_stages(
        [s for s in scored["stages"] if s["followup"] and s["required_kind"] == k])
        for k in sorted({s["required_kind"] for s in scored["stages"]})}
    pairs = {}
    for source in scored["negative_feedback_sources"]:
        key = (source["station_type"], source["required_kind"], source.get('requirement'))
        pairs.setdefault(key, source)
    result["negative_source_pair_coverage"] = [
        {**source, "later_requirement_count": sum(s["task_index"] > source["task_index"]
            and s["required_kind"] == source["required_kind"] and s.get('requirement') == source.get('requirement') for s in scored["stages"])}
        for source in pairs.values()]
    if any('requirement' in s for s in scored['stages']):
        result['by_material_requirement'] = {f'{k}/{r}':summarize_stages(
            [s for s in scored['stages'] if s['required_kind']==k and s.get('requirement')==r])
            for k,r in sorted({(s['required_kind'],s['requirement']) for s in scored['stages']})}
    result['first_planned_encounters'] = summarize_stages([s for s in scored['stages'] if s['planned_encounter']==1])
    result['after_first_planned_encounters'] = summarize_stages([s for s in scored['stages'] if s['planned_encounter']>1])
    result['by_planned_encounter'] = {str(i):summarize_stages([s for s in scored['stages'] if s['planned_encounter']==i])
                                     for i in sorted({s['planned_encounter'] for s in scored['stages']})}
    if any('required_region' in s for s in scored['stages']):
        result['by_required_region'] = {zone:summarize_stages([s for s in scored['stages'] if s['required_region']==zone])
                                        for zone in sorted({s['required_region'] for s in scored['stages']})}
        result['encounter_key'] = ['required_kind','requirement']
        result['region_is_destination_constraint_not_encounter_identity'] = True
    return result


def compare_streams(retain, clear):
    a, b = ({t["task_id"]: t for t in s["tasks"]} for s in (retain, clear))
    if list(a) != list(b):
        raise ValueError("Task identity/order mismatch")
    rows = []
    for task_id in a:
        x, y = a[task_id], b[task_id]
        if x["physical_min_distance"] != y["physical_min_distance"]:
            raise ValueError("Physical references differ")
        rows.append({"task_id": task_id, "followup": x["followup"],
            "retain_success": x["success"], "clear_success": y["success"],
            "retain_processing_attempts": x["processing_attempt_count"],
            "clear_processing_attempts": y["processing_attempt_count"],
            "retain_processing_successes": x["successful_processing_count"],
            "clear_processing_successes": y["successful_processing_count"],
            "retain_strict_success": x["strict_success"], "clear_strict_success": y["strict_success"],
            "signed_strict_success_lift": int(x["strict_success"]) - int(y["strict_success"]),
            "retain_distance": x["distance"], "clear_distance": y["distance"],
            "signed_distance_saved": y["distance"] - x["distance"],
            "signed_distance_saved_per_physical_bound": (y["distance"] - x["distance"]) / x["physical_min_distance"],
            "signed_physical_efficiency_lift": x["physical_efficiency"] - y["physical_efficiency"]})
    cohorts = {}
    for name, chosen in (("all_tasks", rows), ("followup", [r for r in rows if r["followup"]])):
        both = [r for r in chosen if r["retain_success"] and r["clear_success"]]
        clear_cost = sum(r["clear_distance"] for r in both)
        processing = {c: fraction(sum(r[c + "_processing_successes"] for r in chosen),
                                  sum(r[c + "_processing_attempts"] for r in chosen))
                      for c in ("retain", "clear")}
        accuracies = [processing[c]["value"] for c in ("retain", "clear")]
        cohorts[name] = {"tasks": len(chosen), "both_success_tasks": len(both),
            "processing_accuracy": processing,
            "processing_accuracy_lift": accuracies[0] - accuracies[1] if None not in accuracies else None,
            "strict_success_rate_lift": mean(r["signed_strict_success_lift"] for r in chosen) if chosen else None,
            "mean_signed_physical_efficiency_lift": mean(r["signed_physical_efficiency_lift"] for r in chosen) if chosen else None,
            "mean_signed_distance_saved_per_physical_bound": mean(r["signed_distance_saved_per_physical_bound"] for r in chosen) if chosen else None,
            "both_success_distance_reduction": sum(r["signed_distance_saved"] for r in both) / clear_cost if clear_cost else None,
            "shorter": sum(r["signed_distance_saved"] > 0 for r in both),
            "equal_distance": sum(r["signed_distance_saved"] == 0 for r in both),
            "longer": sum(r["signed_distance_saved"] < 0 for r in both),
            "harmed_task_ids": [r["task_id"] for r in chosen if r["signed_physical_efficiency_lift"] < 0]}
    return {"cohorts": cohorts, "per_task": rows,
        "interference_score": None,
        "interference_reason": "No controlled variation of irrelevant history; signed operational contrasts are not an interference score.",
        "confidence_interval": None,
        "uncertainty_reason": "One independent longitudinal run per condition; dependent tasks/stages are not resampled as independent rollouts."}
