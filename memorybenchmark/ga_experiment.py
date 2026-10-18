"""Native GA sessions and matched next-task memory interventions.

At each boundary both runs start from the same actual retained-history state.
Only the retained branch advances that history; cleared probes never feed back.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .game import Game, ProtocolError
from .watch import Observer, atomic_json
from .ga_runtime import (WSLJail, changed_files, copy_memory, encode_state, extract_native,
                         decode_state, make_support, memory_manifest, state_digest)


def save_json(path, value):
    atomic_json(path,value)


class InfrastructureError(RuntimeError):
    pass


class GatewayModel:
    """Forward native SSE payloads only to the configured endpoint, with TLS."""
    def __init__(self, base_url, api_key, model, max_output_tokens=2048):
        if not base_url.startswith("https://"):
            raise ValueError("model gateway must use HTTPS")
        self.endpoint = base_url.rstrip("/")
        self.endpoint += "/responses" if self.endpoint.endswith("/v1") else "/v1/responses"
        self.api_key, self.model = api_key, model
        self.max_output_tokens = max_output_tokens

    def __call__(self, payload):
        if not isinstance(payload, dict) or "input" not in payload:
            raise InfrastructureError("invalid native model payload")
        # No caller URL/header forwarding, server-side stored conversation, or
        # unmanaged built-in tools. Native file/memory tools run in the jail.
        if any(t.get("type") != "function" for t in payload.get("tools", [])):
            raise InfrastructureError("unregistered remote tool")
        payload = {k:v for k,v in payload.items() if k in ("input", "tools", "reasoning")}
        payload.update(model=self.model, stream=True, store=False)
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        request = Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers={
            "Authorization":"Bearer " + self.api_key, "Content-Type":"application/json", "Accept":"text/event-stream"})
        lines, total, completed = [], 0, False
        deadline = time.monotonic() + 100
        try:
            with urlopen(request, timeout=45) as response:
                for raw in response:
                    total += len(raw)
                    if total > 8 * 1024**2 or time.monotonic() > deadline:
                        raise InfrastructureError("model stream budget exceeded")
                    line = raw.decode("utf-8").rstrip("\r\n")
                    lines.append(line)
                    if line.startswith("data:") and line[5:].strip() != "[DONE]":
                        try: event = json.loads(line[5:])
                        except ValueError: continue
                        if event.get("type") in ("error", "response.failed", "response.incomplete"):
                            raise InfrastructureError("model response did not complete")
                        completed |= event.get("type") == "response.completed"
        except HTTPError as error:
            raise InfrastructureError("gateway_http_" + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise InfrastructureError("gateway_transport_error") from None
        if not completed:
            raise InfrastructureError("incomplete model stream")
        return {"lines":lines}


class NativeGASessions:
    def __init__(self, source, support, jail, *, model_alias, max_turns=24, final_turns=6,
                 wall_seconds=900, seed=0, observer=None):
        if not 1 <= max_turns <= 100 or not 1 <= final_turns <= 20:
            raise ValueError("invalid model budget")
        self.source, self.support, self.jail = Path(source), Path(support), jail
        self.model_alias, self.max_turns, self.final_turns = model_alias, max_turns, final_turns
        self.wall_seconds, self.seed = wall_seconds, seed
        self.observer=observer

    def _worker(self, memory, output, config, adapter=None, model=None,watch_id=None,before_memory=None):
        command = self.jail.command(self.source, memory, self.support, self.wall_seconds)
        messages = queue.Queue()
        report = {"llm_calls":0, "model_requests":0, "main_calls":0,"final_calls":0,"tools":[], "session_id":uuid4().hex,
                  "infrastructure_ok":False}
        final_phase = False
        error_log = (output / "worker.stderr").open("w", encoding="utf-8")
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log,
                                   text=True, encoding="utf-8", errors="replace", bufsize=1)
        report["host_process_id"] = process.pid
        def read():
            try:
                while True:
                    line = process.stdout.readline(4 * 1024**2 + 1)
                    if not line: break
                    messages.put(line)
            finally:
                messages.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def send(value):
            process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
            process.stdin.flush()
        deadline = time.monotonic() + self.wall_seconds + 10
        try:
            send(config)
            with (output / "native.log").open("w",encoding="utf-8") as log, (output / "audit.jsonl").open("w",encoding="utf-8") as audit:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise InfrastructureError("worker_wall_timeout")
                    try: line = messages.get(timeout=min(1, remaining))
                    except queue.Empty: continue
                    if line is None: break
                    if len(line.encode("utf-8")) > 4 * 1024**2:
                        raise InfrastructureError("worker_message_too_large")
                    message = json.loads(line)
                    kind = message.get("kind")
                    if kind == "log":
                        log.write(message["text"]); log.flush()
                        continue
                    audit.write(json.dumps(message,ensure_ascii=False) + "\n"); audit.flush()
                    if kind == "session":
                        report["initial_session"] = message
                    elif kind == "tool":
                        report["tools"].append({"name":message["name"],"args":message["args"]})
                        if self.observer:
                            names={"game_action":"操作游戏","code_run":"执行脚本","file_read":"读取文件",
                                   "file_write":"写入文件","file_patch":"修改文件","start_long_term_update":"整理长期记忆"}
                            label=names.get(message["name"],message["name"])
                            target=message["args"].get("target")
                            if target: label+=" · "+str(target)[:60]
                            self.observer.activity(watch_id,"tool",label,phase="acting")
                    elif kind == "worker_error":
                        raise InfrastructureError("worker_" + message["error_type"] + ": " + message["message"])
                    elif kind == "finished":
                        report["worker_result"] = message
                    elif kind == "request":
                        method, params = message.get("method"), message.get("params")
                        if method == "game" and adapter is not None:
                            result = self._game(adapter, params)
                            if self.observer: self.observer.observe(watch_id,result,params.get("action"))
                        elif method == "task_end" and adapter is not None and not final_phase:
                            native = params.get("native_result") or {}
                            if not adapter.game.done:
                                terminal = adapter.game.finish_incomplete("model_budget" if native.get("result") == "MAX_TURNS_EXCEEDED" else "agent_stopped")
                                result = adapter._public(terminal)
                            else:
                                result = adapter.dispatch({"command":"read"})
                            final_phase = True
                            if self.observer:
                                self.observer.observe(watch_id,result)
                                self.observer.activity(watch_id,"finalize","任务结算，进入自主整理",phase="finalizing")
                        elif method == "model" and model is not None:
                            report["model_requests"] += 1
                            field, budget = ("final_calls",self.final_turns) if final_phase else ("main_calls",self.max_turns)
                            if report[field] >= budget:
                                raise InfrastructureError("unexpected model calls beyond budget")
                            report["llm_calls"] += 1
                            report[field] += 1
                            if self.observer:
                                self.observer.activity(watch_id,"model_start","等待模型响应",calls=report["llm_calls"],
                                                       phase="finalizing" if final_phase else "thinking")
                            calls = output / "model"
                            calls.mkdir(exist_ok=True)
                            save_json(calls / f"{report['llm_calls']:03d}-request.json", params)
                            result = model(params)
                            if self.observer:
                                self.observer.activity(watch_id,"model_complete","模型已响应",phase="finalizing" if final_phase else "acting")
                                if before_memory is not None:
                                    try: self.observer.memory(watch_id,before_memory,memory_manifest(memory))
                                    except (ValueError,OSError): pass
                            save_json(calls / f"{report['llm_calls']:03d}-response.json", result)
                        else:
                            raise InfrastructureError("unregistered worker RPC")
                        send({"id":message["id"],"result":result})
                code = process.wait(timeout=5)
                if code != 0 or "worker_result" not in report:
                    raise InfrastructureError("worker exited without a completed result")
                report["infrastructure_ok"] = True
        except Exception as error:
            # No raw upstream auth-bearing exception is written or printed.
            report["infrastructure_error"] = str(error)[:400] if isinstance(error, InfrastructureError) else type(error).__name__
        finally:
            try: process.stdin.close()
            except (BrokenPipeError,OSError): pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                report["infrastructure_ok"] = False
                report["infrastructure_error"] = "worker cleanup unconfirmed; do not snapshot or advance"
            process.stdout.close()
            reader.join(timeout=2)
            error_log.close()
        return report

    @staticmethod
    def _game(adapter, request):
        if not isinstance(request, dict) or request.get("command") not in ("read", "action"):
            return {"error":"invalid_request", "message":"只能操作当前任务。"}
        if set(request) - {"command", "request_id", "action", "expected_revision"}:
            return {"error":"invalid_request", "message":"未知请求参数。"}
        if request["command"] == "action" and adapter.game.done:
            return adapter._public({"observation":adapter.game.observation(),"feedback":"任务已结束。", "outcome":"closed"})
        request = deepcopy(request)
        if request["command"] == "action" and "expected_revision" not in request:
            request_id=request.get("request_id")
            if isinstance(request_id,str) and 0 < len(request_id) <= 128:
                if not hasattr(adapter,"_native_revisions"): adapter._native_revisions={}
                request["expected_revision"]=adapter._native_revisions.setdefault(request_id,adapter.game.revision)
        try:
            return adapter.dispatch(request)
        except ProtocolError as error:
            return {"error":"protocol_error", "message":str(error)}

    def probe(self, baseline, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        memory = output / "state"
        copy_memory(baseline, memory)
        report = self._worker(memory, output, {"protocol":"ga-session-1", "seed":self.seed, "probe_only":True})
        save_json(output / "summary.json", report)
        if not report["infrastructure_ok"]:
            raise InfrastructureError(report.get("infrastructure_error", "jail probe failed"))
        return report

    def run(self, game, task_id, input_memory, output, model,*,condition="prefix"):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        before_world = game.snapshot()
        save_json(output / "world-before.json", encode_state(before_world))
        # Opaque host path prevents mountinfo from exposing retain/clear labels.
        state = self.source.parent.parent / "live-state" / uuid4().hex
        state.parent.mkdir(parents=True,exist_ok=True)
        before = copy_memory(input_memory, state)
        save_json(output / "memory-before.json", before)
        adapter = GameAdapter(game)
        initial = adapter.dispatch({"command":"start", "task_id":task_id})
        save_json(output / "initial-public.json", initial)
        watch_id=self.observer.open(task_id,condition,initial,before) if self.observer else None
        config = {"protocol":"ga-session-1", "seed":self.seed, "model":self.model_alias,
                  "initial_text":initial["text"],"max_turns":self.max_turns,"final_turns":self.final_turns}
        report = self._worker(state, output, config, adapter, model,watch_id,before)
        report.update(task_id=task_id, max_turns=self.max_turns, final_turns=self.final_turns,
                      input_world_digest=state_digest(before_world), input_memory=before,
                      runtime_memory_id=state.name)
        if report["infrastructure_ok"]:
            if not game.done:
                native = report["worker_result"].get("native_result") or {}
                game.finish_incomplete("model_budget" if native.get("result") == "MAX_TURNS_EXCEEDED" else "agent_stopped")
            try:
                after = copy_memory(state, output / "memory-after")
                report["memory_changed"] = changed_files(before, after)
                report["content_changed"] = [p for p in report["memory_changed"] if p != "file_access_stats.json"]
                report["output_memory"] = after
                if self.observer: self.observer.memory(watch_id,before,after,True)
            except (ValueError, RuntimeError) as error:
                report.update(infrastructure_ok=False, infrastructure_error=type(error).__name__ + ": " + str(error))
        report.update(success=game.success, done=game.done, game_actions=game.steps,
                      distance=game.distance, effort=game.effort, remaining_stamina=game.stamina)
        # Infrastructure failures never advance the canonical world or memory.
        if not report["infrastructure_ok"]:
            report["partial_game_success"] = report.pop("success")
            report["success"] = None
        (output / "events.jsonl").write_text("".join(json.dumps(e,ensure_ascii=False)+"\n" for e in game.events),encoding="utf-8")
        save_json(output / "world-after.json", encode_state(game.snapshot()))
        save_json(output / "graph.json", {"graph":commute_graph(game.events,game.task_run_id),
                                         "diagnostics":diagnose(game.events,game.task_run_id)})
        save_json(output / "summary.json", report)
        if self.observer: self.observer.close(watch_id,report)
        return report


def experiment(archive, output, jail, model_factory, *, tasks=("T1","T2"), prefix_count=1,
               model_alias="gpt-5.6-luna", max_turns=24, final_turns=6, seed=0, kind="native_gateway_pilot",
               max_output_tokens=None, scenario="valley"):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = extract_native(archive, output / "source")
    baseline = output / "baseline"
    baseline_manifest = copy_memory(source / "memory", baseline)
    support = make_support(output / "support")
    sessions = NativeGASessions(source, support, jail, model_alias=model_alias,
                               max_turns=max_turns, final_turns=final_turns, seed=seed)
    world = Game(scenario=scenario)
    if len(set(tasks)) != len(tasks) or any(t not in world.tasks for t in tasks) or not 1 <= prefix_count < len(tasks):
        raise ValueError("need unique known tasks, a nonempty prefix and a continuation")
    initial_world = world.snapshot()
    save_json(output / "initial-world.json", encode_state(initial_world))
    report = {"kind":kind, "protocol":"ga-session-1", "agent":"bundled_GenericAgent",
              "archive_sha256":sha256(Path(archive).read_bytes()).hexdigest(),
              "baseline_memory":baseline_manifest, "tasks":list(tasks), "prefix_count":prefix_count,
              "model_alias":model_alias, "seed":seed,"max_turns":max_turns,"final_turns":final_turns,
              "max_output_tokens":max_output_tokens,
              "scenario":scenario, "world_version":world.world["version"],
              "initial_world_digest":state_digest(initial_world),
              "geography_protocol":"shared_submitted_geography" if world.world.get("shared_geography") else "task_local",
              "prefix":[], "pairs":[], "complete":False,
              "intervention":"matched_next_task_reset_to_shipped_baseline",
              "persistent_scope":"/agent/memory only", "forced_memory_write":False}
    report["worker_sha256"] = sha256((support / "ga_worker.py").read_bytes()).hexdigest()
    report["bridge_sha256"] = sha256((support / "agent_bridge.py").read_bytes()).hexdigest()
    save_json(output / "experiment.json", report)
    observer=Observer(output)
    observer.begin(report)
    sessions.observer=observer
    try:
        sessions.probe(baseline, output / "isolation")
        result=_continue(output,report,sessions,model_factory)
    except (Exception,KeyboardInterrupt):
        observer.finish(False)
        raise
    observer.finish(result["complete"])
    return result


def _continue(output, report, sessions, model_factory):
    """Reuse successful sessions; every retry restores BOTH pre-task states."""
    baseline = output / "baseline"
    if memory_manifest(baseline) != report["baseline_memory"]:
        raise InfrastructureError("baseline memory changed")
    world, memory = Game(scenario=report.get("scenario", "valley")), baseline
    if report.get("initial_world_digest"):
        initial = decode_state(json.loads((output / "initial-world.json").read_text(encoding="utf-8")))
        if state_digest(initial) != report["initial_world_digest"]:
            raise InfrastructureError("frozen initial world changed")
        world.restore(initial)
    tasks, prefix_count, seed = report["tasks"],report["prefix_count"],report["seed"]
    def record(): save_json(output / "experiment.json", report)
    def load_success(row):
        location = output / row["path"]
        state = decode_state(json.loads((location / "world-after.json").read_text(encoding="utf-8")))
        restored = Game(); restored.restore(state)
        path = location / "memory-after"
        if memory_manifest(path) != row["output_memory"]:
            raise InfrastructureError("successful memory checkpoint changed")
        return restored,path
    def execute(task,condition,parent,old=None):
        location = parent / condition
        if location.exists():
            location = parent / (condition + "-retry-" + uuid4().hex[:8])
        candidate = Game(); candidate.restore(world.snapshot())
        row = sessions.run(candidate,task,memory if condition != "clear" else baseline,
                           location,model_factory(task,condition),condition=condition)
        row = {"path":str(location.relative_to(output)),**row}
        if old is not None:
            report.setdefault("attempt_history",[]).append(old)
        print(json.dumps({"task":task,"condition":condition,"infrastructure_ok":row["infrastructure_ok"],
                          "success":row["success"],"llm_calls":row["llm_calls"]}),flush=True)
        return row
    for position,task in enumerate(tasks[:prefix_count]):
        old = report["prefix"][position] if position < len(report["prefix"]) else None
        if old and old["infrastructure_ok"]:
            row = old
        else:
            row = execute(task,"prefix",output / "prefix" / task,old)
            if old is None: report["prefix"].append(row)
            else: report["prefix"][position] = row
            record()
        if not row["infrastructure_ok"]: return report
        world,memory = load_success(row)
    for index, task in enumerate(tasks[prefix_count:]):
        checkpoint = world.snapshot()
        pair_root = output / "pairs" / task
        pair = next((p for p in report["pairs"] if p["task_id"] == task),None)
        if pair is None:
            pair_root.mkdir(parents=True)
            save_json(pair_root / "checkpoint.json", encode_state(checkpoint))
            pair = {"task_id":task,"checkpoint_digest":state_digest(checkpoint), "conditions":{}}
            report["pairs"].append(pair)
        if pair["checkpoint_digest"] != state_digest(checkpoint):
            raise InfrastructureError("shared world checkpoint changed")
        # Alternate order to avoid always running the retained condition first.
        order = ("retain","clear") if (seed + index) % 2 == 0 else ("clear","retain")
        pair["execution_order"] = list(order)
        for condition in order:
            old = pair["conditions"].get(condition)
            if old and old["infrastructure_ok"]: continue
            pair["conditions"][condition] = execute(task,condition,pair_root,old)
            record()
        if not all(r["infrastructure_ok"] for r in pair["conditions"].values()):
            return report
        if not all(r["input_world_digest"] == pair["checkpoint_digest"] for r in pair["conditions"].values()):
            raise InfrastructureError("paired initial worlds differ")
        if pair["conditions"]["clear"]["input_memory"] != report["baseline_memory"]:
            raise InfrastructureError("cleared memory input changed")
        if pair["conditions"]["retain"]["input_memory"] != memory_manifest(memory):
            raise InfrastructureError("retained memory input changed")
        world,memory = load_success(pair["conditions"]["retain"])
    report["complete"] = True
    record()
    return report


def resume_experiment(output,jail,model_factory):
    output=Path(output).resolve()
    report=json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    if report["complete"]: return report
    if report.get("aborted"): raise InfrastructureError("aborted protocol cannot be resumed")
    support=output / "support"
    for file,key in (("ga_worker.py","worker_sha256"),("agent_bridge.py","bridge_sha256")):
        if sha256((support / file).read_bytes()).hexdigest() != report[key]:
            raise InfrastructureError("worker protocol changed; start a new run")
    observer=Observer(output)
    observer.begin(report)
    sessions=NativeGASessions(output / "source/GenericAgent",support,jail,model_alias=report["model_alias"],
                              max_turns=report["max_turns"],final_turns=report["final_turns"],seed=report["seed"],observer=observer)
    report["resume_count"]=report.get("resume_count",0)+1
    save_json(output / "experiment.json",report)
    try: result=_continue(output,report,sessions,model_factory)
    except (Exception,KeyboardInterrupt):
        observer.finish(False)
        raise
    observer.finish(result["complete"])
    return result


def main():
    parser = argparse.ArgumentParser(description="Native GA cross-session cartography pilot")
    parser.add_argument("archive",type=Path,nargs="?")
    parser.add_argument("--resume",type=Path,help="resume an interrupted run with frozen native protocol and budgets")
    parser.add_argument("--base-url",required=True)
    parser.add_argument("--model",default="gpt-5.6-luna")
    parser.add_argument("--scenario", choices=("valley", "lake-easy", "loch-ness"), default="lake-easy")
    parser.add_argument("--tasks",nargs="+",default=["T1","T2"])
    parser.add_argument("--prefix-count",type=int,default=1)
    parser.add_argument("--max-turns",type=int,default=24)
    parser.add_argument("--final-turns",type=int,default=6)
    parser.add_argument("--max-output-tokens",type=int,default=2048,
                        help="0 uses gateway output defaults; call/wall/stream limits still apply")
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--distro",default="Ubuntu-24.04")
    parser.add_argument("--runtime")
    parser.add_argument("--infra-retries",type=int,default=1,choices=range(4))
    args = parser.parse_args()
    key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
    if not key: parser.error("set MEMORYBENCH_GATEWAY_KEY in the parent process environment")
    output = args.resume or (Path(".runs/ga-cross-session") / uuid4().hex)
    if args.max_output_tokens < 0: parser.error("max-output-tokens must be nonnegative")
    output_tokens = args.max_output_tokens or None
    jail=WSLJail(args.distro,args.runtime)
    if args.resume:
        saved=json.loads((output/'experiment.json').read_text(encoding='utf-8'))
        model=GatewayModel(args.base_url,key,saved['model_alias'],saved['max_output_tokens'])
        result=resume_experiment(output,jail,lambda *_:model)
    else:
        if args.archive is None: parser.error("archive is required for a new run")
        model = GatewayModel(args.base_url,key,args.model,output_tokens)
        result = experiment(args.archive, output, jail, lambda *_:model,
                            tasks=args.tasks,prefix_count=args.prefix_count,model_alias=args.model,
                            max_turns=args.max_turns,final_turns=args.final_turns,seed=args.seed,
                            max_output_tokens=output_tokens,scenario=args.scenario)
    for _ in range(args.infra_retries):
        if result["complete"]: break
        failures=[r for r in result['prefix'] if not r['infrastructure_ok']]
        failures += [r for p in result['pairs'] for r in p['conditions'].values() if not r['infrastructure_ok']]
        if not failures or any(not any(s in r.get('infrastructure_error','') for s in
            ('gateway_transport_error','gateway_http_429','gateway_http_500','gateway_http_502','gateway_http_503','gateway_http_504','incomplete model stream')) for r in failures):
            break
        result=resume_experiment(output,jail,lambda *_:model)
    print(json.dumps({"complete":result["complete"],"artifacts":str(output.resolve())}))
    if not result["complete"]: raise SystemExit(1)


if __name__ == "__main__": main()
