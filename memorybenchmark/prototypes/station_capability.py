"""A finite information-design experiment, not an agent memory implementation.

The reference planner sees a set of possible worlds, never the actual world ID.
The runtime keeps its evaluator log private from the public observation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, permutations, product
import json
from pathlib import Path


DESIGN_PATH = Path(__file__).resolve().parents[2] / "design" / "station_capability_v1.json"


def capability_groups(design):
    public = design["public"]
    return public.get("capability_groups", {"default": {
        "stations": [n for n, data in public["locations"].items() if data["kind"] == "station"],
        "kinds": list(public["kinds"]),
    }})


def task_stages(task):
    """Public itinerary; legacy commissions have exactly one stage."""
    return task.get("stages", [{"target": task["target"], "required_kind": task["required_kind"]}])


def active_stage(task, state):
    return task_stages(task)[state.stage]


def map_world(design, requested=None):
    """The map owns its actual assignment; candidate worlds remain hypotheses.

    Older prototype maps without a declared fixture use their first canonical
    assignment. Direct StationGame construction still supports offline candidate
    replays; live entry points must all use this selector.
    """
    fixed = design.get("fixed_world", min(design["private_worlds"]))
    if fixed not in design["private_worlds"]:
        raise ValueError("The map's fixed assignment is missing from its candidate family")
    if requested is not None and requested != fixed:
        raise ValueError("This map has a fixed station assignment; use a different map version to change station capabilities")
    return fixed


def load_design(path=None):
    # This developer prototype deliberately lives outside packaged/live scenarios.
    path = Path(path) if path else DESIGN_PATH
    design = json.loads(path.read_text(encoding="utf-8"))
    public = design["public"]
    stations = {n for n, data in public["locations"].items() if data["kind"] == "station"}
    kinds = set(public["kinds"])
    groups = capability_groups(design)
    grouped_stations, grouped_kinds = [], []
    if not groups:
        raise ValueError("Declare at least one independent capability group")
    generator = design.get("world_generator", "independent_pair_swaps")
    balanced = generator == "independent_balanced_allocations"
    typed = generator == "station_type_permutations"
    if generator not in ("independent_pair_swaps", "independent_balanced_allocations", "station_type_permutations"):
        raise ValueError("Unknown private-world generator")
    type_members = public.get("station_types", {})
    if typed:
        declared = [s for t in type_members.values() for s in t["stations"]]
        if set(declared) != stations or len(declared) != len(stations):
            raise ValueError("Station types must partition physical stations")
        for type_id, data in type_members.items():
            if len(data["stations"]) < 2 or any(public["locations"][s].get("station_type") != type_id for s in data["stations"]):
                raise ValueError("Each station must declare its public type consistently")
    allocations = []
    for group in groups.values():
        if typed:
            types = group["station_types"]
            size = len(types)
            if size < 2 or len(set(types)) != size or len(group["kinds"]) != size or len(set(group["kinds"])) != size:
                raise ValueError("Typed groups require a bijection of public types to hidden capabilities")
            members = [s for t in types for s in type_members[t]["stations"]]
            replica_counts = {len(type_members[t]["stations"]) for t in types}
            if set(members) != set(group["stations"]) or len(members) != len(group["stations"]) or len(replica_counts) != 1:
                raise ValueError("Typed group membership or replication is inconsistent")
            count = next(iter(replica_counts))
            if group.get("counts") != {kind: count for kind in group["kinds"]}:
                raise ValueError("Typed groups must declare the physical matching-station counts")
            allocations.append([{s: kind for t, kind in zip(types, ordering) for s in type_members[t]["stations"]}
                                for ordering in permutations(group["kinds"])])
            grouped_stations.extend(group["stations"])
            grouped_kinds.extend(group["kinds"])
            continue
        size = 4 if balanced else 2
        if (len(group["stations"]) != size or len(set(group["stations"])) != size or
                len(group["kinds"]) != 2 or len(set(group["kinds"])) != 2):
            raise ValueError("Each capability group requires distinct stations and two kinds")
        counts = group.get("counts", {kind: 1 for kind in group["kinds"]})
        if counts != {kind: size // 2 for kind in group["kinds"]}:
            raise ValueError("Declare the balanced public count for each capability")
        choices = []
        for first in combinations(group["stations"], size // 2):
            choices.append({station: group["kinds"][0 if station in first else 1]
                            for station in group["stations"]})
        # Preserve the historical binary world IDs and assignments exactly.
        if not balanced:
            choices = [{station: group["kinds"][index ^ bit]
                        for index, station in enumerate(group["stations"])} for bit in (0, 1)]
        allocations.append(choices)
        grouped_stations.extend(group["stations"])
        grouped_kinds.extend(group["kinds"])
    if (set(grouped_stations) != stations or len(grouped_stations) != len(stations) or
            set(grouped_kinds) != kinds or len(grouped_kinds) != len(kinds)):
        raise ValueError("Capability groups must partition the stations and kinds")
    if "private_worlds" not in design:
        design["private_worlds"] = {}
        for indices in product(*(range(len(choices)) for choices in allocations)):
            assignment = {}
            for choices, index in zip(allocations, indices):
                assignment.update(choices[index])
            world_id = "omega_" + ("_".join(f"{i:02d}" for i in indices) if typed else "".join(map(str, indices)))
            design["private_worlds"][world_id] = assignment
    expected = 1
    for choices in allocations:
        expected *= len(choices)
    if len(design["private_worlds"]) != expected:
        raise ValueError("The candidate family must contain every independent balanced assignment")
    assignments = []
    for world in design["private_worlds"].values():
        if set(world) != stations:
            raise ValueError("Each world must assign a capability to every station")
        for group in groups.values():
            counts = group.get("counts", {kind: 1 for kind in group["kinds"]})
            if Counter(world[s] for s in group["stations"]) != counts:
                raise ValueError("Each group must satisfy its public capability counts")
        if typed:
            for data in type_members.values():
                if len({world[s] for s in data["stations"]}) != 1:
                    raise ValueError("Same-type stations must share one capability")
            for group in groups.values():
                if {world[type_members[t]["stations"][0]] for t in group["station_types"]} != set(group["kinds"]):
                    raise ValueError("Each typed group must contain every capability exactly once at type level")
        assignments.append(tuple(sorted(world.items())))
    if len(set(assignments)) != len(assignments):
        raise ValueError("Worlds must have different capability assignments")
    map_world(design)
    seen_edges = set()
    for a, b, distance in public["edges"]:
        edge = tuple(sorted((a, b)))
        if a == b or a not in public["locations"] or b not in public["locations"] or edge in seen_edges:
            raise ValueError("Invalid or duplicate geographic edge")
        if type(distance) is not int or distance <= 0:
            raise ValueError("Road distances must be positive integers")
        seen_edges.add(edge)
    for task in design["tasks"].values():
        if task["required_kind"] not in kinds or type(task["max_steps"]) is not int or task["max_steps"] < 1:
            raise ValueError("Invalid task kind or action budget")
        for key, kind in (("start", "camp"), ("submit_at", "camp"), ("target", "survey")):
            if public["locations"].get(task[key], {}).get("kind") != kind:
                raise ValueError("Task locations have incompatible roles")
        stages = task_stages(task)
        if not isinstance(stages, list) or not stages or stages[0] != {"target": task["target"], "required_kind": task["required_kind"]}:
            raise ValueError("Stage itinerary must start with the declared target and kind")
        for stage in stages:
            if (set(stage) != {"target", "required_kind"} or stage["required_kind"] not in kinds or
                    public["locations"].get(stage["target"], {}).get("kind") != "survey"):
                raise ValueError("Invalid stage target or kind")
    reached = {next(iter(public["locations"]))}
    while True:
        expanded = reached | {n for node in reached for n, _ in neighbors(design, node)}
        if expanded == reached:
            break
        reached = expanded
    if reached != set(public["locations"]):
        raise ValueError("The public geographic graph must be connected")
    return design


@dataclass(frozen=True)
class State:
    position: str
    raw: bool = False
    processed: bool = False
    done: bool = False
    success: bool = False
    stage: int = 0


def neighbors(design, position):
    return [(b if a == position else a, distance)
            for a, b, distance in design["public"]["edges"] if position in (a, b)]


def actions_for(design, task, state):
    """Legal operations depend only on publicly visible state."""
    if state.done:
        return []
    actions = [{"type": "move", "target": n} for n, _ in neighbors(design, state.position)]
    if design["public"]["locations"][state.position]["kind"] == "station":
        actions.append({"type": "inspect"})
        if state.raw:
            actions.append({"type": "process"})
    if state.position == task["submit_at"]:
        actions.append({"type": "submit"})
    actions.append({"type": "abandon"})
    return actions


def transition(design, task, world_id, state, action):
    """One deterministic rule transition, before action-budget termination."""
    if action not in actions_for(design, task, state):
        raise ValueError("Action is not available in this public state")
    verb = action["type"]
    distance = 0
    after = state
    stage = active_stage(task, state)
    if verb == "move":
        target = action["target"]
        distance = dict(neighbors(design, state.position))[target]
        after = replace(state, position=target, raw=state.raw or target == stage["target"])
        feedback = {"kind": "arrived", "location": target, "raw_collected": target == stage["target"]}
    elif verb in ("inspect", "process"):
        capability = design["private_worlds"][world_id][state.position]
        feedback = {"kind": "station_information", "station": state.position, "capability": capability}
        station_type = design["public"]["locations"][state.position].get("station_type")
        if station_type is not None:
            feedback["station_type"] = station_type
        if verb == "process":
            supported = capability == stage["required_kind"]
            after = replace(state, processed=state.processed or supported)
            feedback["result"] = "processed" if supported else "unsupported"
            if supported and state.stage + 1 < len(task_stages(task)):
                after = replace(after, stage=state.stage + 1, raw=False, processed=False)
                feedback.update(stage_completed=state.stage + 1, next_stage=after.stage + 1)
    elif verb == "submit":
        if state.raw and state.processed:
            after = replace(state, done=True, success=True)
            feedback = {"kind": "submitted"}
        else:
            feedback = {"kind": "not_ready"}
    else:
        after = replace(state, done=True)
        feedback = {"kind": "abandoned"}
    return after, feedback, distance


def compatible_worlds(design, events):
    """Worlds compatible with delivered feedback, NOT the agent's knowledge."""
    possible = set(design["private_worlds"])
    for event in events:
        feedback = event.get("delivered", {}).get("feedback", {})
        if feedback.get("kind") == "station_information":
            possible = {w for w in possible if
                        design["private_worlds"][w].get(feedback["station"]) == feedback["capability"]}
    if not possible:
        raise ValueError("Delivered evidence is inconsistent with the candidate world family")
    return tuple(sorted(possible))


