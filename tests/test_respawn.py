from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.analysis import commute_graph, diagnose
from memorybenchmark.game import Game, ProtocolError
from memorybenchmark.watch import Observer, observer_atlas
from memorybenchmark.validation import validate


def move(adapter, *route):
    result = None
    for node in route:
        result = adapter.action("move", node)
    return result


class RespawnTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="lake-easy")
        self.adapter = GameAdapter(self.game)
        self.initial = self.adapter.dispatch({"command": "start", "task_id": "T2"})

    def fatal_route(self):
        return move(self.adapter, "E1", "E2", "P1", "C1", "N1", "C1", "P1")

    def test_fatal_arrival_and_recovery_are_distinct_ordered_edges(self):
        task_run_id = self.game.task_run_id
        self.game.inventory.add("stream_kit")  # Irrelevant protection must be dropped.
        response = self.fatal_route()
        self.assertEqual(response["outcome"], "respawned")
        self.assertEqual(self.game.task_run_id, task_run_id)
        self.assertEqual((self.game.position, self.game.stamina, self.game.steps), ("C0", 70, 7))
        self.assertFalse(self.game.done)
        self.assertFalse(self.game.inventory)
        self.assertIn("N1", self.game.surveyed)
        self.assertEqual(response["respawn"]["death_observation"]["location"]["id"], "P1")
        self.assertEqual(response["respawn"]["death_observation"]["stamina"], 0)
        self.assertEqual(response["observation"]["location"]["id"], "C0")
        self.assertIn("复活边权重 70", response["text"])
        graph = commute_graph(self.game.events, task_run_id)
        self.assertEqual([(e["source"], e["target"], e["kind"]) for e in graph["edges"][-2:]],
                         [("C1", "P1", "commute"), ("P1", "C0", "respawn")])
        self.assertEqual(graph["distance"], 10)
        self.assertEqual((graph["deaths"], graph["respawn_penalty"], graph["total_weight"]), (1, 70, 80))
        self.assertEqual(len({e["id"] for e in graph["edges"]}), 8)
        self.assertEqual(graph["edges"][-1]["inventory_before"], ["stream_kit"])
        self.assertEqual(self.game.events[-1]["to"], "P1")

    def test_response_retries_and_checkpoint_replay_do_not_duplicate_recovery(self):
        move(self.adapter, "E1", "E2", "P1", "C1", "N1", "C1")
        checkpoint = self.game.snapshot()
        request = {"command": "action", "request_id": "fatal-once", "expected_revision": self.game.revision,
                   "action": {"type": "move", "target": "P1"}}
        response = self.adapter.dispatch(request)
        expected = self.game.snapshot()
        self.assertEqual(self.adapter.dispatch(request), response)
        self.assertEqual(self.game.snapshot(), expected)
        self.game.restore(checkpoint)
        self.assertEqual(self.adapter.dispatch(request), response)
        self.assertEqual(self.game.snapshot(), expected)

    def test_completed_progress_survives_but_respawn_never_becomes_a_map_road(self):
        self.fatal_route()
        self.assertEqual(self.game.observer_atlas()["nodes"], [])
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])
        atlas = self.game.observer_atlas()
        self.assertIn("N1", atlas["surveyed"])
        self.assertNotIn(["C0", "P1"], atlas["edges"])
        self.assertNotIn(["P1", "C0"], atlas["edges"])
        self.assertNotIn("recovery", atlas)
        response = self.adapter.dispatch({"command": "start", "task_id": "T3"})
        self.assertEqual(response["observation"]["recovery"]["history"], [])
        self.assertEqual(response["observation"]["recovery"]["penalty"], 0)

    def test_budget_is_shared_across_lives_and_remains_terminal(self):
        self.game.max_steps = 7
        response = self.fatal_route()
        self.assertEqual(response["outcome"], "budget_exhausted")
        self.assertTrue(self.game.done)
        self.assertFalse(self.game.success)
        self.assertEqual(self.game.deaths, 1)
        with self.assertRaises(ProtocolError):
            self.adapter.action("wait")

    def test_success_after_preparing_on_second_life_keeps_all_costs(self):
        self.adapter.action("abandon")
        self.adapter.dispatch({"command": "start", "task_id": "T5"})
        move(self.adapter, "E1", "E2", "P1", "C1", "P1")
        self.assertEqual(self.game.position, "C0")
        self.assertNotIn("P2", self.game.surveyed)
        move(self.adapter, "E1", "U1", "D1")
        self.adapter.action("take", "grip_kit")
        move(self.adapter, "U1", "E1", "E2", "P1", "C1", "N1", "P2", "N1", "C1", "P1", "E2", "E1", "C0")
        self.assertTrue(self.adapter.action("submit")["observation"]["success"])
        graph = commute_graph(self.game.events, self.game.task_run_id)
        self.assertEqual(graph["deaths"], 1)
        self.assertEqual(graph["distance"], self.game.distance)
        self.assertEqual(graph["effort"], self.game.effort)
        self.assertEqual(graph["total_weight"], graph["distance"] + 70)
        for a, b in zip(graph["edges"], graph["edges"][1:]):
            self.assertEqual(a["target"], b["source"])
        self.assertTrue(all(e["life"] == 1 for e in graph["edges"] if e["time"] >= self.game.recovery_history[0]["time_after"]))

    def test_respawn_self_loop_is_recorded_even_when_fatal_arrival_is_at_camp(self):
        self.adapter.action("move", "E1")
        self.game.stamina = 1
        response = self.adapter.action("move", "C0")
        self.assertEqual(response["outcome"], "respawned")
        graph = commute_graph(self.game.events, self.game.task_run_id)
        self.assertEqual((graph["edges"][-1]["source"], graph["edges"][-1]["target"]), ("C0", "C0"))
        self.assertEqual(graph["distance"], 4)
        self.assertEqual(len(diagnose(self.game.events, self.game.task_run_id)["respawns"]), 1)

    def test_configurable_weight_and_legacy_non_respawn_world(self):
        self.game.world["respawn"]["weight"] = 111
        self.fatal_route()
        self.assertEqual(commute_graph(self.game.events, self.game.task_run_id)["respawn_penalty"], 111)
        old = Game()
        old_adapter = GameAdapter(old)
        old_adapter.dispatch({"command": "start", "task_id": "T1"})
        old.stamina = 1
        self.assertEqual(old_adapter.action("move", "J")["outcome"], "exhausted")
        self.assertTrue(old.done)
        invalid = deepcopy(self.game.world)
        invalid["respawn"]["weight"] = -1
        with self.assertRaises(ValueError):
            validate(invalid, self.game.tasks)

    def test_watch_preserves_fatal_arrival_without_drawing_a_fake_return_road(self):
        game = Game(scenario="lake-easy")
        game.tasks["T2"].update(goals=["E2"], stamina=3)
        adapter = GameAdapter(game)
        initial = adapter.dispatch({"command": "start", "task_id": "T2"})
        with tempfile.TemporaryDirectory() as directory:
            observer = Observer(Path(directory))
            observer.begin({"agent":"test", "tasks":["T2"], "prefix_count":1})
            sid = observer.open("T2", "prefix", initial, {})
            for target in ("E1", "E2"):
                result = adapter.action("move", target)
                observer.observe(sid, result, {"type":"move", "target":target})
            fatal = observer.data["sessions"][0]["frames"][-1]
            self.assertEqual((fatal["source"], fatal["target"]), ("E1", "E2"))
            self.assertEqual(fatal["observation"]["location"]["id"], "C0")
            self.assertEqual(fatal["respawn"]["weight"], 70)
            observer.observe(sid, adapter.action("observe"), {"type":"observe"})
            stationary = observer.data["sessions"][0]["frames"][-1]
            self.assertFalse(stationary["moved"])
            self.assertEqual(stationary["source"], "C0")
            observer.observe(sid, adapter.action("submit"), {"type":"submit"})
            atlas = observer_atlas(observer.data, sid, 100)
            self.assertEqual(set(atlas["surveyed"]), {"C0", "E1", "E2"})
            self.assertNotIn(["C0", "E2"], atlas["edges"])
            self.assertEqual(diagnose(game.events, game.task_run_id)["excursions"], [])
