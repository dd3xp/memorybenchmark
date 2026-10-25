from copy import deepcopy
import unittest

from memorybenchmark.prototypes.station_analysis import analyze_trace
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN


class StationAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design(DEFAULT_DESIGN)

    def test_equal_walk_and_success_can_hide_extra_queries(self):
        traces = []
        for extra in (False, True):
            game = StationGame("omega_00", self.design)
            game.start_task("T1")
            for n in ("J", "P", "J", "A"):
                game.step({"type": "move", "target": n})
            if extra:
                game.step({"type": "inspect"})
                game.step({"type": "inspect"})
            game.step({"type": "process"})
            for n in ("J", "C"):
                game.step({"type": "move", "target": n})
            game.step({"type": "submit"})
            traces.append(analyze_trace(self.design, game.events, game.task_run_id))
        self.assertTrue(all(t["success"] for t in traces))
        self.assertEqual(traces[0]["path"], traces[1]["path"])
        self.assertEqual(traces[0]["distance"], traces[1]["distance"])
        self.assertEqual(traces[1]["within_session_repeated_queries"], 1)
        self.assertEqual(traces[0]["query_count"], 0)

    def test_relevant_history_is_distinct_from_total_information(self):
        for task_id, relevant in (("T2", True), ("T3", False)):
            game = StationGame("omega_00", self.design)
            game.start_task("T1")
            for n in ("J", "A"):
                game.step({"type": "move", "target": n})
            game.step({"type": "inspect"})
            game.step({"type": "abandon"})
            game.start_task(task_id)
            game.step({"type": "abandon"})
            measured = analyze_trace(self.design, game.events, game.task_run_id)
            self.assertEqual(measured["prior_compatible_world_count"], 2)
            self.assertEqual(measured["prior_relevant_exposure"], relevant)
            self.assertIsNone(measured["successful_distance_excess"])

    def test_exploratory_wrong_station_is_not_a_history_contradiction(self):
        game = StationGame("omega_11", self.design)
        game.start_task("T1")
        for n in ("J", "P", "J", "A"):
            game.step({"type": "move", "target": n})
        game.step({"type": "process"})
        game.step({"type": "process"})
        game.step({"type": "move", "target": "J"})
        game.step({"type": "abandon"})
        measured = analyze_trace(self.design, game.events, game.task_run_id)
        self.assertEqual(measured["unsupported_processing_count"], 2)
        self.assertEqual(measured["history_contradicting_processing_count"], 1)
        self.assertEqual(measured["historical_new_bits"], 1)
        self.assertEqual(measured["station_excursions"][0]["distance"], 4)


if __name__ == "__main__":
    unittest.main()
