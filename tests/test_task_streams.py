"""Exposure equality, conditional isolation and the long-gap authoring contract."""
from collections import Counter
import unittest
from scripts.task_streams import four_exposure_tasks, exposure_diagnostics


class TaskStreamTests(unittest.TestCase):
    def test_declared_difficulty_sizes_and_balanced_exposures(self):
        for materials, requirements, targets, expected in ((8,None,8,16),
                (12,None,12,24),(12,('catalogue','verify'),16,48),
                (16,('catalogue','verify'),16,64)):
            kinds=[f'k{i}' for i in range(materials)]
            tasks=four_exposure_tasks(kinds,[f'P{i}' for i in range(targets)],
                requirements=requirements,order_seed=761105,target_seed=7,
                max_steps=352,name='test',minimum_repeat_gap=12 if expected==64 else 0)
            self.assertEqual(len(tasks),expected)
            for task in tasks.values():
                self.assertEqual(len(task['stages']),2)
                self.assertNotEqual(task['stages'][0]['target'],task['stages'][1]['target'])
                for key,value in task['stages'][0].items():self.assertEqual(task[key],value)
            stats=exposure_diagnostics(tasks)
            self.assertEqual(set(stats['context_exposures'].values()),{4})
            self.assertEqual(len(Counter(s['target'] for t in tasks.values() for s in t['stages'])),targets)
            if expected==64:self.assertGreaterEqual(stats['minimum_repeat_gap_tasks'],12)

    def test_repeated_builds_are_identical_and_impossible_gaps_fail(self):
        args=dict(requirements=('catalogue','verify'),order_seed=42,target_seed=43,max_steps=352,name='test')
        self.assertEqual(four_exposure_tasks(['a','b'],['P','Q'],**args),
                         four_exposure_tasks(['a','b'],['P','Q'],**args))
        with self.assertRaisesRegex(ValueError,'infeasible'):
            four_exposure_tasks(['a','b'],['P','Q'],minimum_repeat_gap=12,**args)
