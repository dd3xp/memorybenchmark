import argparse
import json
import os
from pathlib import Path
import sys

from .adapters import GameAdapter
from .analysis import commute_graph, diagnose
from .game import Game, ProtocolError
from .server import make_server


def main():
    parser = argparse.ArgumentParser(description="制图游戏最小原型")
    parser.add_argument("--stdio", action="store_true", help="JSON Lines 文字接口")
    parser.add_argument("--scenario", choices=("valley", "river"), default="valley")
    parser.add_argument("--analyze", type=Path, help="分析评测侧 events.jsonl")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-dir", type=Path, default=Path(".runs"))
    parser.add_argument("--watch-dir",type=Path,help="experiment directory shown on the read-only dashboard")
    parser.add_argument("--auth-file", type=Path, default=os.environ.get("MEMORYBENCH_AUTH_FILE"),
                        help="private salted PIN verifier; required when exposing the web service")
    parser.add_argument("--local-http-cookie", action="store_true", help="allow login cookies over local development HTTP")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.analyze:
        events = [json.loads(line) for line in args.analyze.read_text(encoding="utf-8").splitlines() if line.strip()]
        runs = [e["task_run_id"] for e in events if e["kind"] == "task_started"]
        print(json.dumps([{"graph": commute_graph(events, run), "diagnostics": diagnose(events, run)}
                          for run in runs], ensure_ascii=False, indent=2))
    elif args.stdio:
        from uuid import uuid4
        sys.stdin.reconfigure(encoding="utf-8")
        game = Game(log_path=args.log_dir / uuid4().hex / "events.jsonl", scenario=args.scenario)
        adapter = GameAdapter(game)
        for line in sys.stdin:
            try:
                response = adapter.dispatch(json.loads(line))
            except (ProtocolError, ValueError, TypeError) as e:
                response = {"error": "protocol_error", "message": str(e)}
            print(json.dumps(response, ensure_ascii=False), flush=True)
    else:
        auth_file = args.auth_file
        if auth_file is None and (args.log_dir / "web-auth.json").exists():
            auth_file = args.log_dir / "web-auth.json"
        server = make_server(port=args.port, log_root=args.log_dir,watch_root=args.watch_dir,
                             auth_file=auth_file, secure_cookie=not args.local_http_cookie)
        print(f"制图游戏已启动：http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
