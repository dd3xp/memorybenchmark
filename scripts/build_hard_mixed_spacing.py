"""Reorder the fixed v4 Orcia commissions and verify their feedback prerequisites."""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from memorybenchmark.prototypes.composition_lab import cases, experience_keys, stage
from memorybenchmark.prototypes.station_interfaces import item, world
from scripts.build_hard_calibration import validate


BASE = (
    Path(__file__).resolve().parents[1]
    / "memorybenchmark/data/candidates/orcia_binding36_spaced.json"
)
BASE_SHA256 = "811e325812a9afac32631d980d022a8add08680685846100d128f31ea75487f2"
DESIGN_ID = "hard-binding-calibration-v5-61601-36"

# Original commission numbers. Each material's two goals are taught first.
# Early combinations train no additional operation keys. Their delayed repeats
# retain the original third-encounter lags, including the final three commissions.
TASK_ORDER = (
    1,
    6,
    11,
    16,
    21,
    2,
    7,
    12,
    17,
    22,
    3,
    5,
    10,
    8,
    31,
    13,
    18,
    23,
    4,
    32,
    33,
    9,
    14,
    19,
    24,
    15,
    20,
    26,
    27,
    35,
    36,
    28,
    29,
    25,
    34,
    30,
)

# Ordinary commissions cover the first three complementary material pairs.
# Introduce the first two pairs' combinations before the remaining pairs enter.
# Commissions with a third encounter keep their individual distances.
STAGED_DESIGN_ID = "hard-binding-calibration-v6-61601-36"
STAGED_TASK_ORDER = (
    # Ordinary commissions for the first three pairs.
    1,
    2,
    3,
    6,
    7,
    8,
    11,
    12,
    13,
    16,
    17,
    18,
    # Combinations for the first two pairs.
    21,
    22,
    26,
    27,
    # Remaining introductions and the original third encounters.
    4,
    9,
    14,
    19,
    23,
    5,
    31,
    32,
    33,
    24,
    10,
    15,
    20,
    28,
    29,
    25,
    35,
    36,
    30,
    34,
)

SCHEDULES = {
    "mixed-spacing": (DESIGN_ID, TASK_ORDER),
    "staged-composition": (STAGED_DESIGN_ID, STAGED_TASK_ORDER),
}


def experience_history(design):
    """Require ordinary feedback opportunities for both goals before composing."""
    interfaces = world(design)
    prerequisites = defaultdict(set)
    for material, goal in cases(interfaces):
        combination = stage(interfaces, (material, goal), "combined")
        prerequisites[material].update(experience_keys(combination, interfaces))

    history = defaultdict(list)
    taught = set()
    for position, (task_id, task) in enumerate(design["tasks"].items(), 1):
        ordinary = set()
        for part in map(item, task["stages"]):
            keys = experience_keys(part, interfaces)
            if part.mode == "combined":
                if not prerequisites[part.material] <= taught:
                    raise ValueError(
                        f"{task_id} must follow ordinary encounters for both goals"
                    )
            else:
                ordinary.update(keys)
            for key in keys:
                history[key].append((task_id, position))
        taught.update(ordinary)
    return history


def repeat_gap(sequence, ordinal):
    return sequence[ordinal - 1][1] - sequence[ordinal - 2][1]


def build(schedule="mixed-spacing"):
    design_id, order = SCHEDULES[schedule]
    raw = BASE.read_bytes()
    if sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError("The frozen v4 reference design changed")
    baseline = json.loads(raw)
    task_ids = [f"T{number}" for number in order]
    if len(task_ids) != len(baseline["tasks"]) or set(task_ids) != set(
        baseline["tasks"]
    ):
        raise ValueError("The order must contain each original commission exactly once")
    candidate = deepcopy(baseline)
    candidate["tasks"] = {task_id: candidate["tasks"][task_id] for task_id in task_ids}
    original = experience_history(baseline)
    reordered = experience_history(candidate)
    if reordered.keys() != original.keys():
        raise ValueError("An operation scope changed")

    gaps = {2: Counter(), 3: Counter()}
    for key, sequence in reordered.items():
        previous = original[key]
        if [task for task, _ in sequence] != [task for task, _ in previous]:
            raise ValueError(
                "The permutation changed the encounter order within a scope"
            )
        gaps[2][repeat_gap(sequence, 2)] += 1
        if len(sequence) == 3:
            third = repeat_gap(sequence, 3)
            if third != repeat_gap(previous, 3):
                raise ValueError("A third-encounter gap changed")
            gaps[3][third] += 1

    candidate["design_id"] = candidate["public"]["version"] = design_id
    candidate["evaluation"]["allocation"].update(
        minimum_task_index_gap_between_uses=min(
            min(histogram) for histogram in gaps.values()
        ),
        first_combination_task=next(
            position
            for position, task in enumerate(candidate["tasks"].values(), 1)
            if any(item(part).mode == "combined" for part in task["stages"])
        ),
        repeat_gap_histogram={
            str(ordinal): dict(sorted(histogram.items()))
            for ordinal, histogram in gaps.items()
        },
        third_encounter_gaps_preserved=True,
    )
    candidate["provenance"]["reordered_from_sha256"] = BASE_SHA256
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", choices=SCHEDULES, default="mixed-spacing")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assessment = args.output.with_suffix(".assessment.json")
    if args.output.exists() or assessment.exists():
        raise FileExistsError("Use a new output path for the candidate and assessment")

    candidate = build(args.schedule)
    proof = validate(candidate, feedback_only_repeats=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(candidate, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    args.output.write_bytes(data)
    proof["design_sha256"] = sha256(data).hexdigest()
    proof["allocation"] = candidate["evaluation"]["allocation"]
    assessment.write_bytes((json.dumps(proof, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
