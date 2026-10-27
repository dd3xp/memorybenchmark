"""Exhaust all worlds with the same feedback policy, then replay fixed witnesses."""
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
from itertools import permutations, product
import argparse
import json
from pathlib import Path
from statistics import mean, median

from memorybenchmark.prototypes.station_capability import State, StationGame, capability_groups, load_design, task_stages, transition
from memorybenchmark.prototypes.station_routes import shortest_route, task_group
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN, EASY20_LINKED_DESIGN
from scripts.check_station_capability import export_case


class FeedbackSimulation:
    """No hidden capability access in action selection; only transition receives the world."""
    def __init__(self, design):
        self.design = design
        self.route = lru_cache(maxsize=None)(lambda a, b: shortest_route(design, a, b))
        self.groups = capability_groups(design)
        # Public balanced allocation family, not the selected world's assignment.
        self.allocations = {key: sorted({tuple(w[s] for s in g["stations"])
                           for w in design["private_worlds"].values()}) for key, g in self.groups.items()}
        self.candidates = lru_cache(maxsize=None)(self._candidates)

    def _candidates(self, group_id, kind, facts):
        group = self.groups[group_id]; known = dict(facts)
        possible = [a for a in self.allocations[group_id]
                    if all(s not in known or known[s] == k for s, k in zip(group["stations"], a))]
        assert possible
        matching = [s for i, s in enumerate(group["stations"]) if all(a[i] == kind for a in possible)]
        return matching or [s for i, s in enumerate(group["stations"]) if any(a[i] == kind for a in possible)]

    def run(self, world, task_id, history, *, runtime=None):
        task = self.design["tasks"][task_id]; stages = task_stages(task)
        state = State(task["start"]); facts = dict(history)
        actions, distance, decisions = [], 0, []
        if runtime is not None:
            runtime.start_task(task_id)

        def step(action):
            nonlocal state, distance
            after, feedback, cost = transition(self.design, task, world, state, action)
            if runtime is not None:
                actual = runtime.step(action)
                assert actual["feedback"] == feedback and runtime.state == after
            state = after; distance += cost; actions.append(action)
            if feedback["kind"] == "station_information":
                facts[feedback["station"]] = feedback["capability"]

        def walk(target):
            for node in self.route(state.position, target)[0][1:]:
                step({"type": "move", "target": node})

        for index, stage in enumerate(stages):
            walk(stage["target"])
            group_id = task_group(self.design, task_id, index); group = self.groups[group_id]
            destination = stages[index+1]["target"] if index+1 < len(stages) else task["submit_at"]
            tried = []
            while state.stage == index and not state.processed:
                local_facts = tuple(sorted((s, facts[s]) for s in group["stations"] if s in facts))
                candidates = self.candidates(group_id, stage["required_kind"], local_facts)
                station = min(candidates, key=lambda s: (self.route(state.position, s)[1] + self.route(s, destination)[1], s))
                walk(station); step({"type": "process"}); tried.append(station)
            decisions.append({"stage": index+1, "stations": tried})
        walk(task["submit_at"]); step({"type": "submit"})
        assert state.success and len(actions) <= task["max_steps"], (world, task_id, len(actions))
        return {"distance": distance, "operations": len(actions),
                "moves": sum(a["type"] == "move" for a in actions),
                "station_attempts": sum(len(d["stations"]) for d in decisions),
                "decisions": decisions}, facts


def calibrate(design, name):
    sim = FeedbackSimulation(design); per_task = defaultdict(list); worlds = []
    max_steps = 0
    for index, world in enumerate(design["private_worlds"]):
        facts = {}; pairs = []
        for task in design["tasks"]:
            retain, facts = sim.run(world, task, facts)
            clear, _ = sim.run(world, task, {})
            pair = {"task": task, "retain": retain, "clear": clear}
            max_steps = max(max_steps, retain["operations"], clear["operations"])
            pairs.append(pair); per_task[task].append(pair)
        followup = pairs[2:]  # Explicitly report T3-T20, also keep all-task totals.
        row = {"world": world}
        for label, selected in [("all", pairs), ("T3_T20", followup)]:
            row[label] = {mode: {field: sum(p[mode][field] for p in selected)
                                 for field in ("distance", "operations", "moves", "station_attempts")}
                          for mode in ("retain", "clear")}
            row[label]["tasks_with_lower_retained_operations"] = sum(p["retain"]["operations"] < p["clear"]["operations"] for p in selected)
            row[label]["tasks_with_equal_operations"] = sum(p["retain"]["operations"] == p["clear"]["operations"] for p in selected)
            row[label]["tasks_with_higher_retained_operations"] = sum(p["retain"]["operations"] > p["clear"]["operations"] for p in selected)
        worlds.append(row)
        if (index+1) % 324 == 0:
            print(json.dumps({"map": name, "worlds_checked": index+1}), flush=True)
    summary = {}
    for label in ("all", "T3_T20"):
        summary[label] = {mode: {field: mean(w[label][mode][field] for w in worlds)
                        for field in ("distance", "operations", "moves", "station_attempts")}
                        for mode in ("retain", "clear")}
        summary[label].update({field: mean(w[label][field] for w in worlds)
                   for field in ("tasks_with_lower_retained_operations", "tasks_with_equal_operations", "tasks_with_higher_retained_operations")})
        summary[label]["mean_operations_reduction_fraction"] = 1 - summary[label]["retain"]["operations"] / summary[label]["clear"]["operations"]
        summary[label]["world_operations_reduction_fraction_min_median_max"] = [
            fn(1 - w[label]["retain"]["operations"] / w[label]["clear"]["operations"] for w in worlds)
            for fn in (min, median, max)]
    return {"design_id": design["design_id"], "worlds": len(worlds), "completed_replays": len(worlds)*len(design["tasks"])*2,
            "max_policy_operations": max_steps, "summary": summary,
            "task_means": [{"task": task, **{mode: {field: mean(p[mode][field] for p in pairs)
                           for field in ("distance", "operations", "moves", "station_attempts")} for mode in ("retain", "clear")}}
                           for task, pairs in per_task.items()], "per_world": worlds}


