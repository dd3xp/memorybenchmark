import copy
import importlib.util
import sys
from pathlib import Path
import unittest

PROJECT = (
    Path("C:/Codes/memorybenchmark")
    if Path("C:/Codes/memorybenchmark").exists()
    else Path("C:/Codes/benchmark")
)
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).parent))
from boundary_continuation import restore
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)


class BoundaryContract(unittest.TestCase):
    def setUp(self):
        self.design = load_design(PROJECT / "memorybenchmark/data/capulin_easy16.json")
        self.world = map_world(self.design)
        self.game = StationGame(self.world, self.design)
        self.game.start_task("T1")
        self.game.step({"type": "abandon"})
        self.summary = {
            "infrastructure_ok": True,
            "done": True,
            "success": False,
            "task_id": "T1",
            "game_actions": self.game.steps,
            "distance": self.game.distance,
        }

    def test_retains_real_game_failure_without_repeating_it(self):
        actual = restore(self.design, self.world, self.game.events, self.summary, 1)
        self.assertTrue(actual.done)
        self.assertFalse(actual.state.success)
        self.assertEqual(actual.events, self.game.events)

    def test_next_task_starts_at_next_run_without_old_actions(self):
        actual = restore(self.design, self.world, self.game.events, self.summary, 1)
        old = copy.deepcopy(actual.events)
        actual.start_task("T2")
        self.assertEqual(actual.events[:-1], old)
        self.assertEqual(actual.task_run_id, "session-2")

    def test_rejects_changed_outcome(self):
        with self.assertRaises(ValueError):
            restore(
                self.design,
                self.world,
                self.game.events,
                {**self.summary, "success": True},
                1,
            )

    def test_rejects_changed_cost(self):
        with self.assertRaises(ValueError):
            restore(
                self.design,
                self.world,
                self.game.events,
                {**self.summary, "distance": 1000},
                1,
            )

    def test_rejects_other_task(self):
        with self.assertRaises(ValueError):
            restore(
                self.design,
                self.world,
                self.game.events,
                {**self.summary, "task_id": "T2"},
                1,
            )

    def test_rejects_uncommitted_infrastructure_failure(self):
        with self.assertRaises(ValueError):
            restore(
                self.design,
                self.world,
                self.game.events,
                {**self.summary, "infrastructure_ok": False},
                1,
            )


if __name__ == "__main__":
    unittest.main()
