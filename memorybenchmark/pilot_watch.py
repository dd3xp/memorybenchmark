"""Read-only UI projections of frozen station pilots, including live deliveries.

Only explicitly configured roots are scanned. The web representation contains
public geography, task state and aggregate progress, never prompts, native
memory bodies, private worlds, source paths or credentials.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import threading


def read_json(path, limit=64 * 1024**2):
    if path.stat().st_size > limit:
        raise ValueError("记录过大。")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def public_deliveries(folder):
    path = folder / "game-deliveries.jsonl"
    if path.is_file():
        if path.stat().st_size > 16 * 1024**2:
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                yield json.loads(line)
            except ValueError:
                continue
        return
    # Older frozen pilots predate delivery logs; replay only their selected
    # task's authoritative public events, not the cumulative prior history.
    path, graph = folder / "events.jsonl", folder / "graph.json"
    if not path.is_file() or not graph.is_file() or path.stat().st_size > 32 * 1024**2:
        return
    run_id = read_json(graph).get("task_run_id")
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("task_run_id") == run_id and "delivered" in event:
            yield {"request": {"action": event.get("action", {})}, "response": event["delivered"]}


def safe_directory(path, root):
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            return False
        return all(not part.is_symlink() and not getattr(part, "is_junction", lambda: False)()
                   for part in (path, *path.parents) if part.is_relative_to(root))
    except (OSError, ValueError):
        return False


class PilotStore:
    def __init__(self, log_root, private_root=None):
        self.log_root = Path(log_root).resolve()
        configured = private_root or os.environ.get("MEMORYBENCH_PILOT_ROOT")
        self.private_root = Path(configured).resolve() if configured else Path(__file__).resolve().parents[1].with_name("memorybenchmark-private")
        self._cache = {}
        self._lock = threading.RLock()

    def _runs(self):
        candidates = []
        for root, pattern in ((self.log_root, "*/pilot.json"),
                              (self.private_root, "easy20-*/runtime-*/.runs/pilot-*/pilot.json")):
            if not root.is_dir():
                continue
            for path in root.glob(pattern):
                if safe_directory(path.parent, root):
                    identifier = "pilot-" + sha256(str(path.parent).encode()).hexdigest()[:16]
                    candidates.append((identifier, path.parent))
        return dict(candidates)

    def _pilot(self, root):
        path = root / "pilot.json"
        signature = (path.stat().st_mtime_ns, path.stat().st_size)
        with self._lock:
            previous = self._cache.get(str(path))
            if previous is None or previous[0] != signature:
                raw = read_json(path)
                fields = ("agent", "model_alias", "status", "game_access", "action_policy", "tasks")
                compact = {key: raw[key] for key in fields if key in raw}
                session_fields = ("name", "task_id", "condition", "infrastructure_ok", "success", "game_actions", "distance", "llm_calls")
                compact["sessions"] = [{key: row[key] for key in session_fields if key in row}
                                       for row in raw.get("sessions", [])]
                compact["attempt_history"] = [None] * len(raw.get("attempt_history", []))
                self._cache[str(path)] = (signature, compact)
            return self._cache[str(path)][1]

    def _sessions(self, root, pilot):
        recorded = {row["name"]: row for row in pilot.get("sessions", [])}
        result = []
        directory = root / "sessions"
        folders = sorted(directory.iterdir()) if directory.is_dir() else []
        for folder in folders[:100]:
            if not re.fullmatch(r"\d{2,3}-T\d+-(prefix|retain|clear)", folder.name) or not safe_directory(folder, root):
                continue
            row = recorded.get(folder.name, {})
            condition = folder.name.rsplit("-", 1)[1]
            item = {"id": folder.name, "task_id": folder.name.split("-")[1], "condition": condition,
                    "status": "complete" if row.get("infrastructure_ok") else "error" if row else "running",
                    "success": row.get("success"), "operations": row.get("game_actions"),
                    "distance": row.get("distance"), "calls": row.get("llm_calls", 0)}
            result.append(item)
        order = {"prefix": 0, "retain": 1, "clear": 2}
        return sorted(result, key=lambda item: (int(item["task_id"][1:]), order[item["condition"]]))

    def _header(self, identifier, root, pilot):
        valid = [row for row in pilot.get("sessions", []) if row.get("infrastructure_ok")]
        main = [row for row in valid if row["condition"] != "clear"]
        clear = [row for row in valid if row["condition"] == "clear"]
        tasks = len(pilot.get("tasks", []))
        status = pilot.get("status", "interrupted")
        # Frozen directories are runtime/.runs/pilot-name.
        experiment = root.parent.parent.parent
        result_path = experiment / "result.json"
        if pilot.get("status") == "completed":
            status = "complete" if result_path.is_file() else "auditing"
            if (experiment / "driver-exit.json").is_file() and read_json(experiment / "driver-exit.json").get("exit_code"):
                status = "audit_error"
        started = iso(root.stat().st_ctime)
        if (experiment / "driver-started.json").is_file():
            started = read_json(experiment / "driver-started.json").get("started_at", started)
        elif (experiment / "run-plan.json").is_file():
            started = read_json(experiment / "run-plan.json").get("created_at_utc", started)
        label = {"ga": "GA", "hermes": "Hermes"}.get(pilot.get("agent"), "Agent")
        if pilot.get("action_policy") == "single":
            label += " · 逐步"
        return {"id": identifier, "agent": label,
                "model": pilot.get("model_alias", ""), "status": status, "started_at": started,
                "updated_at": iso((root / "pilot.json").stat().st_mtime),
                "main_completed": len(main), "main_total": tasks, "clear_completed": len(clear),
                "clear_total": max(0, tasks - 1), "completed_sessions": len(valid),
                "total_sessions": max(0, 2 * tasks - 1), "successes": sum(row.get("success") is True for row in valid),
                "failed_attempts": len(pilot.get("attempt_history", [])),
                "interface": "native" if pilot.get("game_access") == "native" else "bridge"}

    def listing(self):
        rows = []
        for identifier, root in self._runs().items():
            try:
                rows.append(self._header(identifier, root, self._pilot(root)))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(rows, key=lambda row: (row["status"] == "running", row["started_at"]), reverse=True)[:60]

    def snapshot(self, identifier, session_id=None):
        if not isinstance(identifier, str) or not re.fullmatch(r"pilot-[0-9a-f]{16}", identifier):
            raise ValueError("实验不存在。")
        root = self._runs().get(identifier)
        if root is None:
            raise ValueError("实验不存在。")
        pilot = self._pilot(root)
        sessions = self._sessions(root, pilot)
        if session_id is None:
            active = [row for row in sessions if row["status"] == "running"]
            session = (active or sessions)[-1] if sessions else None
        else:
            session = next((row for row in sessions if row["id"] == session_id), None)
            if session is None:
                raise ValueError("任务会话不存在。")
        design = read_json(root / "design.json")
        public = design["public"]
        header = self._header(identifier, root, pilot)
        response = {**header, "name": public["name"], "sessions": sessions, "session": session,
                    "map": {"locations": deepcopy(public["locations"]), "edges": deepcopy(public["edges"]),
                            "view_box": public.get("view_box", [0, 0, 1200, 900])},
                    "terrain": "field", "frames": []}
        if session is None:
            return response
        folder = root / "sessions" / session["id"]
        frames = response["frames"]
        previous_revision = None
        if folder.is_dir():
            # A writer can leave its final line incomplete between flushes.
            for delivery in public_deliveries(folder):
                observation = delivery.get("response", {}).get("observation")
                if not observation:
                    continue
                revision = (observation.get("revision", observation.get("steps")), observation.get("done"), observation.get("success"))
                if previous_revision == revision:
                    continue
                previous_revision = revision
                task = observation.get("task", {})
                frame = {key: observation[key] for key in ("location", "steps", "distance", "done", "success", "raw", "processed", "stage_index", "stage_count", "stages_completed") if key in observation}
                frame["task"] = {key: task[key] for key in ("id", "name", "target", "required_kind", "max_steps") if key in task}
                action = (delivery.get("request") or {}).get("action", {})
                frame["action"] = {key: action[key] for key in ("type", "target") if key in action}
                feedback = delivery.get("response", {}).get("feedback", {})
                if not isinstance(feedback, dict):
                    feedback = {}
                frame["feedback"] = {key: feedback[key] for key in ("kind", "station", "capability", "result", "raw_collected", "next_stage") if key in feedback}
                frames.append(frame)
        model = folder / "model"
        requests = list(model.glob("*-request.json")) if model.is_dir() else []
        session["calls"] = len(requests) or session["calls"]
        if requests:
            response["updated_at"] = iso(max(path.stat().st_mtime for path in requests))
        if frames:
            current = frames[-1]
            session["phase"] = "整理记忆" if current.get("done") and session["status"] == "running" else "执行任务"
            session["location"] = current["location"]
            session["operations"] = current.get("steps", 0)
            session["distance"] = current.get("distance", 0)
        response["kinds"] = deepcopy(public.get("kinds", {}))
        return response
