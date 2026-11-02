"""Native review joins use the whole declared task budget, including elapsed time."""
import threading
import unittest

from memorybenchmark.ga_worker import drain_background_reviews


class BackgroundReviewWaitTests(unittest.TestCase):
    def test_a_slow_review_can_finish_after_100_seconds_inside_existing_wall_budget(self):
        seconds, events = [450.0], []
        class Review:
            def is_set(self): return seconds[0] >= 572.0
            def wait(self, timeout): seconds[0] += timeout
        drain_background_reviews([Review()], threading.Lock(), 3595, lambda kind, **kw: events.append((kind, kw)),
                                 clock=lambda: seconds[0])
        self.assertGreaterEqual(seconds[0], 572)
        self.assertEqual([kind for kind, _ in events], ['background_review_wait', 'background_reviews_drained'])
        self.assertAlmostEqual(events[0][1]['remaining_wall_seconds'], 3145)

    def test_wait_does_not_restart_or_extend_the_task_wall_budget(self):
        seconds = [899.8]
        class Review:
            def is_set(self): return False
            def wait(self, timeout): seconds[0] += timeout
        with self.assertRaisesRegex(RuntimeError, 'worker wall budget expired'):
            drain_background_reviews([Review()], threading.Lock(), 900, lambda *a, **kw: None, clock=lambda: seconds[0])
        self.assertAlmostEqual(seconds[0], 900)


if __name__ == '__main__':
    unittest.main()
