"""Scripted real-native isolation and memory contract; never an LLM score."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memorybenchmark.agent_adapters import load_adapter, PreparedAgent
from memorybenchmark.ga_runtime import WSLJail
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN

MARKER = "synthetic_native_contract_marker_74931"


class ScriptedResponses:
    def __init__(self, tools, agent="ga"):
        self.tools = iter(tools)
        self.calls = 0
        self.requests = []
        self.agent = agent

    def __call__(self, payload):
        self.requests.append(deepcopy(payload))
        self.calls += 1
        call = next(self.tools, None)
        events = []
        response_id = f"resp_fixture_{self.calls}"
        if call:
            name, arguments = call
            if self.agent == "hermes" and name == "game_action":
                name, arguments = "tool_call", {"calls": [{"name": name, "arguments": arguments}]}
            item = {"type": "function_call", "id": f"fc_fixture_{self.calls}",
                    "call_id": f"call_fixture_{self.calls}", "name": name,
                    "arguments": json.dumps(arguments), "status": "completed"}
            events += [
                {"type": "response.output_item.added", "output_index": 0,
                 "item": {**item, "arguments": "", "status": "in_progress"}},
                {"type": "response.function_call_arguments.done", "item_id": item["id"],
                 "output_index": 0, "arguments": item["arguments"]},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
            ]
        else:
            text = "<summary>Scripted contract complete.</summary> noop"
            item = {"type": "message", "id": f"msg_fixture_{self.calls}", "role": "assistant",
                    "status": "completed", "content": [{"type": "output_text", "text": text, "annotations": []}]}
            events += [{"type": "response.output_text.delta", "output_index": 0, "content_index": 0,
                        "item_id": item["id"], "delta": text},
                       {"type": "response.output_text.done", "output_index": 0, "content_index": 0,
                        "item_id": item["id"], "text": text},
                       {"type": "response.output_item.done", "output_index": 0, "item": item}]
        events.append({"type": "response.completed", "response": {"id": response_id, "object": "response",
            "status": "completed", "model": "fixture", "created_at": 1, "output": [item],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}})
        return {"lines": ["data: " + json.dumps(event) + "\n" for event in events]}


def run(args):
    output = args.output or Path(".runs/station-native-contract") / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    if args.prepared_root:
        # Reuse only the read-only upstream source and untouched native baseline
        # after a failed setup check; live state and all sessions remain fresh.
        previous = args.prepared_root
        prepared = PreparedAgent(previous / "source" / ("GenericAgent" if args.agent == "ga" else "hermes-agent"),
                                 previous / "support", previous / "baseline")
    else:
        prepared = load_adapter(args.agent).prepare(args.archive, output)
    jail = WSLJail(args.distro, args.runtime, args.runtime_dependency)
    sessions = StationNativeSessions(prepared.source, prepared.support, jail, agent=args.agent,
                                    model_alias="fixture", max_turns=10, final_turns=3, seed=1)
    sessions.probe(prepared.baseline, output / "probe")
    game = StationGame("omega_5511", load_design(EASY20_CHOICE_DESIGN))
    if args.agent == "ga":
        write = ("code_run", {"type": "python", "code":
                 f"from pathlib import Path; Path('../memory/fixture.txt').write_text({MARKER!r}); Path('ephemeral.txt').write_text('temporary')"})
        read = ("code_run", {"type": "python", "code":
                "from pathlib import Path; assert not Path('ephemeral.txt').exists(); p=Path('../memory/fixture.txt'); print(p.read_text() if p.exists() else 'absent')"})
    else:
        write = ("memory", {"target": "memory", "operations": [{"action": "add", "content": MARKER}]})
        read = ("read_file", {"path": "/agent/memory/memories/MEMORY.md"})
    prefix_tools = [write]
    if args.agent == "hermes":
        prefix_tools.append(("skill_manage", {"operations": [{"action": "create", "name": "native-fixture-skill",
            "content": "---\nname: native-fixture-skill\ndescription: Synthetic native persistence contract fixture.\n---\n# Fixture\nSynthetic contract data only.\n"}]}))
    first_model = ScriptedResponses(prefix_tools + [("game_action", {"action": "abandon"})], args.agent)
    first = sessions.run(game, "T1", prepared.baseline, output / "prefix", first_model, condition="prefix")
    assert first["infrastructure_ok"], first.get("infrastructure_error")
    assert any(MARKER in path.read_text(encoding="utf-8", errors="replace")
               for path in (output / "prefix/memory-after").rglob("*") if path.is_file())
    if args.agent == "hermes":
        assert list((output / "prefix/memory-after/.curator_backups/blobs").glob("*")), "skill rollback blobs did not persist"
        assert first["initial_session"]["game_tool_registered"]
        assert "memory" in [tool["name"] for tool in first["tools"]], "native tool callback was not decoded"
    for condition in ("retain", "clear"):
        model = ScriptedResponses([read, ("game_action", {"action": "abandon"})], args.agent)
        memory = output / "prefix/memory-after" if condition == "retain" else prepared.baseline
        result = sessions.run(deepcopy(game), "T2", memory, output / condition, model, condition=condition)
        assert result["infrastructure_ok"], result.get("infrastructure_error")
        initial = result["initial_session"]
        assert initial["initial_history_size"] == initial["initial_backend_history_size"] == 0
        assert initial["working"] == {}
        visible = any(MARKER in json.dumps(request, ensure_ascii=False) for request in model.requests)
        assert visible == (condition == "retain"), (condition, visible)
        assert result["worker_result"]["phase_calls"]["main"] == result["main_calls"]
    context_marker = "synthetic_in_session_budget_context_95172"
    context_tool = (("code_run", {"type": "python", "code": f"print({context_marker!r})"})
                    if args.agent == "ga" else ("terminal", {"command": f"printf '{context_marker}'"}))
    model = ScriptedResponses([context_tool] + [("game_action", {"action": "read"})] * 9, args.agent)
    budget = sessions.run(deepcopy(game), "T3", prepared.baseline, output / "budget", model, condition="clear")
    assert budget["infrastructure_ok"], budget.get("infrastructure_error")
    assert budget["main_calls"] == 10 and budget["final_calls"] >= 1
    assert budget["worker_result"]["native_result"]["result"] == "MAX_TURNS_EXCEEDED"
    assert context_marker in json.dumps(model.requests[10], ensure_ascii=False), "final opportunity lost native task context"
    print(json.dumps({"passed": True, "agent": args.agent, "llm_calls": 0,
                      "kind": "scripted_real_native_contract", "output": str(output.resolve())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--agent", choices=("ga", "hermes"), default="ga")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime")
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepared-root", type=Path)
    run(parser.parse_args())
