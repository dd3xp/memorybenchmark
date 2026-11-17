"""Predeclared development screening, counted only at committed task boundaries.

Stopped prefixes are development attempts, never complete benchmark scores.
No model calls, hidden agent hints, game replay or mutable scientific rules.
"""

from hashlib import sha256
import json
from pathlib import Path

from .calibration import processing_accuracy
from .repository import utc
from ..watch import atomic_json


class DevelopmentScreenStop(RuntimeError):
    pass


def decision(metrics, policy):
    repeated = metrics["after_first_planned_goal_encounter"]
    known = metrics["combined_with_both_prior_actual_facts"]
    if repeated["denominator"] < policy["minimum_repeat_operations"]:
        return None
    if metrics["combinations_without_both_prior_actual_facts"]:
        return "missing_required_prior_feedback"
    if known["denominator"] < policy["minimum_known_combined_stages"]:
        return None
    applicable = [
        rule
        for rule in policy["checkpoints"]
        if repeated["denominator"] >= rule["repeat_operations"]
    ]
    if not applicable:
        return None
    rule = applicable[-1]
    if repeated["rate"] < rule["minimum_rate"]:
        return "too_hard"
    if repeated["rate"] > rule["maximum_rate"]:
        return "too_easy"
    return None


def prefix_metrics(design, events, sessions):
    from ..prototypes.station_interfaces import analyze

    starts = {
        e["task_id"]: e["task_run_id"] for e in events if e["kind"] == "task_started"
    }
    rows = []
    for session in sessions:
        row = analyze(design, events, starts[session["task_id"]])
        if row["success"] != session["success"]:
            raise ValueError("Committed task outcome differs from its event snapshot")
        rows.append(row)
    return processing_accuracy(rows)


class HardScreen:
    def __init__(self, job, policy):
        if (
            job["model"] != "gpt-5.6-luna"
            or job["conditions"] != ["retain"]
            or job["condition"] != "retain"
            or job["context_tokens"] != 272000
            or job["movement_mode"] != "step"
            or job["tasks_per_condition"] != 36
            or policy["schema"] != "hard-development-screen-1"
        ):
            raise ValueError("Hard screening needs its explicit full retained contract")
        checkpoints = policy["checkpoints"]
        if (
            policy["minimum_repeat_operations"] < 16
            or policy["minimum_known_combined_stages"] < 6
            or not 0
            < policy["target_minimum_rate"]
            <= policy["target_rate"]
            <= policy["target_maximum_rate"]
            < 1
            or not checkpoints
            or [x["repeat_operations"] for x in checkpoints]
            != sorted({x["repeat_operations"] for x in checkpoints})
            or any(
                not 0 <= x["minimum_rate"] < x["maximum_rate"] <= 1 for x in checkpoints
            )
        ):
            raise ValueError("Invalid predeclared development screening policy")
        self.root = Path(job["root"])
        self.policy = policy
        self.job = job

    def __call__(self, report, game):
        metrics = prefix_metrics(game.design, game.events, report["sessions"])
        completed = len(report["sessions"])
        reason = decision(metrics, self.policy)
        complete = completed == len(report["tasks"])
        # The original driver owns the final strict audit of a full run.
        receipt = {
            "utc": utc(),
            "phase": (
                "full_tasks_pending_original_audit"
                if complete
                else "development_prefix"
            ),
            "completed": completed,
            "planned": len(report["tasks"]),
            "successes": sum(s["success"] is True for s in report["sessions"]),
            "scientific_failures": sum(
                s["success"] is False for s in report["sessions"]
            ),
            "metrics": metrics,
            "decision": reason,
            "target_rate": self.policy["target_rate"],
            "policy_sha256": sha256(
                json.dumps(self.policy, sort_keys=True).encode()
            ).hexdigest(),
            "model_or_game_replay_calls": 0,
            "partial_attempt_is_not_a_complete_result": not complete,
        }
        version = self.root / "development-observations" / f"{completed:02d}.json"
        version.parent.mkdir(parents=True, exist_ok=True)
        if version.exists():
            previous = json.loads(version.read_text(encoding="utf-8"))
            if any(
                previous[k] != receipt[k]
                for k in ("completed", "metrics", "policy_sha256", "decision")
            ):
                raise ValueError("A previously observed development checkpoint changed")
            receipt = previous
        else:
            atomic_json(version, receipt)
        atomic_json(self.root / "development-metrics.json", receipt)
        if reason and not complete:
            atomic_json(self.root / "development-stop.json", receipt)
            raise DevelopmentScreenStop(
                f"Predeclared Hard screen: {reason}; completed={completed}"
            )
