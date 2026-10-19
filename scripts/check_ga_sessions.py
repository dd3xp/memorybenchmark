"""Real native GA + real jail, scripted model responses; NOT memory results.

The synthetic marker is test data for state isolation, not task knowledge.
No credentials or network model calls are needed.
"""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from memorybenchmark.experiment import InfrastructureError, experiment, resume_experiment
from memorybenchmark.ga_runtime import WSLJail
from memorybenchmark.ga_worker import PROMPT_PROTOCOL
from memorybenchmark.mcp_game import GAME_TRANSPORT, SDK_VERSION


class ScriptedModel:
    def __init__(self, tools, task):
        self.tools = iter(tools)
        self.calls = 0
        self.task = task
        self.previous_tool = None
    def __call__(self, payload):
        self.calls += 1
        anchor = payload["input"][0]
        assert anchor["role"] == "developer"
        assert f"当前委托：{self.task} ·" in anchor["content"][0]["text"]
        assert "current_task.md" not in anchor["content"][0]["text"]
        if self.previous_tool == "start_long_term_update":
            text = json.dumps(payload, ensure_ascii=True)
            assert "Memory Management SOP not found" not in text
            assert "This is L0:" in text
        tool = next(self.tools,None)
        self.previous_tool = tool[0] if tool else None
        events = []
        if tool is None:
            # The game has already accepted submit, even before final_loop.
            assert "委托已结束" in anchor["content"][0]["text"]
        if self.task == "T1" and self.calls == 1:
            # Force the real native backend to trim the original task history.
            # This filler is synthetic test data, never a model experiment.
            events.append({"type":"response.output_text.done",
                           "text":"synthetic context padding " * 10000})
        if tool:
            name, args = tool
            events.extend([
                {"type":"response.output_item.added","output_index":0,"item":{
                    "type":"function_call","call_id":f"fixture-{self.calls}","name":name}},
                {"type":"response.function_call_arguments.done","output_index":0,
                 "arguments":json.dumps(args)},
            ])
        else:
            events.append({"type":"response.output_text.done","text":"<summary>Fixture finished.</summary>"})
        events.append({"type":"response.completed","response":{"usage":{"input_tokens":1,"output_tokens":1}}})
        return {"lines":["data: " + json.dumps(e) for e in events]}


def fixture_model(task, condition):
    if task == "T1":
        script = ("from pathlib import Path\n"
                  "assert not Path('current_task.md').exists()\n"
                  "Path('../memory/session_fixture.txt').write_text('synthetic test marker')\n"
                  "Path('ephemeral_fixture.txt').write_text('must disappear')\n")
        tools = [("code_run",{"type":"python","script":script}),
                 ("game_action",{"action":"move","target":"J"}),
                 ("game_action",{"action":"move","target":"A"}),
                 ("game_action",{"action":"submit"}),
                 ("start_long_term_update",{})]
    else:
        script = ("from pathlib import Path\n"
                  "assert not Path('current_task.md').exists()\n"
                  "assert not Path('ephemeral_fixture.txt').exists()\n"
                  "assert not Path('../memory/partial_only.txt').exists()\n"
                  "p=Path('../memory/session_fixture.txt')\n"
                  "print('fixture-marker-present=', p.exists())\n")
        tools = [("code_run",{"type":"python","script":script}),
                 ("game_action",{"action":"move","target":"J"}),
                 ("game_action",{"action":"move","target":"A"}),
                 ("game_action",{"action":"move","target":"K"}),
                 ("game_action",{"action":"submit"})]
    return ScriptedModel(tools, task)


def run(archive, distro="Ubuntu-24.04", runtime=None):
    output = Path(".runs/ga-session-contract") / uuid4().hex
    jail=WSLJail(distro,runtime)
    failed_once=False
    def model_factory(task,condition):
        nonlocal failed_once
        model=fixture_model(task,condition)
        if condition == "clear" and not failed_once:
            failed_once=True
            original=model.__call__
            class Interrupted:
                def __call__(self,payload):
                    if model.calls == 2:
                        raise InfrastructureError("gateway_transport_error")
                    result=original(payload)
                    if model.calls == 1:
                        # Synthetic uncommitted state must disappear on retry.
                        for i,line in enumerate(result['lines']):
                            event=json.loads(line[6:])
                            if event['type']=='response.function_call_arguments.done':
                                args=json.loads(event['arguments'])
                                args['script'] += "\nPath('../memory/partial_only.txt').write_text('discard on retry')\n"
                                event['arguments']=json.dumps(args)
                                result['lines'][i]='data: '+json.dumps(event)
                    return result
            return Interrupted()
        return model
    report = experiment(archive,output,jail,model_factory,
                        kind="scripted_native_contract_not_model_evaluation", max_turns=12,final_turns=4)
    assert not report['complete']
    failed=report['pairs'][0]['conditions']['clear']
    assert failed['success'] is None and failed['distance']==2
    report=resume_experiment(output,jail,model_factory)
    assert report["complete"], output
    assert report["prompt_protocol"] == PROMPT_PROTOCOL
    assert report["adapter"]["agent_id"] == "ga"
    assert report["game_transport"] == GAME_TRANSPORT
    assert len(report['attempt_history'])==1
    pair = report["pairs"][0]
    retained, cleared = pair["conditions"]["retain"],pair["conditions"]["clear"]
    assert "session_fixture.txt" in retained["input_memory"]
    assert "session_fixture.txt" not in cleared["input_memory"]
    assert retained["input_world_digest"] == cleared["input_world_digest"]
    rows = report["prefix"] + [retained,cleared]
    assert len({row["host_process_id"] for row in rows}) == 3
    for row in rows:
        assert row["success"] and row["infrastructure_ok"]
        assert row["initial_session"]["initial_history_size"] == 0
        assert row["initial_session"]["initial_backend_history_size"] == 0
        assert row["initial_session"]["current_task_history_size"] == 1
        assert row["initial_session"]["working"] == {}
        assert row["initial_session"]["prompt_protocol"] == PROMPT_PROTOCOL
        assert row["game_transport"] == GAME_TRANSPORT
        assert row["mcp_sdk_version"] == SDK_VERSION
        assert row["mcp_protocol"] == "2025-11-25"
        assert "current_task.md" not in row["output_memory"]
        assert row["worker_result"]["isolation"]["network_blocked"]
        folder = output / row["path"]
        assert not (folder / "current_task.md").exists()
        assert f"当前委托：{row['task_id']} ·" in row["initial_session"]["task_reminder"]
        for number in range(row["main_calls"] + 1, row["llm_calls"] + 1):
            request = json.loads((folder / "model" / f"{number:03d}-request.json").read_text(encoding="utf-8"))
            assert "委托已结束" in request["input"][0]["content"][0]["text"]
    prefix_log = output / report["prefix"][0]["path"] / "native.log"
    assert "Trimmed context" in prefix_log.read_text(encoding="utf-8")
    for name,present in (("retain",True),("clear",False)):
        log=(output / pair["conditions"][name]["path"] / "native.log").read_text(encoding="utf-8")
        assert f"fixture-marker-present= {present}" in log
    assert 'partial_only.txt' not in cleared['output_memory']
    print(json.dumps({"passed":True,"kind":report["kind"],"artifacts":str(output.resolve())}))
    return report


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("archive",type=Path)
    parser.add_argument("--distro",default="Ubuntu-24.04")
    parser.add_argument("--runtime")
    args=parser.parse_args()
    run(args.archive,args.distro,args.runtime)
