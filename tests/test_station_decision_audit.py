import unittest

from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_choice import station_decisions
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN
from scripts.audit_station_decisions import align_tools


class DecisionAuditTests(unittest.TestCase):
    def setUp(self):
        self.game = StationGame('omega_5000', load_design(EASY20_CHOICE_DESIGN))
        self.game.start_task('T1')
        self.game.step({'type': 'move', 'target': 'J'})
        self.messages = [
            {'kind': 'request', 'method': 'game', 'params': {'command': 'action', 'action': {'type': 'move', 'target': 'JN'}}},
            {'kind': 'request', 'method': 'game', 'params': {'command': 'action', 'action': {'type': 'move', 'target': 'J'}}},
            {'kind': 'request', 'method': 'task_end'},
        ]

    def test_illegal_request_is_retained_without_becoming_a_graph_edge(self):
        g = self.game
        result = align_tools(g.events, g.task_run_id, self.messages, station_decisions(g.design, g.events, g.task_run_id))
        self.assertEqual(result['rejected_native_game_requests'], [{'type': 'move', 'target': 'JN'}])
        self.assertIsNone(result['before_first_postcollection_station'])

    def test_missing_legal_request_cannot_be_silently_skipped(self):
        g = self.game
        with self.assertRaises(ValueError):
            align_tools(g.events, g.task_run_id, self.messages[:1] + self.messages[2:],
                        station_decisions(g.design, g.events, g.task_run_id))

    def test_post_terminal_request_cannot_become_an_executed_edge(self):
        g = self.game
        final_request = {'kind': 'request', 'method': 'game', 'params': {'command': 'action', 'action': {'type': 'move', 'target': 'JN'}}}
        result = align_tools(g.events, g.task_run_id, self.messages + [final_request],
                             station_decisions(g.design, g.events, g.task_run_id))
        self.assertEqual(result['rejected_native_game_requests'], [{'type': 'move', 'target': 'JN'}] * 2)


if __name__ == '__main__':
    unittest.main()
