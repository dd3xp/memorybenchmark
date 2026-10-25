"""An unfinished native response must not end an environment task."""
import unittest

from memorybenchmark.ga_worker import ModelBudgetExhausted, run_environment_task
from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_session import DEFAULT_DESIGN, StationSession


class ContinuationTests(unittest.TestCase):
    def run_fixture(self, plans, *, budget=40):
        game = StationGame("omega_01", load_design(DEFAULT_DESIGN))
        session = StationSession(game, "T2")
        calls, prompts, limits, emissions = [], [], [], []
        responses = iter(plans)

        def native(prompt, remaining):
            prompts.append(prompt)
            limits.append(remaining)
            for action in next(responses):
                calls.append(action)
                if action is not None:
                    game.step(action)
                yield "native response"
            return {"result": "CURRENT_TASK_DONE"}

        result = run_environment_task(native, lambda: session.dispatch({"command": "read"}),
            lambda: len(calls), lambda kind, **kw: emissions.append((kind, kw)),
            initial_text=session.initial["text"], max_turns=budget)
        return game, result, prompts, limits, emissions

    def test_unsupported_processing_then_plain_plan_resumes_and_submits(self):
        move = lambda n: {"type": "move", "target": n}
        first = [move(n) for n in ("J", "Q", "J", "A")] + [{"type": "process"}, None]
        second = [move(n) for n in ("J", "B")] + [{"type": "process"}] + [move(n) for n in ("J", "C")] + [{"type": "submit"}, None]
        game, result, prompts, limits, emissions = self.run_fixture([first, second])
        self.assertTrue(game.state.success)
        self.assertEqual(limits, [40, 34])
        self.assertIn("当前位置：A", prompts[1])
        self.assertNotIn("B 支持", prompts[1])
        self.assertEqual(len([e for e in emissions if e[0] == "continuation"]), 1)
        self.assertEqual(game.steps, 11)  # No host-generated actions or edges.
        self.assertFalse(any(e["kind"] == "runner_terminated" for e in game.events))

    def test_repeated_plain_responses_exhaust_one_shared_budget(self):
        game, result, prompts, limits, emissions = self.run_fixture([[None]] * 3, budget=3)
        self.assertEqual(limits, [3, 2, 1])
        self.assertEqual(result["result"], "MAX_TURNS_EXCEEDED")
        self.assertFalse(game.done)  # Only the host records the terminal event.
        self.assertEqual(game.steps, 0)
        self.assertEqual(len(game.events), 1)

    def test_explicit_abandon_is_terminal_without_continuation(self):
        game, result, prompts, limits, emissions = self.run_fixture([[{"type": "abandon"}, None]])
        self.assertTrue(game.done)
        self.assertFalse(game.state.success)
        self.assertEqual(len(prompts), 1)

    def test_budget_signal_escapes_native_exception_retries(self):
        calls = [1]
        def native(prompt, remaining):
            calls.append(1)
            try:
                raise ModelBudgetExhausted()
            except Exception:
                self.fail("budget stop must not be retried as a transport/tool failure")
            yield
        result = run_environment_task(native, lambda: {"observation": {"done": False}},
            lambda: len(calls), lambda *a, **kw: None, initial_text="task", max_turns=2)
        self.assertEqual(result["result"], "MAX_TURNS_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
