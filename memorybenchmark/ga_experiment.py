"""Compatibility entry point for the bundled native GenericAgent adapter."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from .agent_sessions import WorkerSessions
from .errors import InfrastructureError
from .ga_runtime import WSLJail
from .ga_worker import PROMPT_PROTOCOL
from .mcp_game import GAME_TRANSPORT
from .model_gateway import GatewayModel


class NativeGASessions(WorkerSessions):
    def __init__(self, *args, prompt_protocol=PROMPT_PROTOCOL, game_transport=None, **kwargs):
        if game_transport is None:
            game_transport = GAME_TRANSPORT if prompt_protocol == PROMPT_PROTOCOL else "legacy-rpc"
        super().__init__(*args, prompt_protocol=prompt_protocol, game_transport=game_transport,
                         worker_protocol="ga-session-1", worker_filename="ga_worker.py", **kwargs)

    def task_config(self, initial):
        config = super().task_config(initial)
        if self.prompt_protocol not in ("cartography-native-memory-2", PROMPT_PROTOCOL):
            config.pop("task_observation")
        return config


def experiment(*args, **kwargs):
    from .experiment import experiment as run
    return run(*args, agent="ga", **kwargs)


def resume_experiment(*args, **kwargs):
    from .experiment import resume_experiment as resume
    return resume(*args, **kwargs)


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