class StationGame:
    """Mechanism sandbox. It has no model API, native memory or live UI adapter."""
    def __init__(self, world_id, design=None):
        self.design = deepcopy(design if design is not None else load_design())
        if world_id not in self.design["private_worlds"]:
            raise ValueError("Unknown private world")
        self._world_id = world_id
        self.events = []
        self.state = None
        self.task_id = self.task_run_id = None
        self.steps = self.distance = self.clock = 0
        self._runs = 0

    @property
    def done(self):
        return self.state is not None and self.state.done

    def finish_incomplete(self, reason):
        """Host termination, never a fabricated agent action or commute."""
        if not self.done:
            self.state = replace(self.state, done=True)
            delivered = {"observation": self.observation(),
                         "feedback": {"kind": "runner_terminated", "reason": reason}}
            self._record({"kind": "runner_terminated", "position": self.state.position,
                          "time": self.clock, "delivered": delivered, "evidence_delivered": []})
            return deepcopy(delivered)
        return {"observation": self.observation(), "feedback": {"kind": "current_observation"}}

    @property
    def task(self):
        return self.design["tasks"][self.task_id]

    def observation(self):
        if self.state is None:
            raise ValueError("Start a task first")
        result = {"environment": deepcopy(self.design["public"]),
                "task": {"id": self.task_id, **deepcopy(self.task), **active_stage(self.task, self.state)},
                "location": self.state.position, "raw": self.state.raw, "processed": self.state.processed,
                "steps": self.steps, "distance": self.distance, "time": self.clock,
                "done": self.state.done, "success": self.state.success,
                "available_actions": actions_for(self.design, self.task, self.state)}
        if "stages" in self.task:
            result.update(stage_index=self.state.stage, stage_count=len(task_stages(self.task)),
                          stages_completed=self.state.stage + int(self.state.processed))
        return result

    def _record(self, event):
        event.update(event_id=len(self.events), task_id=self.task_id,
                     task_run_id=self.task_run_id, world_version=self.design["public"]["version"])
        self.events.append(deepcopy(event))

    def start_task(self, task_id):
        if self.state is not None and not self.state.done:
            raise ValueError("Finish or abandon the current task first")
        if task_id not in self.design["tasks"]:
            raise ValueError("Unknown task")
        self.task_id = task_id
        self._runs += 1
        self.task_run_id = f"session-{self._runs}"
        self.state = State(self.task["start"])
        self.steps = self.distance = self.clock = 0
        delivered = {"observation": self.observation(), "feedback": {"kind": "started"}}
        self._record({"kind": "task_started", "position": self.state.position, "time": 0,
                      "delivered": delivered, "evidence_delivered": []})
        return deepcopy(delivered)

    def step(self, action):
        if self.state is None or self.state.done:
            raise ValueError("No active task")
        before, time_before = self.state, self.clock
        after, feedback, cost = transition(self.design, self.task, self._world_id, before, action)
        self.steps += 1
        self.clock += cost if action["type"] == "move" else 1
        self.distance += cost
        if self.steps >= self.task["max_steps"] and not after.done:
            after = replace(after, done=True)
            feedback = {**feedback, "termination": "budget_exhausted"}
        self.state = after
        delivered = {"observation": self.observation(), "feedback": feedback}
        evidence = []
        if feedback["kind"] == "station_information":
            evidence = [{"claim": "station_capability", "station": feedback["station"],
                         "capability": feedback["capability"], "source_event_id": len(self.events)}]
        self._record({"kind": "action", "action": deepcopy(action), "from": before.position,
                      "to": after.position, "moved": action["type"] == "move",
                      "movement_cost": cost, "effort_cost": cost, "time_before": time_before,
                      "time_after": self.clock, "inventory_before": [],
                      "state_before": {"raw": before.raw, "processed": before.processed,
                                       **({"stage": before.stage} if "stages" in self.task else {})},
                      "state_after": {"raw": after.raw, "processed": after.processed,
                                      **({"stage": after.stage} if "stages" in self.task else {})},
                      "delivered": delivered, "evidence_delivered": evidence})
        return deepcopy(delivered)


