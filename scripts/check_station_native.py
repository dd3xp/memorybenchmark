"""Real GA + jail + station MCP; synthetic model fixture, NOT an agent score."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from memorybenchmark.ga_runtime import WSLJail, copy_memory, extract_native, make_support
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import STATION_TOOL, StationNativeSessions
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN


class FixtureModel:
    def __init__(self, task, condition):
        exists = condition == "retain"
        script = ("from pathlib import Path\nassert not Path('/mnt/c').exists()\n"
                  "assert not Path('ephemeral_station.txt').exists()\n")
        if task == "T1":
            script += "Path('../memory/station_contract_marker.txt').write_text('synthetic marker')\nPath('ephemeral_station.txt').write_text('discard')"
        else:
            script += f"assert Path('../memory/station_contract_marker.txt').exists() is {exists}"
        route = ["J", "P" if task == "T1" else "Q", "J", "A" if task == "T1" else "B"]
        self.tools = iter([("code_run", {"type": "python", "script": script})] +
            [("game_action", {"action": "move", "target": n}) for n in route] +
            [("game_action", {"action": "process"})] +
            [("game_action", {"action": "move", "target": n}) for n in ("J", "C")] +
            [("game_action", {"action": "submit"})])
        self.calls = 0
        self.task = task

    def __call__(self, payload):
        self.calls += 1
        assert f"当前委托 {self.task}：" in payload["input"][0]["content"][0]["text"]
        schema = next(t for t in payload["tools"] if t.get("name") == "game_action")
        assert schema["parameters"] == STATION_TOOL["parameters"]
        tool = next(self.tools, None)
        if tool:
            name, args = tool
            events = [{"type": "response.output_item.added", "output_index": 0, "item": {
                "type": "function_call", "call_id": f"contract-{self.calls}", "name": name}},
                {"type": "response.function_call_arguments.done", "output_index": 0, "arguments": json.dumps(args)}]
        else:
            events = [{"type": "response.output_text.done", "text": "<summary>Fixture finished.</summary>"}]
        events.append({"type": "response.completed", "response": {"usage": {"input_tokens": 1, "output_tokens": 1}}})
        return {"lines": ["data: " + json.dumps(e) for e in events]}


def check(archive, output, distro):
    output.mkdir(parents=True, exist_ok=False)
    source = extract_native(archive, output / "source")
    copy_memory(source / "memory", output / "baseline")
    sessions = StationNativeSessions(source, make_support(output / "support"), WSLJail(distro),
                                    model_alias="scripted-contract", max_turns=16, final_turns=3)
    sessions.probe(output / "baseline", output / "probe")
    game = StationGame("omega_00", load_design(DEFAULT_DESIGN))
    prefix = sessions.run(game, "T1", output / "baseline", output / "prefix", FixtureModel("T1", "prefix"), condition="prefix")
    assert prefix["infrastructure_ok"] and prefix["success"], prefix
    for condition in ("retain", "clear"):
        memory = output / "prefix" / "memory-after" if condition == "retain" else output / "baseline"
        result = sessions.run(deepcopy(game), "T2", memory, output / condition, FixtureModel("T2", condition), condition=condition)
        assert result["infrastructure_ok"] and result["success"], result
        initial = result["initial_session"]
        assert initial["initial_history_size"] == initial["initial_backend_history_size"] == 0
        assert initial["working"] == {}
        assert initial["isolation"]["evaluator_hidden"] and initial["isolation"]["network_blocked"]
        assert ("station_contract_marker.txt" in result["input_memory"]) == (condition == "retain")
    print(json.dumps({"passed": True, "kind": "synthetic_native_contract_not_model_score", "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--distro", default="Ubuntu-24.04")
    args = parser.parse_args()
    check(args.archive, args.output.resolve(), args.distro)
