from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.analysis import commute_graph, diagnose
from memorybenchmark.calibrate import calibrate, common_history
from memorybenchmark.game import Game, ProtocolError
from memorybenchmark.server import make_server


class GameTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="river")
        self.adapter = GameAdapter(self.game)
        self.first = self.adapter.dispatch({"command": "start", "task_id": "T1"})

    def test_local_observation_does_not_reveal_rule_or_map(self):
        obs = self.first["observation"]
        self.assertEqual({n["id"] for n in obs["map"]["nodes"]}, {"S", "J"})
        self.assertEqual([n["target"] for n in obs["neighbors"]], ["J"])
        self.assertNotIn("无法通行", self.first["text"])
        self.assertEqual(self.game.evidence, [])
        self.assertNotIn("evidence", obs)

    def test_blocked_crossing_delivers_evidence_without_commute(self):
        self.adapter.action("move", "J")
        self.adapter.action("move", "F")
        # The unsafe move remains available; the legal-action list is not an oracle.
        self.assertIn("R", [n["target"] for n in self.game.observation()["neighbors"]])
        before = self.game.clock
        result = self.adapter.action("move", "R")
        self.assertEqual(result["outcome"], "blocked")
        self.assertFalse(result["observation"]["done"])
        self.assertEqual(self.game.position, "F")
        self.assertEqual(self.game.clock, before + 1)
        self.assertIn("雨夜", result["feedback"])
        self.assertEqual(len(self.game.evidence), 1)
        self.assertEqual(len(commute_graph(self.game.events, self.game.task_run_id)["edges"]), 2)
        self.assertEqual(diagnose(self.game.events, self.game.task_run_id)["repeated_block_events"], [])

    def test_request_replay_is_idempotent_and_conflicts_do_not_mutate(self):
        request = {"command": "action", "action": {"type": "move", "target": "J"},
                   "request_id": "move-1", "expected_revision": self.game.revision}
        result = self.adapter.dispatch(request)
        snapshot = self.game.snapshot()
        self.assertEqual(self.adapter.dispatch(request), result)
        self.assertEqual(self.game.snapshot(), snapshot)
        with self.assertRaises(ProtocolError):
            self.adapter.dispatch({**request, "action": {"type": "move", "target": "F"}})
        self.assertEqual(self.game.snapshot(), snapshot)

    def test_stale_version_and_invalid_schema_are_not_executed(self):
        snapshot = self.game.snapshot()
        for action, version in [({"type": "move", "target": "J"}, -1),
                                ({"type": "teleport", "target": "K"}, self.game.revision),
                                ({"type": "move", "target": "J", "extra": 1}, self.game.revision)]:
            with self.assertRaises(ProtocolError):
                self.game.step(action, request_id="bad", expected_revision=version)
            self.assertEqual(self.game.snapshot(), snapshot)

    def test_budget_failure_keeps_evidence_and_new_task_clears_public_map(self):
        self.adapter.action("move", "J")
        self.adapter.action("move", "F")
        self.adapter.action("move", "R")
        self.game.max_steps = self.game.steps + 1
        self.adapter.action("wait")
        self.assertTrue(self.game.done)
        self.assertFalse(self.game.success)
        self.assertEqual(len(self.game.evidence), 1)
        self.adapter.dispatch({"command": "start", "task_id": "T2"})
        self.assertEqual(self.game.max_steps, 40)
        self.assertEqual({n["id"] for n in self.game.observation()["map"]["nodes"]}, {"S", "J"})
        self.assertEqual(len(self.game.evidence), 1)

    def test_repeated_commutes_preserve_order_and_multiplicity(self):
        for target in ("J", "F", "J", "F", "J"):
            self.adapter.action("move", target)
        graph = commute_graph(self.game.events, self.game.task_run_id)
        pairs = [(e["source"], e["target"]) for e in graph["edges"]]
        self.assertEqual(pairs.count(("J", "F")), 2)
        self.assertEqual(pairs.count(("F", "J")), 2)
        self.assertEqual([e["order"] for e in graph["edges"]], list(range(5)))
        self.assertEqual(len({e["id"] for e in graph["edges"]}), 5)

    def test_weather_and_nonmovement_are_replayable(self):
        snapshot = self.game.snapshot()
        self.adapter.action("observe")
        self.adapter.action("wait")
        expected = self.game.snapshot()
        self.game.restore(snapshot)
        self.adapter.action("observe")
        self.adapter.action("wait")
        # Request IDs are transport-generated; compare game events and state.
        self.assertEqual(self.game.events, expected["events"])
        self.assertEqual(self.game.clock, expected["clock"])
        self.assertEqual(commute_graph(self.game.events, self.game.task_run_id)["edges"], [])

    def test_changed_weather_does_not_count_as_repeated_block(self):
        game = Game()
        game.restore(common_history())
        game.clock = 120
        adapter = GameAdapter(game)
        adapter.dispatch({"command": "start", "task_id": "T2"})
        for target in ("J", "F", "R"):
            result = adapter.action("move", target)
        self.assertEqual(game.position, "R")
        self.assertEqual(result["outcome"], "ok")
        self.assertEqual(diagnose(game.events, game.task_run_id)["repeated_block_events"], [])

    def test_equal_success_and_move_cost_have_distinct_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            results = calibrate(Path(directory))
        a, b = results["new_exploration"], results["repeated_block"]
        self.assertEqual((a["success"], a["moves"], a["distance"]), (True, 5, 8))
        self.assertEqual((b["success"], b["moves"], b["distance"]), (True, 5, 8))
        self.assertEqual(a["diagnostics"]["excursions"][0]["kind"], "return_with_new_location")
        self.assertEqual(b["diagnostics"]["excursions"][0]["kind"], "return_with_repeated_block")
        self.assertEqual(len(b["diagnostics"]["repeated_block_events"]), 1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = make_server(port=0, log_root=Path(self.directory.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def post(self, path, data):
        request = Request(self.root + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_human_and_agent_transport_observations_match(self):
        web = self.post("/api/start", {"task_id": "T1"})
        agent = GameAdapter(Game())
        local = agent.dispatch({"command": "start", "task_id": "T1"})
        self.assertEqual(web["text"], local["text"])
        web = self.post("/api/action", {"instance_id": web["instance_id"], "request_id": "one",
                        "action": {"type": "move", "target": "J"}, "expected_revision": web["observation"]["revision"]})
        local = agent.action("move", "J")
        a, b = deepcopy(web["observation"]), deepcopy(local["observation"])
        a.pop("task_run_id"); b.pop("task_run_id")
        self.assertEqual(a, b)
        self.assertEqual(web["text"], local["text"])

    def test_private_paths_not_served_and_instances_are_isolated(self):
        a = self.post("/api/start", {"task_id": "T1"})
        b = self.post("/api/start", {"task_id": "T1"})
        self.post("/api/action", {"instance_id": a["instance_id"], "request_id": "one", "action": {"type": "move", "target": "J"}})
        with urlopen(self.root + "/api/observation?instance_id=" + b["instance_id"]) as response:
            self.assertEqual(json.load(response)["observation"]["location"]["id"], "S")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.root + "/.runs/anything/events.jsonl")
        self.assertEqual(error.exception.code, 404)

    def test_lake_shared_geography_reaches_human_and_agent_transport(self):
        response=self.post('/api/start',{'scenario':'lake-easy','task_id':'T1'})
        token=response['instance_id']
        adapter=GameAdapter(Game(scenario='lake-easy'))
        local=adapter.dispatch({'command':'start','task_id':'T1'})
        self.assertEqual(response['text'],local['text'])
        self.assertNotIn('atlas',response)
        for index,target in enumerate(('E1','E2','P1','C1')):
            response=self.post('/api/action',{'instance_id':token,'request_id':str(index),
                                            'action':{'type':'move','target':target}})
        response=self.post('/api/action',{'instance_id':token,'request_id':'submit','action':{'type':'submit'}})
        self.assertTrue(response['observation']['success'])
        with urlopen(self.root+'/api/atlas?instance_id='+token) as r:
            self.assertIn('P1',json.load(r)['surveyed'])
        next_task=self.post('/api/start',{'instance_id':token,'task_id':'T2'})
        self.assertNotIn('P1',next_task['observation']['map']['surveyed'])
        self.assertIn('P1',next_task['observation']['map']['charted'])
        self.assertIn('P1',next_task['text'])
        with urlopen(self.root+'/api/tasks?scenario=loch-ness') as r:
            data=json.load(r)
            self.assertEqual(len(data['tasks']),8)
            self.assertEqual(data['scenario'],'lake-easy')
        for path in ('/maps.js','/lake.svg','/play.css'):
            with urlopen(self.root+path) as r:
                self.assertEqual(r.status,200)


if __name__ == "__main__":
    unittest.main()