@dataclass(frozen=True)
class Plan:
    distance: Fraction
    steps: Fraction
    action: dict | None


class ReferencePlanner:
    """Exact finite-horizon policy search under a uniform candidate-world prior.

    Primary objective: expected walked distance, requiring success in every
    remaining world. Expected operation count breaks ties. Uninformative loops
    and all legal inspections are included; action choices cannot see theta.
    """
    def __init__(self, design, task_id):
        self.design, self.task = design, design["tasks"][task_id]
        self.solve = lru_cache(maxsize=None)(self._solve)

    def initial(self, worlds):
        worlds = tuple(sorted(set(worlds)))
        if not worlds or not set(worlds).issubset(self.design["private_worlds"]):
            raise ValueError("Reference information must describe at least one known candidate world")
        return self.solve(State(self.task["start"]), worlds, self.task["max_steps"])

    def _solve(self, state, worlds, remaining):
        if state.done:
            return Plan(Fraction(0), Fraction(0), None) if state.success else None
        if remaining <= 0:
            return None
        best = None
        for action in actions_for(self.design, self.task, state):
            groups = defaultdict(list)
            for world in worlds:
                after, feedback, cost = transition(self.design, self.task, world, state, action)
                groups[(after, json.dumps(feedback, sort_keys=True), cost)].append(world)
            expected_distance, expected_steps = Fraction(0), Fraction(1)
            feasible = True
            for (after, _, cost), posterior in groups.items():
                future = self.solve(after, tuple(posterior), remaining - 1)
                if future is None:
                    feasible = False
                    break
                probability = Fraction(len(posterior), len(worlds))
                expected_distance += probability * (cost + future.distance)
                expected_steps += probability * future.steps
            if feasible and (best is None or (expected_distance, expected_steps) < (best.distance, best.steps)):
                best = Plan(expected_distance, expected_steps, deepcopy(action))
        return best


def replay_policy(game, planner, initial_worlds):
    """Replay one policy using new feedback, never the runtime's private ID."""
    worlds = tuple(sorted(set(initial_worlds)))
    planner.initial(worlds)  # Validate the analysis input before executing anything.
    while not game.state.done:
        choice = planner.solve(game.state, worlds, game.task["max_steps"] - game.steps)
        if choice is None or choice.action is None:
            raise ValueError("No guaranteed-success reference policy in the remaining budget")
        response = game.step(choice.action)
        feedback = response["feedback"]
        if feedback["kind"] == "station_information":
            worlds = tuple(w for w in worlds if
                           game.design["private_worlds"][w][feedback["station"]] == feedback["capability"])
            if not worlds:
                raise ValueError("Observed feedback contradicts the supplied reference information")
    if not game.state.success:
        raise AssertionError("A reference policy failed during runtime replay")
    return worlds
