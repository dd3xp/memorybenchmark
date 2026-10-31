"""Scripted real-native isolation and memory contract; never an LLM score."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memorybenchmark.agent_adapters import load_adapter, PreparedAgent
from memorybenchmark.ga_runtime import WSLJail, make_support
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN, EASY20_LINKED_DESIGN, EASY20_REUSE_DESIGN, FEEDBACK_PROTOCOLS
from memorybenchmark.prototypes.station_routes import shortest_route

MARKER = "synthetic_native_contract_marker_74931"


def response_observations(value):
    """Find actual game outputs inside each agent's native model messages."""
    if isinstance(value, dict):
        if "observation" in value and "feedback" in value and not isinstance(value.get("responses"), list):
            yield value
        else:
            for nested in value.values():
                yield from response_observations(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from response_observations(nested)
    elif isinstance(value, str):
        # Hermes intentionally labels MCP output as external data. Decode
        # that native envelope for auditing only; never edit model inputs.
        stripped = value.strip()
        if stripped.startswith("<untrusted_tool_result ") and stripped.endswith("</untrusted_tool_result>"):
            parts = stripped.split("\n\n", 1)
            if len(parts) == 2:
                value = parts[1].rsplit("</untrusted_tool_result>", 1)[0].strip()
        try:
            parsed = json.loads(value)
        except ValueError:
            return
        if isinstance(parsed, (dict, list)):
            yield from response_observations(parsed)


def check_feedback_delivery(folder, report, model, mode):
    body = (folder / "game-deliveries.jsonl").read_bytes()
    assert report["feedback_mode"] == mode
    assert report["feedback_protocol"] == FEEDBACK_PROTOCOLS[mode]
    assert report["game_deliveries_sha256"] == sha256(body).hexdigest()
    delivered = [json.loads(line) for line in body.decode("utf-8").splitlines()]
    assert "environment" in delivered[0]["response"]["observation"]
    for entry in delivered[1:]:
        response = entry["response"]
        if "observation" not in response:
            continue
        full = mode == "full" or entry["request"] == {"command": "read"}
        assert ("environment" in response["observation"]) == full
    outputs = list(response_observations(model.requests))
    assert outputs, "No actual game results reached the native model requests"
    actions = [r for r in outputs if r["feedback"]["kind"] != "current_observation"]
    assert actions
    assert all(("environment" in r["observation"]) == (mode == "full") for r in actions)
    assert any(r["feedback"]["kind"] == "current_observation" and "environment" in r["observation"] for r in outputs)


class ScriptedResponses:
    def __init__(self, tools, agent="ga", game_access="bridge"):
        self.tools = iter(tools)
        self.calls = 0
        self.requests = []
        self.agent = agent
        self.game_access = game_access

    def __call__(self, payload):
        self.requests.append(deepcopy(payload))
        self.calls += 1
        # Native background review can issue tool-free requests. It must not
        # consume a scheduled game action from the synthetic conversation.
        call = next(self.tools, None) if payload.get("tools") else None
        events = []
        response_id = f"resp_fixture_{self.calls}"
        if call:
            name, arguments = call
            if self.game_access == "native" and name == "game_action":
                if self.agent == "ga":
                    name, arguments = "code_run", {"type": "python", "script":
                        "import json; from game_client import action; print(json.dumps(action(**" +
                        repr(arguments) + "), ensure_ascii=False))"}
                else:
                    name = "mcp__cartography__game_action"
            if self.agent == "hermes" and name in ("game_action", "mcp__cartography__game_action"):
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
        support = make_support(output / "support")
        if args.agent == "hermes":
            shutil.copyfile(Path(__file__).resolve().parents[1] / "memorybenchmark/hermes_worker.py", support / "hermes_worker.py")
        prepared = PreparedAgent(previous / "source" / ("GenericAgent" if args.agent == "ga" else "hermes-agent"),
                                 support, previous / "baseline")
    else:
        prepared = load_adapter(args.agent).prepare(args.archive, output)
    jail = WSLJail(args.distro, args.runtime, args.runtime_dependency)
    sessions = StationNativeSessions(prepared.source, prepared.support, jail, agent=args.agent,
                                    feedback_mode=args.feedback_mode, game_access=args.game_access,
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
    first_model = ScriptedResponses(prefix_tools + [("game_action", {"action": "abandon"})], args.agent, args.game_access)
    first = sessions.run(game, "T1", prepared.baseline, output / "prefix", first_model, condition="prefix")
    assert first["infrastructure_ok"], first.get("infrastructure_error")
    assert any(MARKER in path.read_text(encoding="utf-8", errors="replace")
               for path in (output / "prefix/memory-after").rglob("*") if path.is_file())
    if args.agent == "hermes":
        assert list((output / "prefix/memory-after/.curator_backups/blobs").glob("*")), "skill rollback blobs did not persist"
        assert first["initial_session"]["game_tool_registered"]
        assert "memory" in [tool["name"] for tool in first["tools"]], "native tool callback was not decoded"
    for condition in ("retain", "clear"):
        model = ScriptedResponses([read, ("game_action", {"action": "abandon"})], args.agent, args.game_access)
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
    model = ScriptedResponses([context_tool] + [("game_action", {"action": "read"})] * 9, args.agent, args.game_access)
    budget = sessions.run(deepcopy(game), "T3", prepared.baseline, output / "budget", model, condition="clear")
    assert budget["infrastructure_ok"], budget.get("infrastructure_error")
    assert budget["main_calls"] == 10 and budget["final_calls"] >= 1
    assert budget["worker_result"]["native_result"]["result"] == "MAX_TURNS_EXCEEDED"
    assert context_marker in json.dumps(model.requests[10], ensure_ascii=False), "final opportunity lost native task context"
    linked = StationGame("omega_0000", load_design(EASY20_LINKED_DESIGN))
    itinerary_tools = [("game_action", {"action": "read"})]; position = "C"
    # Synthetic model supplies a fixed valid itinerary; this is not learned memory.
    for destination, process in (("P",False),("A",True),("R",False),("D",True),("C",False)):
        for node in shortest_route(linked.design, position, destination)[0][1:]:
            itinerary_tools.append(("game_action",{"action":"move","target":node}))
        position = destination
        if process:itinerary_tools.append(("game_action",{"action":"process"}))
    itinerary_tools.append(("game_action",{"action":"submit"}))
    linked_sessions = StationNativeSessions(prepared.source, prepared.support, jail, agent=args.agent,
                                            feedback_mode=args.feedback_mode, game_access=args.game_access,
                                            model_alias="fixture", max_turns=80, final_turns=3, seed=1)
    linked_model = ScriptedResponses(itinerary_tools,args.agent,args.game_access)
    result = linked_sessions.run(linked,"T1",prepared.baseline,output / "linked",linked_model,condition="prefix")
    assert result["infrastructure_ok"],result.get("infrastructure_error")
    assert linked.state.success and linked.observation()["stages_completed"] == 2
    processing = [e for e in linked.events if e.get("action",{}).get("type") == "process"]
    assert len(processing) == 2 and not processing[0]["delivered"]["observation"]["done"]
    assert len({e["task_run_id"] for e in linked.events}) == 1, "Two stages must share a native session"
    check_feedback_delivery(output / "linked", result, linked_model, args.feedback_mode)
    typed = StationGame("omega_00_00",load_design(EASY20_REUSE_DESIGN))
    typed_tools=[("game_action",{"action":"read"})];position="C"
    for destination,process in (("P",False),("A1",True),("R",False),("E1",True),("C",False)):
        for node in shortest_route(typed.design,position,destination)[0][1:]:
            typed_tools.append(("game_action",{"action":"move","target":node}))
        position=destination
        if process:typed_tools.append(("game_action",{"action":"process"}))
    typed_tools.append(("game_action",{"action":"submit"}))
    typed_model=ScriptedResponses(typed_tools,args.agent,args.game_access)
    typed_result=linked_sessions.run(typed,"T1",prepared.baseline,output/"typed",typed_model,condition="prefix")
    assert typed_result["infrastructure_ok"] and typed.state.success,typed_result.get("infrastructure_error")
    check_feedback_delivery(output/"typed",typed_result,typed_model,args.feedback_mode)
    typed_outputs=list(response_observations(typed_model.requests))
    assert any(r["feedback"].get("station_type")=="A" for r in typed_outputs)
    assert all("evaluation" not in r["observation"].get("environment",{}) for r in typed_outputs)
    assert "station_types" in json.dumps(typed_model.requests[0]),"Public class labels missing from actual native input"
    assert all(not s["has_prior_matching_opportunity"] for s in typed_result["experience_opportunities"]["stages"])
    print(json.dumps({"passed": True, "agent": args.agent, "llm_calls": 0,
                      "kind": "scripted_real_native_contract", "feedback_mode": args.feedback_mode,
                      "game_access": args.game_access,
                      "feedback_protocol": result["feedback_protocol"], "linked_actions": linked.steps,
                      "linked_distance": linked.distance, "typed_actions":typed.steps,"typed_distance":typed.distance,
                      "typed_public_labels_and_feedback_delivered":True,"output": str(output.resolve())}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--agent", choices=("ga", "hermes"), default="ga")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--runtime")
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepared-root", type=Path)
    parser.add_argument("--feedback-mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--game-access", choices=("native", "bridge"), default="bridge")
    run(parser.parse_args())
