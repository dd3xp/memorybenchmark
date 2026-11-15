"""Verify native GA/Hermes progress preservation with synthetic SSE only."""
from memorybenchmark.audit_records import read_audit
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time
from uuid import uuid4

from memorybenchmark.agent_adapters import load_adapter
from memorybenchmark.map_catalog import CURRENT_MAP, station_design
from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_pilot import StationNativeSessions
from memorybenchmark.recovery_runtime import RecoveryJail, install
from memorybenchmark.request_recovery import RecoveringGatewayModel, RequestFailure
from memorybenchmark.response_stream import SpoolLines
from scripts.check_station_native_sessions import ScriptedResponses, response_observations


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    prepared = load_adapter(args.agent).prepare(args.archive, output)
    install()
    jail = RecoveryJail(args.distro, args.runtime, args.runtime_dependency,
                        recovery_root=output / "request-recovery")
    sessions = StationNativeSessions(prepared.source, prepared.support, jail,
        agent=args.agent, feedback_mode="compact", game_access="native", action_policy="single",
        movement_mode="step", model_alias="fixture", max_turns=20, final_turns=2,
        wall_seconds=180, reasoning_effort="high")
    probe = sessions.probe(prepared.baseline, output / "probe")
    design = load_design(station_design(CURRENT_MAP))
    game = StationGame(map_world(design), design)
    start = design["tasks"]["T1"]["start"]
    target = next(b if a == start else a for a,b,w in design["public"]["edges"] if start in (a,b))
    marker = "synthetic_recovery_progress_" + uuid4().hex
    write = (("code_run", {"type":"python", "script":
        "from pathlib import Path; Path('../memory/recovery-fixture.txt').write_text("+repr(marker)+")"})
        if args.agent == "ga" else
        ("memory", {"target":"memory", "operations":[{"action":"add", "content":marker}]}))
    scripted = ScriptedResponses([("game_action", {"action":"move", "target":target}),
                                  write, ("game_action", {"action":"abandon"})], args.agent, "native")
    model = RecoveringGatewayModel("https://fixture.invalid", "synthetic-no-credential", "fixture", None,
                                   jitter=lambda a,b:0)
    injected = []
    failed_hash = None
    def attempt(body):
        nonlocal failed_hash
        payload = json.loads(body)
        observations = list(response_observations(payload.get("input", [])))
        after_move = any(o["observation"].get("location") == target for o in observations)
        if after_move and payload.get("tools") and len(injected)<3:
            identity = sha256(body).hexdigest()
            if failed_hash is None:
                failed_hash = identity
            assert identity == failed_hash, "Retry changed the native request"
            injected.append({"request_sha256":identity, "lease_id":jail.control.name,
                             "game_steps":game.steps, "distance":game.distance, "events":len(game.events)})
            if len(injected)<3:
                time.sleep(getattr(args,'fault_wait_seconds',0))
                raise RequestFailure("gateway_http_502", retryable=True, body="synthetic transient error")
        result = scripted(payload)
        padding_mib = getattr(args, 'stream_padding_mib', 0)
        if padding_mib:
            path = model.output / 'synthetic-model-streams' / f'{scripted.calls:03d}.sse'
            path.parent.mkdir(exist_ok=True)
            with path.open('wb') as stream:
                padding = b': ' + b'x' * 8190 + b'\n\n'
                for _ in range((padding_mib * 1024**2 + len(padding)-1)//len(padding)):
                    stream.write(padding)
                for line in result['lines']: stream.write((line+'\n').encode('utf-8'))
            digest=sha256();line_count=0
            with path.open('rb') as stream:
                for raw in stream:digest.update(raw);line_count+=1
            result={'lines':SpoolLines(path,size=path.stat().st_size,digest=digest.hexdigest(),line_count=line_count)}
        return result, {"input_tokens":1,"output_tokens":1,"total_tokens":2}
    model._attempt = attempt
    result = sessions.run(game, "T1", prepared.baseline, output / "session", model, condition="retain")
    assert result["infrastructure_ok"], result
    assert len(injected)==3 and all(entry == injected[0] for entry in injected), injected
    moves = [e for e in game.events if e.get("kind")=="action" and e.get("action",{}).get("type")=="move"]
    assert len(moves)==1, "A delivered move was replayed"
    assert any(marker in p.read_text(encoding="utf-8", errors="replace") for p in
               (output / "session/memory-after").rglob("*") if p.is_file()), "Native memory write was lost"
    audit = read_audit(output / "session")
    assert sum(e.get("kind")=="session" for e in audit)==1
    calls = list((output / "session/model").glob("*-request.json"))
    assert len(calls)==result["llm_calls"]==scripted.calls
    if getattr(args, 'stream_padding_mib', 0):
        assert result['initial_session']['transport_protocol']=='rpc-sse-chunks-1'
    summary = {"passed":True,"agent":args.agent,"native_archive_sha256":sha256(args.archive.read_bytes()).hexdigest(),
        "synthetic_response_padding_mib_per_call":getattr(args,'stream_padding_mib',0),
        "real_model_calls":0,"faults_injected":2,"same_worker_lease":True,"native_sessions":1,
        "same_request_bytes":True,"delivered_moves":len(moves),"native_memory_write_preserved":True,
        "logical_model_calls":result["llm_calls"],"physical_attempts":result["llm_calls"]+2,
        "injected_attempts":injected,"isolation":probe["worker_result"]["isolation"]}
    (output / "validation.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary),flush=True)
    return summary


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent",choices=("ga","hermes"),required=True)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--distro",default="Ubuntu")
    parser.add_argument("--runtime",required=True)
    parser.add_argument("--runtime-dependency",action="append",default=[])
    parser.add_argument("--fault-wait-seconds",type=float,default=0,
                        help="Synthetic outage duration before each injected failure; no gateway requests")
    parser.add_argument("--stream-padding-mib",type=int,default=0,
                        help="Synthetic SSE comments per response; validate large streams with native clients and zero model calls")
    run(parser.parse_args())
