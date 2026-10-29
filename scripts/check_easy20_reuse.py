"""Check conditional experience guarantees and feasibility without model calls."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from itertools import permutations, product
import argparse
import gzip
import json
from pathlib import Path
import shutil
from math import prod
from statistics import median

from memorybenchmark.prototypes.station_capability import State, StationGame, load_design, transition
from memorybenchmark.prototypes.station_experience import experience_schedule
from memorybenchmark.prototypes.station_session import EASY20_LINKED_DESIGN, EASY20_REUSE_DESIGN
from memorybenchmark.prototypes.station_routes import shortest_route, task_group, walk
from scripts.check_easy20_linked import FeedbackSimulation, calibrate
from scripts.check_station_capability import export_case


def validate_success_guarantee(design):
    """Check every possible successful station, not one preferred route policy."""
    rows = experience_schedule(design)
    stages = [s for r in rows for s in r["stages"]]
    source_checks = inheritance_checks = 0
    for world, assignment in design["private_worlds"].items():
        for row in rows:
            task = design["tasks"][row["task_id"]]
            for stage in row["stages"]:
                kind = stage["required_kind"]
                candidates = [s for s, k in assignment.items() if k == kind]
                assert len(candidates) == 2
                for station in candidates:
                    _, feedback, _ = transition(design, task, world,
                        State(station, raw=True, stage=stage["stage_index"]), {"type": "process"})
                    assert feedback["result"] == "processed"
                    assert (feedback["station"], feedback["capability"]) == (station, kind)
                    station_type = design["public"]["locations"][station]["station_type"]
                    assert feedback["station_type"] == station_type
                    assert all(assignment[s] == kind for s in design["public"]["station_types"][station_type]["stations"])
                    source_checks += 1
                for source in stage["earlier_same_kind_stages"]:
                    old = design["tasks"][source["task_id"]]["stages"][source["stage_index"]]
                    assert old["required_kind"] == kind
                    for station in candidates:
                        assert assignment[station] == old["required_kind"]
                        inheritance_checks += 1
    return {"worlds_checked": len(design["private_worlds"]),
            "successful_station_feedback_checks": source_checks,
            "source_to_later_stage_checks": inheritance_checks,
            "stages": len(stages), "stages_with_same_kind_predecessor": sum(bool(s["earlier_same_kind_stages"]) for s in stages),
            "first_kind_requirements": sum(not s["earlier_same_kind_stages"] for s in stages),
            "kind_requirement_counts": dict(Counter(s["required_kind"] for s in stages)),
            "target_counts": dict(Counter(s["target"] for s in stages)),
            "condition": "An earlier same-kind stage actually processed successfully. This does not assume whole-task success or saved/retrieved memory.",
            "scope": "Deterministic feedback and stable assignments; structural checks do not simulate native agent learning."}


def typed_order_budget(design):
    """All type visit orders; pick each type's nearer instance using public roads.

    Other capabilities cannot affect the cost before the requested type is found.
    Enumerating compatible requested-type pairs therefore covers every world.
    This is not a bound on arbitrary wandering or redundant same-type visits.
    """
    route = lru_cache(None)(lambda a, b: shortest_route(design, a, b))
    groups = design["public"]["capability_groups"]
    members = design["public"]["station_types"]
    orderings = {key: list(permutations(group["station_types"])) for key, group in groups.items()}
    @lru_cache(None)
    def stops(task_id, index, start, order):
        task = design["tasks"][task_id]; stage = task["stages"][index]
        goal = task["stages"][index+1]["target"] if index == 0 else task["submit_at"]
        position = stage["target"]; path, distance = route(start, position); ops = len(path)-1
        outcomes = {}
        for type_id in order:
            station = min(members[type_id]["stations"], key=lambda s: (route(position,s)[1]+route(s,goal)[1],s))
            path, cost = route(position, station); ops += len(path)-1+1; distance += cost; position=station
            outcomes[type_id] = (ops+1, distance, station)  # inspect each; process once on match
        return outcomes
    cases=[]; checked=0
    for task_id, task in design["tasks"].items():
        keys=[task_group(design,task_id,i) for i in (0,1)]; best=None
        for t1,t2 in product(*(groups[key]["station_types"] for key in keys)):
            compatible = next((w for w,assignment in design["private_worlds"].items()
                if assignment[members[t1]["stations"][0]] == task["stages"][0]["required_kind"]
                and assignment[members[t2]["stations"][0]] == task["stages"][1]["required_kind"]),None)
            if compatible is None: continue
            for order1,order2 in product(orderings[keys[0]],orderings[keys[1]]):
                a=stops(task_id,0,task["start"],order1)[t1]
                b=stops(task_id,1,a[2],order2)[t2]
                home,cost=route(b[2],task["submit_at"])
                value=(a[0]+b[0]+len(home),a[1]+b[1]+cost);checked+=1
                if best is None or value > (best["operations"],best["distance"]):
                    best={"task":task_id,"world":compatible,"operations":value[0],"distance":value[1],"orders":[order1,order2]}
        assert best["operations"] <= task["max_steps"],best
        game=StationGame(best["world"],design);game.start_task(task_id)
        for stage,order in zip(task["stages"],best["orders"]):
            walk(game,stage["target"])
            index=game.state.stage;goal=task["stages"][1]["target"] if index==0 else task["submit_at"]
            for type_id in order:
                station=min(members[type_id]["stations"],key=lambda s:(route(game.state.position,s)[1]+route(s,goal)[1],s))
                walk(game,station);feedback=game.step({"type":"inspect"})["feedback"]
                if feedback["capability"]==stage["required_kind"]:
                    game.step({"type":"process"});break
        walk(game,task["submit_at"]);game.step({"type":"submit"})
        assert game.state.success and (game.steps,game.distance)==(best["operations"],best["distance"])
        cases.append(best)
    return {"type_order_pairs_checked":checked,"real_worst_case_replays":len(cases),
            "max_operations":max(r["operations"] for r in cases),"cases":cases,
            "scope":"Every compatible requested-type pair and both 24-order permutations; choose each type's instance by public route cost, inspect then process on match. Arbitrary wandering is not bounded."}


def witnesses(design, output):
    cases=[];sim=FeedbackSimulation(design)
    for world in ("omega_00_00","omega_23_23"):
        game=StationGame(world,design);history={}
        for index,task in enumerate(design["tasks"],1):
            if task in ("T3","T13"):
                for label,facts in (("retain",history),("clear",{})):
                    replay=deepcopy(game);row,_=sim.run(world,task,facts,runtime=replay)
                    case=export_case(output,f"{world}-{task}-{label}",replay)
                    case.update(world=world,task=task,condition=label,measurements=row);cases.append(case)
            _,history=sim.run(world,task,history,runtime=game)
            if index==13:break
    return cases


def type_count_review(design):
    """How early this scripted policy's feedback determines every pairing."""
    sim=FeedbackSimulation(design);histogram=Counter()
    for world in design["private_worlds"]:
        facts={}
        for index,task in enumerate(design["tasks"],1):
            _,facts=sim.run(world,task,facts)
            sizes=[]
            for key,group in sim.groups.items():
                sizes.append(sum(all(s not in facts or facts[s]==k for s,k in zip(group["stations"],a))
                                 for a in sim.allocations[key]))
            if prod(sizes)==1:
                histogram[index]+=1;break
        else:histogram[0]+=1
    resolved=[index for index,count in histogram.items() if index for _ in range(count)]
    return {"station_types":len(design["public"]["station_types"]),"physical_stations":16,"worlds":len(design["private_worlds"]),
        "first_task_after_which_all_type_mappings_are_determined_histogram":dict(sorted(histogram.items())),
        "min_median_max_task": [min(resolved),median(resolved),max(resolved)],
        "scope":"Same fixed scripted feedback policy, evaluator-compatible worlds. Determined from delivered evidence is not equivalent to saved or used by a native agent.",
        "recommendation":"Keep eight types for Easy mechanism validation; do not claim large-capacity memory or controlled interference. Add separate higher-cardinality conditions if that becomes a research target."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output",type=Path,help="Publish validation and losslessly compressed authoritative witness logs")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    design, legacy = load_design(EASY20_REUSE_DESIGN), load_design(EASY20_LINKED_DESIGN)
    assert (len(design["public"]["locations"]),len(design["public"]["edges"])) == (70,77)
    guarantee = validate_success_guarantee(design)
    calibration = calibrate(design, "reuse-v4")
    budget = typed_order_budget(design)
    cases = witnesses(design, args.output)
    type_review=type_count_review(design)
    report = {"kind": "scripted_design_validation_not_native_memory_results", "llm_calls": 0,
              "design_id": design["design_id"], "design_sha256": sha256(EASY20_REUSE_DESIGN.read_bytes()).hexdigest(),
              "legacy_design_sha256": sha256(EASY20_LINKED_DESIGN.read_bytes()).hexdigest(),
              "same_number_of_locations_and_roads": True,
              "success_guarantee": guarantee, "schedule": experience_schedule(design),
              "feedback_policy_calibration": calibration, "candidate_order_budget": budget,
              "type_count_review":type_review,
              "witnesses": cases,
              "limits": ["No native agent or externally written memories.",
                         "Successful processing guarantees exposure, not saving or causal use.",
                         "Failed tasks retain only actual feedback; no forced catch-up.",
                         "Delays between requirements do not establish unrefreshed retention; negative cost effects do not establish interference."]}
    (args.output / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "design_snapshot.json").write_text(json.dumps(design, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.public_output:
        public=args.public_output;public.mkdir(parents=True,exist_ok=True);(public/"cases").mkdir(exist_ok=True)
        published=deepcopy(report)
        for case in published["witnesses"]:
            raw=args.output/case["log"];case["uncompressed_log_sha256"]=sha256(raw.read_bytes()).hexdigest()
            target=public/(case["log"]+".gz");target.write_bytes(gzip.compress(raw.read_bytes(),mtime=0))
            case["log"]+=".gz";case["log_encoding"]="Lossless gzip of full authoritative events; no fields removed"
            for field in ("graph","svg"):shutil.copy2(args.output/case[field],public/case[field])
        (public/"validation.json").write_text(json.dumps(published,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (public/"type-count-review.json").write_text(json.dumps(type_review,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"design_id": design["design_id"], "guarantee": guarantee,
        "policy_replays": calibration["completed_replays"], "max_policy_operations": calibration["max_policy_operations"],
        "candidate_order_pairs": budget["type_order_pairs_checked"],
        "max_candidate_order_operations": budget["max_operations"], "llm_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
