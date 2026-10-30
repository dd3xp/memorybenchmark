"""Shared isolated-worker sessions, budgets, MCP game calls and memory snapshots."""
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
from uuid import uuid4

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .errors import InfrastructureError
from .decision_gate import DecisionGate
from .ga_runtime import changed_files, copy_memory, encode_state, memory_manifest, state_digest
from .game_session import dispatch_current
from .mcp_game import GAME_TRANSPORT, MCPGameClient, require_mcp
from .watch import atomic_json as save_json


class WorkerSessions:
    def __init__(self, source, support, jail, *, model_alias, max_turns=24, final_turns=6,
                 wall_seconds=900, seed=0, observer=None, prompt_protocol="agent-session-1",
                 worker_protocol="agent-session-1", worker_filename="agent_worker.py",
                 game_transport=GAME_TRANSPORT):
        if not 1 <= max_turns <= 100 or not 1 <= final_turns <= 20:
            raise ValueError("invalid model budget")
        self.source, self.support, self.jail = Path(source), Path(support), jail
        self.model_alias, self.max_turns, self.final_turns = model_alias, max_turns, final_turns
        self.wall_seconds, self.seed = wall_seconds, seed
        self.observer=observer
        self.prompt_protocol = prompt_protocol
        self.worker_protocol, self.worker_filename = worker_protocol, worker_filename
        if game_transport not in (GAME_TRANSPORT, "legacy-rpc"):
            raise ValueError("unsupported game transport")
        self.game_transport = game_transport
        if game_transport == GAME_TRANSPORT:
            require_mcp()

    def _worker(self, memory, output, config, adapter=None, model=None,watch_id=None,before_memory=None,game_client=None):
        command = self.jail.command(self.source, memory, self.support, self.wall_seconds,
                                    worker_filename=self.worker_filename)
        messages = queue.Queue()
        report = {"llm_calls":0, "model_requests":0, "main_calls":0,"final_calls":0,"tools":[], "session_id":uuid4().hex,
                  "infrastructure_ok":False, "continuations":[], "wall_seconds":self.wall_seconds}
        final_phase = False
        gate = DecisionGate(config.get("action_policy", "batch"))
        error_log = (output / "worker.stderr").open("w", encoding="utf-8")
        started = time.monotonic()
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
            # A model response can arrive after timeout(1) has killed the jail.
            # Classify the elapsed wall budget before writing to its dead pipe.
            if time.monotonic() - started >= self.wall_seconds:
                raise InfrastructureError("worker_wall_timeout")
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
                    if (kind == "request" and message.get("method") == "game"
                            and not gate.claim(message.get("params") or {})):
                        message["action_policy_rejected"] = True
                    audit.write(json.dumps(message,ensure_ascii=False) + "\n"); audit.flush()
                    if kind == "session":
                        report["initial_session"] = message
                    elif kind == "continuation":
                        report["continuations"].append(message)
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
                            if message.get("action_policy_rejected"):
                                result = gate.rejected()
                            else:
                                result = game_client(params) if game_client is not None else self._game(adapter, params)
                                gate.observe(result)
                                if self.observer: self.observer.observe(watch_id,result,params.get("action"))
                        elif method == "task_end" and adapter is not None and not final_phase:
                            native = params.get("native_result") or {}
                            if not adapter.game.done:
                                if report.get("initial_session", {}).get("execution_protocol") == "environment-gated-1":
                                    if native.get("result") != "MAX_TURNS_EXCEEDED" or report["main_calls"] != self.max_turns:
                                        raise InfrastructureError("premature task_end before environment completion or model budget")
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
                            try:
                                result = model(params)
                            except Exception as error:
                                detail = str(error)[:400] if isinstance(error, InfrastructureError) else type(error).__name__
                                report["model_error_at_call"] = report["llm_calls"]
                                audit.write(json.dumps({"kind": "model_transport_error", "call": report["llm_calls"],
                                                        "error": detail}, ensure_ascii=False) + "\n")
                                audit.flush()
                                raise
                            if self.observer:
                                self.observer.activity(watch_id,"model_complete","模型已响应",phase="finalizing" if final_phase else "acting")
                                if before_memory is not None:
                                    try: self.observer.memory(watch_id,before_memory,memory_manifest(memory))
                                    except (ValueError,OSError): pass
                            save_json(calls / f"{report['llm_calls']:03d}-response.json", result)
                            gate.begin_response(report["llm_calls"])
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
            if isinstance(error, OSError):
                report["host_io_error"] = {"type": type(error).__name__, "errno": error.errno,
                    "winerror": getattr(error, "winerror", None), "worker_returncode": process.poll()}
        finally:
            try: process.stdin.close()
            except (BrokenPipeError,OSError): pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                report["infrastructure_ok"] = False
                report["underlying_infrastructure_error"] = report.get("infrastructure_error")
                report["infrastructure_error"] = "worker cleanup unconfirmed; do not snapshot or advance"
            process.stdout.close()
            reader.join(timeout=2)
            error_log.close()
            report["worker_returncode"] = process.poll()
            report["worker_elapsed_seconds"] = round(time.monotonic() - started, 3)
            if gate.policy != "batch":
                report.update(action_policy=gate.policy, action_policy_rejections=gate.rejections)
            # A worker can report its failure while the parent is servicing its
            # last model request. Sending that response then hits a closed pipe;
            # preserve the already queued root error instead of losing it.
            while not messages.empty():
                pending = messages.get_nowait()
                if pending is None:
                    continue
                try: queued = json.loads(pending)
                except (TypeError, ValueError): continue
                if isinstance(queued, dict) and queued.get("kind") == "worker_error" and not report["infrastructure_ok"]:
                    detail = {"error_type": str(queued.get("error_type", "unknown"))[:80],
                              "message": str(queued.get("message", ""))[:300]}
                    report["underlying_worker_error"] = detail
                    if report.get("host_io_error", {}).get("worker_returncode") is not None and report["infrastructure_error"] != "worker cleanup unconfirmed; do not snapshot or advance":
                        report["infrastructure_error"] = "worker_" + detail["error_type"] + ": " + detail["message"]
        return report

    _game = staticmethod(dispatch_current)

    def probe(self, baseline, output):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        memory = output / "state"
        copy_memory(baseline, memory)
        report = self._worker(memory, output, {"protocol":self.worker_protocol, "seed":self.seed, "probe_only":True})
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
        state = self.support.parent / "live-state" / uuid4().hex
        state.parent.mkdir(parents=True,exist_ok=True)
        before = copy_memory(input_memory, state)
        save_json(output / "memory-before.json", before)
        adapter = GameAdapter(game)
        initial = adapter.dispatch({"command":"start", "task_id":task_id})
        save_json(output / "initial-public.json", initial)
        watch_id=self.observer.open(task_id,condition,initial,before) if self.observer else None
        config = self.task_config(initial)
        context = MCPGameClient(lambda request: dispatch_current(adapter, request)) if self.game_transport == GAME_TRANSPORT else nullcontext(None)
        with context as game_client:
            report = self._worker(state, output, config, adapter, model, watch_id, before, game_client)
            report["game_transport"] = self.game_transport
            if game_client is not None:
                report.update(game_client.identity)
        report.update(task_id=task_id, max_turns=self.max_turns, final_turns=self.final_turns,
                      prompt_protocol=self.prompt_protocol,
                      input_world_digest=state_digest(before_world), input_memory=before,
                      runtime_memory_id=state.name)
        document = report.get("initial_session", {}).get("task_document")
        if document is not None:
            report["task_document_sha256"] = sha256(document.encode("utf-8")).hexdigest()
        reminder = report.get("initial_session", {}).get("task_reminder")
        if reminder is not None:
            report["task_reminder_sha256"] = sha256(reminder.encode("utf-8")).hexdigest()
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
        if game.world.get("respawn"):
            report.update(deaths=game.deaths,
                          respawn_penalty=sum(e["weight"] for e in game.recovery_history))
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

    def task_config(self, initial):
        return {"protocol": self.worker_protocol, "seed": self.seed, "model": self.model_alias,
                "initial_text": initial["text"], "task_observation": initial["observation"],
                "max_turns": self.max_turns, "final_turns": self.final_turns}
