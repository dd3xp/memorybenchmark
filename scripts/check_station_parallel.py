"""Run two complete real-native sessions concurrently with scripted responses.

No provider calls: this checks process overlap, memory separation, feedback and
single-action boundaries. It is software validation, never an agent score.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import threading

from memorybenchmark.ga_runtime import WSLJail
from memorybenchmark.prototypes.station_capability import StationGame, task_stages
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_routes import shortest_route
from scripts.check_ga_single_action import check_boundaries
from scripts.check_station_native_sessions import ScriptedResponses, response_observations


def run(args):
    reference = args.reference_run.resolve()
    pilot = json.loads((reference / "pilot.json").read_text(encoding="utf-8"))
    design = json.loads((reference / "design.json").read_text(encoding="utf-8"))
    agent = pilot["agent"]
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    task_id = pilot["tasks"][0]
    task = design["tasks"][task_id]
    itinerary = [("game_action", {"action": "read"})]
    position = task["start"]
    assignment = design["private_worlds"][pilot["world"]]
    for stage in task_stages(task):
        station = min((s for s, kind in assignment.items() if kind == stage["required_kind"]),
                      key=lambda s: shortest_route(design, stage["target"], s)[1])
        for destination in (stage["target"], station):
            for node in shortest_route(design, position, destination)[0][1:]:
                itinerary.append(("game_action", {"action": "move", "target": node}))
            position = destination
        itinerary.append(("game_action", {"action": "process"}))
    itinerary.extend(("game_action", {"action": "move", "target": node})
                     for node in shortest_route(design, position, task["submit_at"])[0][1:])
    itinerary.append(("game_action", {"action": "submit"}))
    sessions = StationNativeSessions(reference / "source" / ("GenericAgent" if agent == "ga" else "hermes-agent"),
        reference / "support", WSLJail(args.distro, args.runtime, args.runtime_dependency),
        agent=agent, game_access="native", action_policy="single", movement_mode="step", feedback_mode="compact",
        model_alias="fixture", seed=pilot["seed"], max_turns=100, final_turns=3, wall_seconds=600)
    barrier = threading.Barrier(2)
    markers = {c: "synthetic_parallel_contract_" + c + "_93651" for c in ("retain", "clear")}
    def branch(condition):
        marker = markers[condition]
        write = (("code_run", {"type": "python", "script":
                  "from pathlib import Path; Path('../memory/parallel-fixture.txt').write_text(" + repr(marker) + "); print('saved')"})
                 if agent == "ga" else ("memory", {"target": "memory", "operations": [{"action": "add", "content": marker}]}))
        scripted = ScriptedResponses([write, *itinerary], agent, "native")
        def model(payload):
            if not scripted.calls:
                barrier.wait(timeout=180)  # Both real workers reached their first model request.
            return scripted(payload)
        folder = root / condition
        result = sessions.run(StationGame(pilot["world"], design), task_id, reference / "baseline", folder, model, condition=condition)
        assert result["infrastructure_ok"], result.get("infrastructure_error")
        assert result["success"] and result["action_policy_rejections"] == 0
        initial = result["initial_session"]
        assert initial["initial_history_size"] == initial["initial_backend_history_size"] == 0
        assert initial["working"] == {}
        other = markers["clear" if condition == "retain" else "retain"]
        assert other not in json.dumps(scripted.requests, ensure_ascii=False)
        bodies = [p.read_text(encoding="utf-8", errors="replace") for p in (folder / "memory-after").rglob("*.md")]
        bodies += [p.read_text(encoding="utf-8", errors="replace") for p in (folder / "memory-after").glob("*.txt")]
        assert any(marker in body for body in bodies)
        assert all(other not in body for body in bodies)
        # Native code_run may truncate a repeated full-map read. Check the
        # authoritative delivery and the compact action feedback independently.
        data = (folder / "game-deliveries.jsonl").read_bytes()
        assert sha256(data).hexdigest() == result["game_deliveries_sha256"]
        entries = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        assert entries[0]["response"]["observation"]["environment"] == design["public"]
        outputs = [r for r in response_observations(scripted.requests) if r["feedback"]["kind"] != "current_observation"]
        assert outputs and all("environment" not in r["observation"] for r in outputs)
        assert any(r["observation"]["success"] for r in outputs)
        return {"condition": condition, "game_operations": result["game_actions"], "distance": result["distance"],
                "session_id": result["session_id"], "boundary": check_boundaries(folder)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(branch, ("retain", "clear")))
    assert rows[0]["session_id"] != rows[1]["session_id"]
    read = lambda p: json.loads(p.read_text(encoding="utf-8"))
    assert read(root / "retain/memory-before.json") == read(root / "clear/memory-before.json")
    assert read(root / "retain/initial-public.json") == read(root / "clear/initial-public.json")
    validation = {"passed": True, "kind": "real_native_parallel_scripted_contract", "agent": agent,
                  "real_model_calls": 0, "live_worker_overlap_verified": True, "isolated_memory_writes_verified": True, "rows": rows}
    (root / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    print(json.dumps(validation))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--runtime-dependency", action="append", default=[])
    run(parser.parse_args())
