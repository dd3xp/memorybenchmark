"""Live UI projections read public game deliveries without exposing native data."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
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

    def test_high_runs_are_distinguishable_from_legacy_low_runs(self):
        self.pilot.update(action_policy="single", reasoning_effort="high")
        self.save()
        header = self.store.listing()[0]
        self.assertEqual(header["agent"], "GA · high")
        self.assertEqual(header["reasoning_effort"], "high")

    def test_map_identity_is_public_cached_and_refreshes_when_design_changes(self):
        from memorybenchmark import pilot_watch
        actual_read = pilot_watch.read_json
        reads = []
        design_path = (self.run / "design.json").resolve()
        def record(path, *args, **kwargs):
            if Path(path).resolve() == design_path:
                reads.append(path)
            return actual_read(path, *args, **kwargs)
        with patch.object(pilot_watch, "read_json", side_effect=record):
            first = self.store.listing()
            second = self.store.listing()
            self.assertEqual(len(reads), 1)
            self.assertEqual(first[0]["name"], second[0]["name"])
            self.assertNotIn("private-world-sentinel", json.dumps(first))
            self.design["public"]["name"] = "Changed public map name"
            (self.run / "design.json").write_text(json.dumps(self.design), encoding="utf-8")
            self.assertEqual(self.store.listing()[0]["name"], "Changed public map name")
            self.assertEqual(len(reads), 2)

    def test_independent_listing_uses_latest_ledger_without_projecting_all_sessions(self):
        self.pilot.update(experiment_mode="independent", memory_condition="retain")
        self.save()
        (self.folder / "transport-attempts.jsonl").write_text(json.dumps({
            "utc": "2099-01-01T00:00:00Z", "kind": "network_retry", "attempt": 3, "reason": "gateway_http_502"})+'\n')
        with patch.object(self.store, "_sessions", side_effect=AssertionError("Full session projection is not needed for a header")):
            header=self.store.listing()[0]
        self.assertEqual(header["status"], "network_retry")

    def test_independent_clear_counts_its_explicit_task_list_without_legacy_flag(self):
        for count in (16, 24, 48, 64):
            with self.subTest(tasks=count):
                self.pilot.update(experiment_mode="independent", memory_condition="clear",
                                  tasks=[f"T{i}" for i in range(1, count+1)])
                self.pilot.pop("clear_first_task", None)
                self.pilot["sessions"] = [
                    {"name": f"{i:02}-T{i}-clear", "task_id": f"T{i}", "condition": "clear",
                     "infrastructure_ok": True, "success": True}
                    for i in range(1, count)]
                self.save()
                header = self.store.listing()[0]
                self.assertEqual(header["total_sessions"], count)
                self.assertEqual(header["completed_sessions"], count-1)
                self.assertEqual(header["status"], "running")

    def test_legacy_paired_clear_still_excludes_shared_first_task(self):
        self.pilot.update(tasks=[f"T{i}" for i in range(1, 25)])
        self.save()
        rows = {row["condition"]: row for row in self.store.listing()}
        self.assertEqual(rows["retain"]["total_sessions"], 24)
        self.assertEqual(rows["clear"]["total_sessions"], 23)

    def test_counterpart_identity_survives_independent_driver_restart_dates(self):
        identities = []
        for condition in ("retain", "clear"):
            folder = self.private / ("easy20-fixture-" + condition + "-20261105") / "runtime-hermes/.runs" / ("pilot-hermes-" + condition + "-map-20261105")
            folder.mkdir(parents=True)
            (folder / "design.json").write_text(json.dumps(self.design), encoding="utf-8")
            identities.append(self.store._map_header(folder)["comparison_key"])
        self.assertEqual(*identities)
        self.assertNotIn(str(self.private), identities[0])

    def test_easy16_model_pairs_are_discovered_independently_without_exposing_private_data(self):
        roots = []
        for model in ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"):
            for condition in ("retain", "clear"):
                folder = (self.private / f"easy16-{model}-hermes-capulin-{condition}-20261108"
                          / "runtime-hermes/.runs" / f"pilot-hermes-{condition}-capulin-easy-{model}-20261108")
                folder.mkdir(parents=True)
                pilot = {**self.pilot, "agent": "hermes", "model_alias": model,
                         "experiment_mode": "independent", "memory_condition": condition,
                         "tasks": [f"T{i}" for i in range(1, 17)]}
                (folder / "pilot.json").write_text(json.dumps(pilot), encoding="utf-8")
                (folder / "design.json").write_text(json.dumps(self.design), encoding="utf-8")
                roots.append(folder)
        before = {p: sha256(p.read_bytes()).hexdigest() for root in roots
                  for p in root.rglob("*") if p.is_file()}
        rows = [row for row in self.store.listing() if row["model"].startswith("gemini-")]
        self.assertEqual(len(rows), 4)
        pairs = {}
        for row in rows:
            self.assertEqual(row["total_sessions"], 16)
            pairs.setdefault(row["model"], {})[row["condition"]] = row["comparison_key"]
        for pair in pairs.values():
            self.assertEqual(set(pair), {"retain", "clear"})
            self.assertEqual(pair["retain"], pair["clear"])
        self.assertNotEqual(pairs["gemini-3.5-flash-lite"]["retain"],
                            pairs["gemini-3.1-flash-lite"]["retain"])
        public = json.dumps(rows)
        for private in (str(self.private), "private-key-sentinel", "private-world-sentinel", "private-source"):
            self.assertNotIn(private, public)
        hidden = rows[0]["experiment_id"]
        (self.private / ".pilot-watch-hidden.json").write_text(json.dumps({"schema": 1, "hidden_experiments": [hidden]}))
        visible = [row for row in self.store.listing() if row["model"].startswith("gemini-")]
        self.assertEqual(len(visible), 3)
        with self.assertRaises(ValueError):
            self.store.snapshot(hidden)
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for root in roots
                                  for p in root.rglob("*") if p.is_file()})

    def test_hidden_experiments_leave_evidence_unchanged_and_cannot_be_selected(self):
        identifier = self.store.listing()[0]["experiment_id"]
        before = {p: sha256(p.read_bytes()).hexdigest() for p in self.run.rglob("*") if p.is_file()}
        policy = self.private / ".pilot-watch-hidden.json"
        policy.write_text(json.dumps({"schema": 1, "hidden_experiments": [identifier, "../../private"]}))
        self.assertEqual(self.store.listing(), [])
        with self.assertRaises(ValueError):
            self.store.snapshot(identifier)
        self.assertEqual(before, {p: sha256(p.read_bytes()).hexdigest() for p in self.run.rglob("*") if p.is_file()})
        for invalid in ("{", '{"schema":2,"hidden_experiments":[]}', '{"schema":1,"hidden_experiments":null}'):
            policy.write_text(invalid)
            self.assertEqual(len(self.store.listing()), 2)

    def infra_handoff_fixture(self):
        self.pilot.update(status="interrupted", experiment_mode="independent", memory_condition="retain")
        self.save()
        experiment = self.run.parent.parent.parent
        base = experiment / "infra-repair-v1"
        base.mkdir()
        launch = {"started_at": "2026-11-06T01:00:00Z", "pid": 123}
        marker = {"session": "02-T2-retain", "token": "private-token-sentinel",
                  "created_utc": "2026-11-06T01:01:00+00:00", "driver_started": launch}
        future = self.run / "sessions" / marker["session"]
        future.mkdir()
        (future / ".infra-transport-handoff.json").write_text(json.dumps(marker))
        (base / "pending-handoff.json").write_text(json.dumps(marker))
        (experiment / "driver-started.json").write_text(json.dumps(launch))
        exit_record = {"exit_code": 1, "type": "RuntimeError", "utc": "2026-11-06T01:02:00Z",
                       "message": "Unrecorded session directory; inspect before retrying"}
        (experiment / "driver-exit.json").write_text(json.dumps(exit_record))
        return experiment, base, future, launch, exit_record

    def test_infra_handoff_is_maintenance_and_never_a_phantom_session(self):
        experiment, _, _, _, _ = self.infra_handoff_fixture()
        (experiment / "transport-status.json").write_text(json.dumps({
            "utc": "2026-11-06T01:01:30Z", "kind": "needs_attention", "reason": "old-result"}))
        header = self.store.listing()[0]
        self.assertEqual(header["status"], "maintenance")
        self.assertEqual(header["recovery"]["reason"], "task_boundary_verification")
        snapshot = self.store.snapshot(header["id"])
        self.assertEqual(snapshot["session"]["id"], "01-T1-prefix")
        self.assertNotIn("private-token-sentinel", json.dumps(snapshot))
        self.assertNotIn(str(experiment), json.dumps(snapshot))

    def test_infra_handoff_rejects_unknown_errors_partial_folders_and_stale_launches(self):
        experiment, base, future, launch, exit_record = self.infra_handoff_fixture()
        for label, change in (
            ("unknown_error", {"message": "unexpected program error"}),
            ("same_message_wrong_type", {"type": "ValueError"}),
            ("exit_before_marker", {"utc": "2026-11-06T01:00:30Z"}),
        ):
            with self.subTest(label=label):
                (experiment / "driver-exit.json").write_text(json.dumps({**exit_record, **change}))
                self.assertEqual(self.store.listing()[0]["status"], "interrupted")
        (experiment / "driver-exit.json").write_text(json.dumps(exit_record))
        (future / "events.jsonl").write_text("partial evidence")
        self.assertEqual(self.store.listing()[0]["status"], "interrupted")
        (future / "events.jsonl").unlink()
        (experiment / "driver-started.json").write_text(json.dumps({**launch, "pid": 999}))
        self.assertEqual(self.store.listing()[0]["status"], "interrupted")
        (experiment / "driver-started.json").write_text(json.dumps(launch))
        (base / "installation-failed.json").write_text("{}")
        self.assertEqual(self.store.listing()[0]["status"], "interrupted")

    def test_request_recovery_has_a_distinct_public_state_without_provider_bodies(self):
        self.pilot.update(experiment_mode="independent", memory_condition="retain")
        self.save()
        experiment = self.run.parent.parent.parent
        (experiment / "driver-started.json").write_text(json.dumps({"started_at":"2026-11-04T12:00:00Z"}))
        (experiment / "transport-status.json").write_text(json.dumps({
            "utc":"2026-11-04T12:01:00Z", "kind":"network_retry", "attempt":17,
            "reason":"gateway_http_502", "body":"private-upstream-error", "retry_in_seconds":30}))
        header = self.store.listing()[0]
        self.assertEqual(header["status"], "network_retry")
        self.assertEqual(header["recovery"]["attempt"], 17)
        self.assertNotIn("private-upstream-error", json.dumps(header))
        (experiment / "transport-status.json").write_text(json.dumps({
            "utc":"2026-11-04T12:01:00Z", "kind":"needs_attention", "reason":"gateway_http_401"}))
        self.assertEqual(self.store.listing()[0]["status"], "needs_attention")
        # The public CLI stores recovery status directly beside pilot.json;
        # managed deployments store it beside their outer driver instead.
        (experiment / "transport-status.json").replace(self.run / "transport-status.json")
        self.assertEqual(self.store.listing()[0]["status"], "needs_attention")

    def test_previous_driver_exit_does_not_label_current_audit_interrupted(self):
        self.pilot["status"] = "completed"
        self.save()
        experiment = self.run.parent.parent.parent
        (experiment / "driver-started.json").write_text(json.dumps({"started_at":"2026-11-04T12:00:00Z"}))
        (experiment / "driver-exit.json").write_text(json.dumps({"exit_code":1,"utc":"2026-11-04T11:00:00Z"}))
        self.assertEqual(self.store.listing()[0]["status"], "auditing")

    def test_transport_handoff_is_not_a_live_future_session_or_an_unknown_failure(self):
        self.pilot.update(experiment_mode='independent',memory_condition='retain')
        self.save()
        future=self.run/'sessions/02-T2-retain';future.mkdir()
        marker={'session':'02-T2-retain','token':'fixture'}
        (future/'.native-transport-handoff.json').write_text(json.dumps(marker))
        experiment=self.run.parent.parent.parent
        (experiment/'native-policy-v3-pending.json').write_text(json.dumps(marker))
        identifier=self.store.listing()[0]['id']
        self.assertEqual(self.store.snapshot(identifier)['session']['id'],'01-T1-prefix')
        self.pilot['status']='interrupted';self.save()
        path=experiment/'driver-exit.json'
        path.write_text(json.dumps({'message':'Unrecorded session directory; inspect before retrying'}))
        self.assertEqual(self.store.listing()[0]['status'],'maintenance')
        path.write_text(json.dumps({'message':'different unexpected error'}))
        self.assertEqual(self.store.listing()[0]['status'],'interrupted')

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

    def test_reserved_handoff_directory_is_not_a_running_session(self):
        guard = self.run / "sessions/01-T1-clear"
        guard.mkdir()
        (guard / ".parallel-handoff.json").write_text('{"token":"planned-handoff"}')
        listing = self.store.listing()
        self.assertEqual(next(r for r in listing if r["condition"] == "clear")["status"], "waiting")
        self.assertEqual([r["id"] for r in self.store._sessions(self.run, self.pilot)], ["01-T1-prefix"])

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

    def test_independent_run_has_one_entry_and_cannot_select_a_phantom_peer(self):
        self.pilot.update(experiment_mode="independent", memory_condition="clear", clear_first_task=True)
        self.save()
        listing = self.store.listing()
        self.assertEqual(len(listing), 1)
        row = listing[0]
        self.assertEqual(row["condition"], "clear")
        self.assertEqual(row["total_sessions"], 20)
        self.assertEqual(row["experiment_mode"], "independent")
        # Between its own tasks an independent owner is still running; there
        # is no peer condition whose completion it could be waiting for.
        self.assertEqual(row["status"], "running")
        self.assertEqual(self.store.snapshot(row["experiment_id"])["condition"], "clear")
        with self.assertRaises(ValueError):
            self.store.snapshot(row["experiment_id"] + "-retain")

    def test_map_catalog_geometry_excludes_experience_answers_and_unknown_paths(self):
        maps = map_listing()
        self.assertEqual({m['id'] for m in maps}, {'capulin-easy','forest-easy','cascade-easy','nessie-normal','dingo-normal','boar-normal','orcia-hard','hampi-hard','angkor-hard','scandinavia-lunatic','mongolia-lunatic','andes-lunatic'})
        self.assertEqual([m['id'] for m in maps if m['current']],['capulin-easy'])
        for row in maps:
            data = map_detail(row["id"])
            self.assertEqual(len(data["map"]["locations"]), row["node_count"])
            self.assertNotIn("private_worlds", json.dumps(data))
            self.assertNotIn("capabilities", data)
            self.assertTrue(data["materials"])
            self.assertTrue(all(isinstance(kind, str) for kind in data["materials"]))
        self.assertGreater(map_detail("capulin-easy")["node_count"], 20)
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
            for route in ("/experiments", "/maps", "/play", "/play?map=forest-easy", "/play?map=nessie-normal", "/long-lake-normal-terrain.svg", "/site.css", "/atlas-view.js", "/select.js", "/select.css", "/atlas-chinese.woff2", "/atlas-serif.woff2", "/atlas-sans.woff2", "/cottage-icons.svg", "/botanical-sprig.svg"):
                with get(route) as response:
                    self.assertEqual(response.status, 200)
            with get("/api/experiments/runs") as response:
                self.assertEqual(len(json.load(response)["runs"]), 2)
            for map_id in ("capulin-easy", "forest-easy", "cascade-easy", "nessie-normal", "dingo-normal", "boar-normal"):
                with urlopen(Request(base + "/api/field/start?map=" + map_id, data=b"{}", headers={"Cookie": cookie, "Content-Type": "application/json"})) as response:
                    result = json.load(response)
                    self.assertEqual(result["task_index"], 1)
                    self.assertTrue(result["observation"]["environment"]["name"])
                    self.assertNotIn("private_worlds", json.dumps(result))
                with get("/api/field/design?map=" + map_id + "&instance_id=" + result["instance_id"]) as response:
                    self.assertTrue(json.load(response)["tasks"])
            for map_id in ("nessie-easy", "easy20", "linked20", "capability-v1", "lake-easy", "unknown"):
                with self.assertRaises(HTTPError) as missing:
                    get("/api/maps/detail?id="+map_id)
                self.assertEqual(missing.exception.code,404)
                with self.assertRaises(HTTPError) as missing:
                    get("/play?map="+map_id)
                self.assertEqual(missing.exception.code,404)
            with self.assertRaises(HTTPError):
                get("/api/experiments/run?id=../../private")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
