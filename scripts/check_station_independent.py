"""Two complete independent native runs using synthetic model responses only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading
from unittest.mock import patch

from memorybenchmark.agent_sessions import REASONING_EFFORTS, observed_reasoning_effort
from memorybenchmark.ga_runtime import WSLJail
from memorybenchmark.prototypes import station_independent as independent
from memorybenchmark.prototypes.station_capability import load_design, map_world, task_stages
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_routes import shortest_route
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN
from scripts.check_station_native_sessions import ScriptedResponses
from scripts.compare_station_experiments import compare
from scripts.report_station_experiment import report


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    design = load_design(EASY20_REUSE_DESIGN)
    assignment = design["private_worlds"][map_world(design)]
    markers = {c: "synthetic_independent_contract_" + c + "_58729" for c in ("retain", "clear")}
    barrier = threading.Barrier(2)
    clear_finished = threading.Event()
    inspected = []
    observed_requests = []

    class ScriptedSessions(StationNativeSessions):
        def run(self, game, task_id, memory, output, model, *, condition):
            itinerary = []
            marker = markers[condition]
            other = markers["clear" if condition == "retain" else "retain"]
            if task_id == "T1":
                itinerary.append(("code_run", {"type": "python", "script":
                    "from pathlib import Path; Path('../memory/independent-fixture.txt').write_text(" + repr(marker) + "); print('saved')"})
                    if args.agent == "ga" else ("memory", {"target": "memory", "operations": [{"action": "add", "content": marker}]}))
            else:
                itinerary.append(("code_run", {"type": "python", "script":
                    "from pathlib import Path; p=Path('../memory/independent-fixture.txt'); print(p.read_text() if p.exists() else 'absent')"})
                    if args.agent == "ga" else ("read_file", {"path": "/agent/memory/memories/MEMORY.md"}))
            task = design["tasks"][task_id]
            position = task["start"]
            for stage in task_stages(task):
                station = min((s for s, kind in assignment.items() if kind == stage["required_kind"]),
                              key=lambda s: shortest_route(design, stage["target"], s)[1])
                for destination in (stage["target"], station):
                    itinerary.extend(("game_action", {"action": "move", "target": node})
                                     for node in shortest_route(design, position, destination)[0][1:])
                    position = destination
                itinerary.append(("game_action", {"action": "process"}))
            itinerary.extend(("game_action", {"action": "move", "target": node})
                             for node in shortest_route(design, position, task["submit_at"])[0][1:])
            itinerary.append(("game_action", {"action": "submit"}))
            scripted = ScriptedResponses(itinerary, args.agent, "native")
            def callback(payload):
                # This is an explicit software contract for a pinned native
                # version, not an interception rule in the experiment runner.
                effort = observed_reasoning_effort(payload)
                main_request = bool(payload.get("tools"))
                observed_requests.append((main_request, effort))
                if main_request:
                    assert effort == args.reasoning_effort, "Pinned upstream configuration was not loaded"
                if scripted.calls == 0:
                    if task_id == "T1":
                        barrier.wait(timeout=180)
                    elif condition == "retain":
                        assert clear_finished.wait(timeout=240), "Clear run was blocked by retained progress"
                return scripted(payload)
            result = super().run(game, task_id, memory, output, callback, condition=condition)
            assert result["infrastructure_ok"] and result["success"], result.get("infrastructure_error")
            assert other not in json.dumps(scripted.requests, ensure_ascii=False)
            if task_id == "T2":
                assert (marker in json.dumps(scripted.requests, ensure_ascii=False)) == (condition == "retain")
            inspected.append({"condition": condition, "task": task_id, "session_id": result["session_id"],
                              "operations": result["game_actions"], "distance": result["distance"]})
            return result

    def branch(condition):
        output = root / condition
        jail = WSLJail(args.distro, args.runtime, args.runtime_dependency)
        try:
            result = independent.experiment(output, jail, None, archive=args.archive,
                agent=args.agent, condition=condition, tasks=["T1", "T2"], model_alias="fixture",
                reasoning_effort=args.reasoning_effort)
            assert len(result["sessions"]) == 2
            return report(output, native_archive=args.archive)
        finally:
            if condition == "clear":
                clear_finished.set()
    with patch.object(independent, "StationNativeSessions", ScriptedSessions), ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(branch, condition) for condition in ("retain", "clear")]
        audits = [future.result() for future in futures]
    assert len({r["session_id"] for r in inspected}) == 4
    assert any(main for main, _ in observed_requests)
    efforts = {}
    for _, effort in observed_requests:
        efforts[effort] = efforts.get(effort, 0) + 1
    validation = {"passed": True, "agent": args.agent, "kind": "independent_real_native_scripted_contract",
        "reasoning_effort": args.reasoning_effort, "native_request_effort_verified": True,
        "native_configuration_entry": "mykey.native_oai_config.reasoning_effort" if args.agent == "ga" else "AIAgent.reasoning_config",
        "native_main_requests_verified": sum(main for main, _ in observed_requests),
        "observed_request_reasoning_efforts": efforts,
        "real_model_calls": 0, "runs": 2, "sessions": 4, "clear_finished_while_retain_t2_waited": True,
        "own_histories_replayed": True, "retain_inherits_own_memory": True, "clear_restores_native_baseline": True,
        "session_ids_distinct": True, "rows": inspected, "audited_tasks": [a["replay"]["canonical_tasks"] for a in audits]}
    comparison = compare(root / "retain", root / "clear")
    assert comparison["both_success_followup_tasks"] == ["T2"]
    validation["offline_comparison_verified"] = True
    (root / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps(validation))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--agent", choices=("ga", "hermes"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default="low")
    run(parser.parse_args())
