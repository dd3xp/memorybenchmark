"""Live UI projections read public game deliveries without exposing native data."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from memorybenchmark.map_catalog import map_detail, map_listing
from memorybenchmark.pilot_watch import PilotStore
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_session import EASY20_REUSE_DESIGN, StationSession
from memorybenchmark.server import make_server
from memorybenchmark.web_auth import save_pin


class PilotWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.private = self.base / "private"
        self.run = self.private / "easy20-fixture/runtime-ga/.runs/pilot-fixture"
        self.folder = self.run / "sessions/01-T1-prefix"
        (self.folder / "model").mkdir(parents=True)
        self.design = load_design(EASY20_REUSE_DESIGN)
        (self.run / "design.json").write_text(json.dumps(self.design), encoding="utf-8")
        self.pilot = {"agent": "ga", "model_alias": "fixture", "status": "running", "game_access": "native",
                      "world": "private-world-sentinel", "tasks": list(self.design["tasks"]), "sessions": [],
                      "api_key": "private-key-sentinel", "implementation_sha256": {"private/path": "private-source"}}
        self.save()
        self.entries = []
        self.game = StationGame("omega_15_05", self.design)
        self.session = StationSession(self.game, "T1", feedback_mode="compact",
                                      on_delivery=lambda request, response: self.entries.append({"request": request, "response": response}))
        for i, node in enumerate(("J", "JN")):
            self.session.dispatch({"command": "action", "request_id": str(i), "action": {"type": "move", "target": node}})
        self.write_deliveries()
        (self.folder / "model/001-request.json").write_text('{"instructions":"private-prompt-sentinel"}', encoding="utf-8")
        self.store = PilotStore(self.base / "logs", self.private)

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.run / "pilot.json").write_text(json.dumps(self.pilot), encoding="utf-8")

    def write_deliveries(self):
        (self.folder / "game-deliveries.jsonl").write_text("".join(json.dumps(row) + "\n" for row in self.entries), encoding="utf-8")

    def test_active_location_trace_and_partial_line_are_read_only_and_public(self):
        self.pilot["action_policy"] = "single"
        self.save()
        path = self.folder / "game-deliveries.jsonl"
        with path.open("a", encoding="utf-8") as output:
            output.write('{"request":')
        before = {p: sha256(p.read_bytes()).hexdigest() for p in self.run.rglob("*") if p.is_file()}
        listing = self.store.listing()
        self.assertEqual(listing[0]["agent"], "GA")
        data = self.store.snapshot(listing[0]["id"])
        self.assertEqual(data["session"]["location"], "JN")
        self.assertEqual([frame["location"] for frame in data["frames"]], ["C", "J", "JN"])
        self.assertEqual(data["session"]["calls"], 1)
        self.assertEqual(data["total_sessions"], 20)
        self.assertEqual(data["condition"], "retain")
        public = json.dumps(data)
        for secret in ("private_worlds", "private-world-sentinel", "private-key-sentinel", "private/path", "private-prompt-sentinel"):
            self.assertNotIn(secret, public)
        # ISO timestamps can contain "T20" at 20:00 UTC. Check actual task
        # fields rather than unrelated substrings in the serialized payload.
        self.assertEqual([row["task_id"] for row in data["sessions"]], ["T1"])
        self.assertTrue(all(frame["task"]["id"] == "T1" for frame in data["frames"]))
        self.assertNotIn("tasks", data)
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in self.run.rglob("*") if p.is_file()})

    def test_completed_branches_and_current_selection_are_separate(self):
        row = {"name": "01-T1-prefix", "condition": "prefix", "task_id": "T1", "infrastructure_ok": True,
               "success": True, "game_actions": 12, "distance": 14, "llm_calls": 8}
        self.pilot["sessions"] = [row]
        other = self.run / "sessions/02-T2-retain"
        other.mkdir()
        self.save()
        identifier = self.store.listing()[0]["id"]
        current = self.store.snapshot(identifier)
        self.assertEqual(current["completed_sessions"], 1)
        self.assertEqual(current["session"]["id"], "02-T2-retain")
        prior = self.store.snapshot(identifier, "01-T1-prefix")
        self.assertEqual(prior["session"]["status"], "complete")
        self.assertEqual(prior["session"]["location"], "JN")
        with self.assertRaises(ValueError):
            self.store.snapshot(identifier, "../../model/001-request.json")
        self.pilot["status"] = "completed"
        self.save()
        self.assertEqual(self.store.listing()[0]["status"], "auditing")
        (self.run.parent.parent.parent / "result.json").write_text("{}")
        self.assertEqual(self.store.listing()[0]["status"], "complete")

    def test_condition_runs_have_independent_progress_and_session_selection(self):
        self.pilot["clear_first_task"] = True
        self.pilot["sessions"] = [{"name":"01-T1-prefix", "condition":"prefix", "task_id":"T1",
                                   "infrastructure_ok":True, "success":True, "game_actions":2, "distance":2, "llm_calls":1}]
        clear = self.run / "sessions/01-T1-clear"
        clear.mkdir()
        (clear / "game-deliveries.jsonl").write_text(json.dumps({"response":{"observation":{"location":"C", "steps":0, "distance":0}}}) + "\n")
        self.save()
        listing = self.store.listing()
        self.assertEqual(len(listing), 2)
        retained, cleared = listing
        self.assertEqual([row["total_sessions"] for row in listing], [20, 20])
        self.assertEqual([row["completed_sessions"] for row in listing], [1, 0])
        self.assertEqual([row["status"] for row in listing], ["waiting", "running"])
        a, b = self.store.snapshot(retained["id"]), self.store.snapshot(cleared["id"])
        self.assertEqual(a["session"]["id"], "01-T1-prefix")
        self.assertEqual(b["session"]["id"], "01-T1-clear")
        self.assertEqual([row["id"] for row in b["sessions"]], ["01-T1-clear"])
        self.assertEqual(b["frames"][0]["location"], "C")
        with self.assertRaises(ValueError):
            self.store.snapshot(cleared["id"], "01-T1-prefix")
        self.assertEqual(self.store.snapshot(retained["experiment_id"])["id"], retained["id"])
        self.pilot.pop("clear_first_task")
        self.save()
        self.assertEqual([row["total_sessions"] for row in self.store.listing()], [20, 19])

    def test_older_event_logs_replay_only_the_selected_task(self):
        (self.folder / "game-deliveries.jsonl").unlink()
        events = [{"task_run_id": "prior-task", "delivered": {"observation": {"location": "private-prior-sentinel"}}}, *self.game.events]
        (self.folder / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        (self.folder / "graph.json").write_text(json.dumps({"task_run_id": self.game.task_run_id}), encoding="utf-8")
        data = self.store.snapshot(self.store.listing()[0]["id"])
        self.assertEqual([frame["location"] for frame in data["frames"]], ["C", "J", "JN"])
        self.assertNotIn("private-prior-sentinel", json.dumps(data))

    def test_map_catalog_geometry_excludes_experience_answers_and_unknown_paths(self):
        maps = map_listing()
        self.assertEqual(len(maps), 9)
        for row in maps:
            data = map_detail(row["id"])
            self.assertEqual(len(data["map"]["locations"]), row["node_count"])
            self.assertNotIn("private_worlds", json.dumps(data))
            self.assertNotIn("capabilities", data)
        self.assertEqual(map_detail("easy20")["node_count"], 70)
        with self.assertRaises(ValueError):
            map_detail("../station_easy20_reuse.json")

    def test_http_dashboard_routes_auth_and_multiple_play_maps(self):
        auth = self.base / "auth.json"
        save_pin(auth, "019827")
        server = make_server(port=0, log_root=self.base / "play", pilot_root=self.private,
                             auth_file=auth, secure_cookie=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            for route in ("/api/experiments/runs", "/api/maps"):
                with self.assertRaises(HTTPError) as error:
                    urlopen(base + route)
                self.assertEqual(error.exception.code, 401)
            with urlopen(Request(base + "/login", data=b'{"pin":"019827"}', headers={"Content-Type": "application/json"})) as response:
                cookie = response.headers["Set-Cookie"].split(";", 1)[0]
            def get(route):
                return urlopen(Request(base + route, headers={"Cookie": cookie}))
            for route in ("/experiments", "/maps", "/play", "/play?map=linked20", "/site.css", "/atlas-view.js", "/select.js", "/select.css"):
                with get(route) as response:
                    self.assertEqual(response.status, 200)
            with get("/api/experiments/runs") as response:
                self.assertEqual(len(json.load(response)["runs"]), 2)
            for map_id in ("easy20", "station20", "choice20", "linked20", "capability-v1", "capability-v2"):
                with urlopen(Request(base + "/api/field/start?map=" + map_id, data=b"{}", headers={"Cookie": cookie, "Content-Type": "application/json"})) as response:
                    result = json.load(response)
                    self.assertEqual(result["task_index"], 1)
                    self.assertTrue(result["observation"]["environment"]["name"])
                    self.assertNotIn("private_worlds", json.dumps(result))
                with get("/api/field/design?map=" + map_id + "&instance_id=" + result["instance_id"]) as response:
                    self.assertTrue(json.load(response)["tasks"])
            with self.assertRaises(HTTPError):
                get("/api/experiments/run?id=../../private")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