def witnesses(design, output):
    cases = []; sim = FeedbackSimulation(design)
    # Fixed family endpoints and T3: include a zero-gain control, no best-world search.
    for world in ("omega_0000", "omega_5555"):
        history = {}; game = StationGame(world, design)
        for task in ("T1", "T2"):
            _, history = sim.run(world, task, history, runtime=game)
        from copy import deepcopy
        for label, facts in (("retain", history), ("clear", {})):
            replay = deepcopy(game); expected, _ = sim.run(world, "T3", facts, runtime=replay)
            row = export_case(output, f"{world}-T3-{label}", replay)
            assert (row["distance"], replay.steps) == (expected["distance"], expected["operations"])
            row.update(world=world, condition=label, measurements=expected)
            cases.append(row)
    return cases


def candidate_order_budget(design):
    """Enumerate all local worlds/orders geometrically; replay each task's worst case."""
    sim = FeedbackSimulation(design); groups = list(sim.groups)
    permutations_by_group = {key: list(permutations(g["stations"])) for key,g in sim.groups.items()}
    checked = 0; worst_cases = []
    for task_id, task in design["tasks"].items():
        group_ids = [task_group(design,task_id,i) for i in range(2)]
        best = None
        for allocation_indices in product(range(6), repeat=2):
            digits = ['0']*4
            for group,index in zip(group_ids, allocation_indices):digits[groups.index(group)] = str(index)
            world = 'omega_'+''.join(digits)
            assignment = design['private_worlds'][world]
            for orders in product(*(permutations_by_group[key] for key in group_ids)):
                position = task['start']; operations = 1; distance = 0
                for stage, order in zip(task['stages'],orders):
                    leg, cost = sim.route(position,stage['target']);operations += len(leg)-1;distance += cost;position=stage['target']
                    for station in order:
                        leg,cost=sim.route(position,station);operations += len(leg)-1;distance += cost;position=station
                        operations += 1  # inspect, with process additionally on a match
                        if assignment[station] == stage['required_kind']:
                            operations += 1;break
                leg,cost=sim.route(position,task['submit_at']);operations += len(leg)-1;distance += cost
                checked += 1
                if best is None or (operations,distance) > (best['operations'],best['distance']):
                    best={'task':task_id,'world':world,'operations':operations,'distance':distance,'orders':orders}
        assert best['operations'] <= task['max_steps'], best
        # Inspect then process each match using the real engine, not the compact cost counter.
        game=StationGame(best['world'],design);game.start_task(task_id)
        from memorybenchmark.prototypes.station_routes import walk
        for stage,order in zip(task['stages'],best['orders']):
            walk(game,stage['target'])
            for station in order:
                walk(game,station);feedback=game.step({'type':'inspect'})['feedback']
                if feedback['capability']==stage['required_kind']:
                    game.step({'type':'process'});break
        walk(game,task['submit_at']);game.step({'type':'submit'})
        assert game.state.success and (game.steps,game.distance)==(best['operations'],best['distance'])
        worst_cases.append(best)
    return {'all_local_world_and_order_pairs_checked':checked,'real_worst_case_replays':len(worst_cases),
            'max_operations':max(r['operations'] for r in worst_cases),'cases':worst_cases,
            'scope':'Every two-group allocation and pair of 24 candidate orders; inspect at each visited station, process on match. Other groups cannot change route/capability. Free arbitrary wandering is not bounded.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    new = load_design(EASY20_LINKED_DESIGN); old = load_design(EASY20_CHOICE_DESIGN)
    report = {"kind": "exhaustive_world_fixed_feedback_policy_calibration_not_native_agent_or_optimal_memory_value",
              "policy": "Same public-geography greedy policy, uniform public balanced allocations, prefer known matches otherwise exclude known nonmatches. Only prior delivered feedback differs; no forced inspection.",
              "scope": "All 1296 worlds per map; all 20 tasks. T3-T20 also reported explicitly; first two are ordinary scored tasks, not training sessions.",
              "new_design_sha256": sha256(EASY20_LINKED_DESIGN.read_bytes()).hexdigest(),
              "old_design_sha256": sha256(EASY20_CHOICE_DESIGN.read_bytes()).hexdigest(),
              "calibrator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "baseline": calibrate(old, "choice-v2"), "linked": calibrate(new, "linked-v3"),
              "witnesses": witnesses(new, args.output), "candidate_order_budget": candidate_order_budget(new),
              "limitations": ["scripted information ablation, no native agent or learned memory",
                              "one fixed feedback policy, not optimal value of information",
                              "new map has two stages and longer branches; aggregate change includes both",
                              "per-world and per-task results include zeros and adverse differences"]}
    (args.output/"design_snapshot.json").write_text(json.dumps(new, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (args.output/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: report[key]["summary"] for key in ("baseline", "linked")}))


if __name__ == "__main__":
    main()
