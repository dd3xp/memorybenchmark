"""Bounded development smoke using the bundled GA's actual model/tool loop.

Not a benchmark: filesystem/network isolation and paired memory controls are
not installed by this script. All artifacts remain under ignored .runs/.
Credentials are taken only from the process environment, never written.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import types
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from memorybenchmark.adapters import GameAdapter
from memorybenchmark.agent_bridge import GameTool, register_genericagent
from memorybenchmark.game import Game


def prepare(archive, output):
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            relative = Path(member.name)
            if relative.parts[0] != "GenericAgent" or not (member.isfile() or member.isdir()):
                continue
            if any(p in ("memory", "temp", "__pycache__", ".git") for p in relative.parts):
                continue
            if relative.name in ("mykey.py", "mykey.json") or relative.name.startswith(".env") or relative.suffix in (".log", ".pyc"):
                continue
            bundle.extract(member, path=output, filter="data")
    return output / "GenericAgent"


def run(archive, output, model, base_url, max_turns):
    if not os.environ.get("MEMORYBENCH_GATEWAY_KEY"):
        raise RuntimeError("Set MEMORYBENCH_GATEWAY_KEY in the process environment.")
    output.mkdir(parents=True, exist_ok=False)
    source = prepare(archive, output)
    config = types.ModuleType("mykey")
    config.native_oai_config = {"apikey": os.environ["MEMORYBENCH_GATEWAY_KEY"],
        "apibase": base_url, "model": model, "api_mode": "responses", "reasoning_effort": "low",
        "max_retries": 0, "connect_timeout": 10, "read_timeout": 40, "context_win": 50000, "proxy": None}
    config.proxy = None
    sys.modules["mykey"] = config
    sys.path.insert(0, str(source))
    previous_cwd = Path.cwd()
    game = Game(log_path=output / "events.jsonl")
    adapter = GameAdapter(game)
    observation = adapter.dispatch({"command":"start", "task_id":"T1"})
    report = {"kind":"development_smoke_no_isolation", "agent":"bundled_GenericAgent",
              "model_alias":model, "max_model_turns":max_turns, "max_output_tokens":1024,
              "archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(), "llm_calls":0,
              "paired_memory_experiment":False}
    try:
        os.chdir(source)
        with (output / "native.log").open("w",encoding="utf-8") as log, redirect_stdout(log), redirect_stderr(log):
            import requests
            original_post = requests.post
            def verified_post(*args, **kwargs):
                kwargs["verify"] = True
                return original_post(*args, **kwargs)
            requests.post = verified_post
            import agentmain
            from agent_loop import StepOutcome
            agent = agentmain.GeneraticAgent()
            agent.next_llm(0)
            register_genericagent(agentmain, agent, StepOutcome, GameTool(adapter.dispatch))
            raw_ask = agent.llmclient.backend.raw_ask
            def bounded_ask(*args, **kwargs):
                report["llm_calls"] += 1
                if report["llm_calls"] > max_turns:
                    raise RuntimeError("development model-call budget exhausted")
                kwargs["max_tokens"] = 1024
                return raw_ask(*args, **kwargs)
            agent.llmclient.backend.raw_ask = bounded_ask
            handler = agentmain.GenericAgentHandler(agent, [], str(source / "temp"))
            memory_before = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (source / "memory").rglob("*") if p.is_file()}
            guide = ("\n你正在进行制图游戏开发测试。游戏只能通过 game_action 操作；到达自动测绘，目标满足后调用游戏 submit。"
                     "你可以使用原生文件和记忆工具管理自己的笔记。不读取游戏源码或评测文件，不访问无关的文件和网络。"
                     "游戏 done=true 后不要再操作游戏，可自行整理经验并结束回复。\n")
            generator = agentmain.agent_runner_loop(agent.llmclient, agentmain.get_system_prompt() + guide,
                observation["text"], handler, agentmain.TOOLS_SCHEMA, max_turns=max_turns, verbose=False)
            try:
                while True:
                    chunk = next(generator)
                    log.write(str(chunk))
                    log.flush()
            except StopIteration as ended:
                report["native_loop_result"] = str(ended.value)[:500]
            report["native_import"] = "passed"
            memory_after = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (source / "memory").rglob("*") if p.is_file()}
            report["memory_files_changed"] = sorted(k for k,v in memory_after.items() if memory_before.get(k) != v)
    except Exception as error:
        report["error_type"] = type(error).__name__
        # Do not surface raw upstream exceptions that may embed auth headers.
    finally:
        os.chdir(previous_cwd)
    report.update({"success":game.success,"done":game.done,"game_actions":game.steps,
                   "distance":game.distance,"effort":game.effort,"remaining_stamina":game.stamina,
                   "final_location":game.position})
    (output / "summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--max-turns", type=int, default=8, choices=range(1,13))
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    output = ROOT / ".runs" / "native-ga-smoke" / uuid4().hex
    print(json.dumps(run(args.archive.resolve(),output,args.model,args.base_url,args.max_turns),ensure_ascii=False,indent=2))
    print("Artifacts:",output)
