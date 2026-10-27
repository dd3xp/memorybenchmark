"""Agent-neutral matched memory experiments over the task-scoped game MCP."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from .agent_adapters import (PreparedAgent, adapter_identity, available_adapters, load_adapter)
from .errors import AdapterError, InfrastructureError
from .ga_runtime import WSLJail, decode_state, encode_state, memory_manifest, state_digest
from .game import Game
from .mcp_game import GAME_TRANSPORT, require_mcp, transport_identity
from .model_gateway import GatewayModel
from .watch import Observer, atomic_json as save_json


def experiment(archive, output, jail, model_factory, *, agent="ga", adapter_spec=None,
               tasks=("T1", "T2"), prefix_count=1, model_alias="gpt-5.6-luna",
               max_turns=24, final_turns=6, seed=0, kind="native_gateway_pilot",
               max_output_tokens=None, scenario="valley"):
    # Unsupported agents/dependencies/budgets fail before creating a run or
    # performing a game action. They never become a fabricated zero score.
    adapter = load_adapter(agent, adapter_spec)
    require_mcp()
    if not 1 <= max_turns <= 100 or not 1 <= final_turns <= 20:
        raise ValueError("invalid model budget")
    world = Game(scenario=scenario)
    if len(set(tasks)) != len(tasks) or any(t not in world.tasks for t in tasks) or not 1 <= prefix_count < len(tasks):
        raise ValueError("need unique known tasks, a nonempty prefix and a continuation")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    prepared = adapter.prepare(Path(archive), output).validate(output, adapter.worker_filename)
    baseline_manifest = memory_manifest(prepared.baseline)
    initial_world = world.snapshot()
    save_json(output / "initial-world.json", encode_state(initial_world))
    report = {"kind": kind, "protocol": "matched-memory-1", "agent": adapter.label,
              "adapter": adapter_identity(adapter, adapter_spec),
              "game_transport": GAME_TRANSPORT, "mcp": transport_identity(),
              "prompt_protocol": adapter.prompt_protocol,
              "task_anchor": adapter.task_anchor,
              "archive_sha256": sha256(Path(archive).read_bytes()).hexdigest() if Path(archive).is_file() else None,
              "source_path": str(prepared.source.relative_to(output)),
              "support_path": str(prepared.support.relative_to(output)),
              "support_files": memory_manifest(prepared.support),
              "baseline_memory": baseline_manifest, "tasks": list(tasks), "prefix_count": prefix_count,
              "model_alias": model_alias, "seed": seed, "max_turns": max_turns, "final_turns": final_turns,
              "max_output_tokens": max_output_tokens, "scenario": scenario,
              "world_version": world.world["version"], "initial_world_digest": state_digest(initial_world),
              "geography_protocol": "shared_submitted_geography" if world.world.get("shared_geography") else "task_local",
              "prefix": [], "pairs": [], "complete": False,
              "intervention": "matched_next_task_reset_to_shipped_baseline",
              "persistent_scope": "/agent/memory only", "forced_memory_write": False}
    # Preserve convenient checksums used by existing GA audit tooling.
    report["worker_sha256"] = sha256((prepared.support / adapter.worker_filename).read_bytes()).hexdigest()
    if (prepared.support / "agent_bridge.py").is_file():
        report["bridge_sha256"] = sha256((prepared.support / "agent_bridge.py").read_bytes()).hexdigest()
    save_json(output / "experiment.json", report)
    observer = Observer(output)
    observer.begin(report)
    sessions = adapter.create_sessions(prepared, jail, report, observer)
    try:
        sessions.probe(prepared.baseline, output / "isolation")
        result = _continue(output, report, sessions, model_factory)
    except (Exception, KeyboardInterrupt):
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



def resume_experiment(output, jail, model_factory):
    output = Path(output).resolve()
    report = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    if report["complete"]:
        return report
    if report.get("aborted"):
        raise InfrastructureError("aborted protocol cannot be resumed")
    if "adapter" in report:
        recorded = report["adapter"]
        adapter = load_adapter(recorded["agent_id"], recorded["factory"])
        if adapter_identity(adapter, recorded["factory"]) != recorded:
            raise InfrastructureError("agent adapter changed; restore the recorded version before resuming")
        if report.get("game_transport") != GAME_TRANSPORT or report.get("mcp") != transport_identity():
            raise InfrastructureError("game MCP protocol changed; restore the recorded version before resuming")
        prepared = PreparedAgent(output / report["source_path"], output / report["support_path"], output / "baseline")
        prepared.validate(output, adapter.worker_filename)
        if memory_manifest(prepared.support) != report["support_files"]:
            raise InfrastructureError("frozen worker support changed; restore it before resuming")
    else:
        # Old runs retain their frozen workers and direct RPC game transport.
        adapter = load_adapter("ga")
        prepared = PreparedAgent(output / "source/GenericAgent", output / "support", output / "baseline")
        for filename, key in (("ga_worker.py", "worker_sha256"), ("agent_bridge.py", "bridge_sha256")):
            if sha256((prepared.support / filename).read_bytes()).hexdigest() != report[key]:
                raise InfrastructureError("worker protocol changed; start a new run")
    observer = Observer(output)
    observer.begin(report)
    sessions = adapter.create_sessions(prepared, jail, report, observer)
    report["resume_count"] = report.get("resume_count", 0) + 1
    save_json(output / "experiment.json", report)
    try:
        result = _continue(output, report, sessions, model_factory)
    except (Exception, KeyboardInterrupt):
        observer.finish(False)
        raise
    observer.finish(result["complete"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Native agent memory experiments: shared MCP game + lifecycle adapters")
    parser.add_argument("archive", type=Path, nargs="?", help="native archive or user adapter bundle")
    parser.add_argument("--agent", help="registered agent ID, default ga")
    parser.add_argument("--adapter", help="user lifecycle plugin: importable_module:create_adapter")
    parser.add_argument("--list-agents", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--scenario", choices=("valley", "lake-easy"), default="lake-easy")
    parser.add_argument("--tasks", nargs="+", default=["T1", "T2"])
    parser.add_argument("--prefix-count", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--final-turns", type=int, default=6)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--runtime")
    parser.add_argument("--runtime-dependency", action="append", default=[])
    parser.add_argument("--infra-retries", type=int, default=1, choices=range(4))
    args = parser.parse_args(argv)
    if args.list_agents:
        print(json.dumps(available_adapters(), ensure_ascii=False))
        return
    saved = None
    if args.resume:
        saved = json.loads((args.resume / "experiment.json").read_text(encoding="utf-8"))
        recorded = saved.get("adapter", {"agent_id": "ga", "factory": None})
        if (args.agent and args.agent != recorded["agent_id"]) or (args.adapter and args.adapter != recorded["factory"]):
            parser.error("resume must use the recorded agent adapter")
        agent_id, factory = recorded["agent_id"], recorded["factory"]
    else:
        agent_id, factory = args.agent or "ga", args.adapter
    try:
        load_adapter(agent_id, factory)
        if saved is None or saved.get("game_transport") == GAME_TRANSPORT:
            require_mcp()
    except (AdapterError, RuntimeError) as error:
        parser.error(str(error))
    if not args.base_url:
        parser.error("--base-url is required")
    key = os.environ.get("MEMORYBENCH_GATEWAY_KEY")
    if not key:
        parser.error("set MEMORYBENCH_GATEWAY_KEY in the parent process environment")
    if args.max_output_tokens < 0:
        parser.error("max-output-tokens must be nonnegative")
    if saved is None and args.archive is None:
        parser.error("archive is required for a new run")
    output = args.resume or args.output or Path(".runs/agent-cross-session") / uuid4().hex
    jail = WSLJail(args.distro, args.runtime, args.runtime_dependency)
    model = GatewayModel(args.base_url, key, saved["model_alias"] if saved else args.model,
                         saved["max_output_tokens"] if saved else args.max_output_tokens or None)
    if saved:
        result = resume_experiment(output, jail, lambda *_: model)
    else:
        result = experiment(args.archive, output, jail, lambda *_: model,
            agent=agent_id, adapter_spec=factory, tasks=args.tasks, prefix_count=args.prefix_count,
            model_alias=args.model, max_turns=args.max_turns, final_turns=args.final_turns,
            seed=args.seed, max_output_tokens=args.max_output_tokens or None, scenario=args.scenario)
    for _ in range(args.infra_retries):
        if result["complete"]:
            break
        failures = [r for r in result["prefix"] if not r["infrastructure_ok"]]
        failures += [r for p in result["pairs"] for r in p["conditions"].values() if not r["infrastructure_ok"]]
        retryable = ("gateway_transport_error", "gateway_http_429", "gateway_http_500", "gateway_http_502",
                     "gateway_http_503", "gateway_http_504", "incomplete model stream")
        if not failures or any(not any(tag in row.get("infrastructure_error", "") for tag in retryable) for row in failures):
            break
        result = resume_experiment(output, jail, lambda *_: model)
    print(json.dumps({"complete": result["complete"], "artifacts": str(output.resolve())}))
    if not result["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
