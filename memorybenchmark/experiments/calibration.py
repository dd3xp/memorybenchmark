"""Descriptive calibration endpoints from the original driver's audited rows."""

from collections import Counter


def fraction(correct, denominator):
    return {
        "correct": correct,
        "denominator": denominator,
        "rate": correct / denominator if denominator else None,
    }


def summarize(result):
    if result.get("status") != "completed_and_audited" or len(
        result.get("rows", [])
    ) != result.get("tasks"):
        raise ValueError("Calibration needs all original audited task rows")
    encounter = Counter()
    first_correct = repeat_correct = repeat_count = 0
    stages_correct = stage_count = combined_correct = combined_count = known_correct = (
        known_count
    ) = 0
    by_encounter = {}
    missing_premises = 0
    for task in result["rows"]:
        operations = task["processing_operations"]
        if len(operations) != task["necessary_operation_denominator"]:
            raise ValueError("A required unattempted operation was omitted")
        for operation in operations:
            key = (
                operation["material"],
                operation["operation"],
                operation["scope_format"],
                operation["goal"] if operation["operation"] == "verify" else "",
            )
            encounter[key] += 1
            n = encounter[key]
            value = operation["first_processing_correct"]
            if type(value) is not bool:
                raise ValueError(
                    "First correctness must include false for unattempted operations"
                )
            row = by_encounter.setdefault(str(n), {"correct": 0, "denominator": 0})
            row["correct"] += value
            row["denominator"] += 1
            first_correct += value
            if n > 1:
                repeat_count += 1
                repeat_correct += value
        for stage in task["stage_outcomes"]:
            value = stage["whole_stage_first_correct"]
            stages_correct += value
            stage_count += 1
            if not stage["combined"]:
                continue
            combined_count += 1
            combined_correct += value
            relevant = [
                o for o in operations if o["stage_index"] == stage["stage_index"]
            ]
            if len(relevant) != 2:
                raise ValueError("A combined stage needs both required operations")
            if all(o["prior_matching_feedback"] for o in relevant):
                known_count += 1
                known_correct += value
            else:
                missing_premises += 1
    denominator = sum(row["denominator"] for row in by_encounter.values())
    return {
        "condition": result["condition"],
        "tasks": fraction(result["successes"], result["tasks"]),
        "all_first_goal_compatible_operations": fraction(first_correct, denominator),
        "after_first_planned_goal_encounter": fraction(repeat_correct, repeat_count),
        "goal_classes": len(encounter),
        "by_encounter": by_encounter,
        "all_stages_first_correct": fraction(stages_correct, stage_count),
        "combined_stages_first_correct": fraction(combined_correct, combined_count),
        "combined_with_both_prior_actual_facts": fraction(known_correct, known_count),
        "combinations_without_both_prior_actual_facts": missing_premises,
        "distance": result["totals"]["distance"],
        "model_calls": result["totals"]["llm_calls"],
        "processing_failures": result["totals"]["unsupported_processing_count"],
        "reported_usage": result.get("model_usage"),
        "infrastructure_costs": result.get("transport_costs"),
        "reasoning_is_output_subset": True,
        "unreported_usage_remains_unknown": True,
        "prior_fact_opportunity_does_not_prove_memory_delivery_or_internal_use": True,
        "single_run_descriptive_only": True,
    }


def choose_followup(retain_metrics):
    """Predeclared screening decision; never select a world by its agent score."""
    if (
        retain_metrics["condition"] != "retain"
        or retain_metrics["tasks"]["denominator"] != 12
    ):
        raise ValueError(
            "Only the completed twelve-task retained pilot screens a design"
        )
    known = retain_metrics["combined_with_both_prior_actual_facts"]
    if known["denominator"] < 6:
        return {
            "variant": "binding",
            "reason": "too_few_previously_observed_combinations; current design not established as a memory test",
        }
    if known["rate"] >= 0.95:
        return {
            "variant": "binding",
            "reason": "observed-known combinations still saturated",
        }
    return {
        "variant": "interface-confirmation",
        "reason": "independent confirmation of the observed gap; do not claim it from one pilot",
    }
