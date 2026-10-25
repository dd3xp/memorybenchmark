from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.prototypes.station_capability import (
    ReferencePlanner, StationGame, compatible_worlds, load_design, replay_policy,
)


DESIGN = Path(__file__).resolve().parents[1] / "design" / "station_capability_v2.json"


def query_and_abandon(game, task, station):
    game.start_task(task)
    for node in ("J", station):
        game.step({"type": "move", "target": node})
    game.step({"type": "inspect"})
    game.step({"type": "abandon"})


class IndependentExperienceTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design(DESIGN)

    def test_world_generator_covers_independent_assignments_without_public_leaks(self):
        worlds = self.design["private_worlds"]
        self.assertEqual(len(worlds), 4)
        self.assertEqual({(w["A"], w["D"]) for w in worlds.values()},
                         {("profile", "bearing"), ("profile", "elevation"), ("shore", "bearing"), ("shore", "elevation")})
        initial = [StationGame(w, self.design).start_task("T1") for w in worlds]
        self.assertTrue(all(response == initial[0] for response in initial))

    def test_two_actual_queries_reduce_four_candidates_in_two_separate_steps(self):
        game = StationGame("omega_00", self.design)
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 4)
        query_and_abandon(game, "T1", "A")
        first = compatible_worlds(self.design, game.events)
        self.assertEqual(len(first), 2)
        self.assertEqual({self.design["private_worlds"][w]["D"] for w in first}, {"bearing", "elevation"})
        query_and_abandon(game, "T3", "D")
        self.assertEqual(compatible_worlds(self.design, game.events), ("omega_00",))

    def test_equal_candidate_counts_do_not_mean_equal_value_for_current_task(self):
        ab, de = StationGame("omega_00", self.design), StationGame("omega_00", self.design)
        query_and_abandon(ab, "T1", "A")
        query_and_abandon(de, "T3", "D")
        first, second = compatible_worlds(self.design, ab.events), compatible_worlds(self.design, de.events)
        self.assertEqual(len(first), len(second))
        for task, expected in (("T2", (8, 10)), ("T5", (10, 8))):
            planner = ReferencePlanner(self.design, task)
            self.assertEqual((planner.initial(first).distance, planner.initial(second).distance), expected)

    def test_success_in_one_family_does_not_supply_unvisited_family_truth(self):
        for world in self.design["private_worlds"]:
            game = StationGame(world, self.design)
            game.start_task("T1")
            replay_policy(game, ReferencePlanner(self.design, "T1"), tuple(self.design["private_worlds"]))
            self.assertTrue(game.state.success)
            self.assertEqual(len(compatible_worlds(self.design, game.events)), 2)
            seen = {e["delivered"]["feedback"].get("station") for e in game.events
                    if e["delivered"]["feedback"]["kind"] == "station_information"}
            self.assertTrue(seen.issubset({"A", "B"}))

    def test_ordinary_task_can_discover_other_family_before_its_related_commission(self):
        game = StationGame("omega_10", self.design)
        game.start_task("T1")
        for node in ("J", "D"):
            game.step({"type": "move", "target": node})
        game.step({"type": "inspect"})
        replay_policy(game, ReferencePlanner(self.design, "T1"), compatible_worlds(self.design, game.events))
        self.assertTrue(game.state.success)
        self.assertEqual(compatible_worlds(self.design, game.events), ("omega_10",))
        self.assertLessEqual(game.steps, 16)

    def test_failed_uninformative_history_does_not_lock_a_later_task(self):
        game = StationGame("omega_11", self.design)
        game.start_task("T1")
        for node in ("J", "A"):
            game.step({"type": "move", "target": node})
        game.step({"type": "abandon"})
        self.assertEqual(len(compatible_worlds(self.design, game.events)), 4)
        game.start_task("T5")
        self.assertFalse(game.state.raw)
        replay_policy(game, ReferencePlanner(self.design, "T5"), compatible_worlds(self.design, game.events))
        self.assertTrue(game.state.success)

    def test_loader_rejects_nonindependent_or_ambiguous_world_families(self):
        invalid = []
        missing = deepcopy(self.design)
        missing["private_worlds"].pop("omega_11")
        invalid.append(missing)
        crossed = deepcopy(self.design)
        crossed["private_worlds"]["omega_00"]["A"] = "bearing"
        invalid.append(crossed)
        duplicated = deepcopy(self.design)
        duplicated["public"]["capability_groups"]["AB"]["stations"].append("A")
        invalid.append(duplicated)
        with tempfile.TemporaryDirectory() as directory:
            for index, design in enumerate(invalid):
                path = Path(directory) / f"invalid-{index}.json"
                path.write_text(json.dumps(design), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_design(path)


if __name__ == "__main__":
    unittest.main()
