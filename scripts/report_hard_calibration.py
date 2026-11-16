"""Assemble paired calibration results from already verified local receipts."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def condition(folder):
    folder = Path(folder)
    verified = read(folder / "local-verification.json")
    job = read(folder / "job.json")
    metrics = read(folder / "calibration-metrics.json")
    result_bytes = (folder / "result.json").read_bytes()
    result = json.loads(result_bytes)
    identity = (job["pair_id"], job["condition"], job["source_digest"])
    if not verified.get("passed") or identity != (
        verified["pair_id"],
        verified["condition"],
        verified["source_digest"],
    ):
        raise ValueError("A matching passed local receipt is required")
    if (
        job["context_tokens"] != 272000
        or verified["actual_context"] != 272000
        or job["model"] != "gpt-5.6-luna"
        or job["movement_mode"] != "step"
        or job["tasks_per_condition"] != 12
        or metrics["source_result_sha256"] != sha256(result_bytes).hexdigest()
        or metrics["condition"] != job["condition"]
        or metrics["source_digest"] != job["source_digest"]
        or metrics["design_id"] != job["design_id"]
    ):
        raise ValueError("Result, metrics and authorized native job must agree")
    return {
        "pair_id": job["pair_id"],
        "condition": job["condition"],
        "design_id": metrics["design_id"],
        "metrics": {
            key: value
            for key, value in metrics.items()
            if key != "local_archive_verification"
        },
        "local_verification": verified,
        "game_failure_tasks": [
            row["task_id"] for row in result["rows"] if not row["success"]
        ],
    }


def build(folders, normal):
    pairs = {}
    for folder in folders:
        row = condition(folder)
        paired = pairs.setdefault(row["pair_id"], {})
        if row["condition"] in paired:
            raise ValueError("Duplicate condition would duplicate the scientific count")
        paired[row["condition"]] = row
    if len(pairs) != 2 or any(
        set(pair) != {"retain", "clear"} for pair in pairs.values()
    ):
        raise ValueError("Both authorized rounds need retain and clear results")
    for pair in pairs.values():
        retained, cleared = pair["retain"], pair["clear"]
        if (
            retained["design_id"] != cleared["design_id"]
            or retained["metrics"]["source_digest"]
            != cleared["metrics"]["source_digest"]
        ):
            raise ValueError("A pair cannot mix designs or frozen executors")
    if normal["actual_context_tokens_all_sessions"] != 272000:
        raise ValueError("An invalid historical context cannot serve as a reference")
    reference = next(
        row
        for row in normal["rows"]
        if row["map"] == "nessie-normal" and row["condition"] == "retain"
    )
    endpoint = reference["after_first_encounter"]
    normal_rate = endpoint["correct"] / endpoint["denominator"]
    rows = []
    for pair in pairs.values():
        retained = pair["retain"]["metrics"]["after_first_planned_goal_encounter"]
        clear = pair["clear"]["metrics"]["after_first_planned_goal_encounter"]
        rows.append(
            {
                "conditions": pair,
                "retain_minus_clear_repeat_percentage_points": 100
                * (retained["rate"] - clear["rate"]),
                "normal_minus_retained_repeat_percentage_points": 100
                * (normal_rate - retained["rate"]),
            }
        )
    return {
        "schema": "bounded-hard-calibration-paired-report-1",
        "status": "four_conditions_originally_audited_and_locally_verified",
        "planned_tasks": 48,
        "completed_tasks": sum(
            r["metrics"]["tasks"]["denominator"]
            for p in pairs.values()
            for r in p.values()
        ),
        "successful_tasks": sum(
            r["metrics"]["tasks"]["correct"] for p in pairs.values() for r in p.values()
        ),
        "rounds": rows,
        "normal_descriptive_reference": reference,
        "model_calls_for_this_report": 0,
        "archive_reverification_for_this_report": False,
        "reasoning_is_output_subset": True,
        "unknown_usage_is_not_zero": True,
        "interpretation_limits": [
            "Development screening; twelve tasks per condition, one run per design.",
            "Normal uses route movement; the calibration uses step movement and different goal conditions.",
            "Prior actual feedback is an opportunity, not proof of saved memory delivery or internal causal use.",
            "A full36-task held-out candidate has not been model evaluated or authorized for launch.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, action="append", required=True)
    parser.add_argument("--normal-reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve the original report; use a new version")
    report = build(args.folder, read(args.normal_reference))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("status", "completed_tasks", "successful_tasks")
            }
        )
    )


if __name__ == "__main__":
    main()
