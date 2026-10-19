from copy import deepcopy
import unittest

from memorybenchmark.game import Game
from memorybenchmark.ga_worker import build_task_reminder, pin_task_reminder


class TaskContextTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="lake-easy")
        self.observation = self.game.start_task("T5")["observation"]

    def test_reminder_keeps_public_requirements_without_experience_or_progress(self):
        o = deepcopy(self.observation)
        o.update(available_tools=[{"id": "SECRET_STOCK"}], history="SECRET_HISTORY",
                 conditions={"weather": "SECRET_WEATHER"}, future_task="SECRET_FUTURE")
        o["objective"]["targets"][0]["recorded"] = "SECRET_PROGRESS"
        o["map"]["private"] = "SECRET_MAP"
        o["recovery"]["history"] = ["SECRET_RECOVERY"]
        reminder = build_task_reminder(o)
        self.assertIn("当前委托：T5", reminder)
        self.assertIn(o["instruction"], reminder)
        self.assertIn("P2", reminder)
        self.assertIn("C0 提交", reminder)
        self.assertNotIn("SECRET_", reminder)
        self.assertNotIn("grip_kit", reminder)
        self.assertNotIn(".md", reminder)
        self.assertEqual(len(reminder.splitlines()), 2)

    def test_sibling_conditions_do_not_leak_ids_or_memory_labels_into_task_reminder(self):
        sibling = deepcopy(self.observation)
        sibling.update(task_run_id="different-sibling-run", condition="clear")
        self.assertEqual(build_task_reminder(sibling), build_task_reminder(self.observation))
        legacy = Game().start_task("T1")["observation"]
        self.assertIn(legacy["instruction"], build_task_reminder(legacy))

    def test_task_is_reintroduced_when_all_old_task_messages_have_been_trimmed(self):
        reminder = build_task_reminder(self.observation)
        # Only the latest tool result survives; the original task is absent.
        payload = {"input": [{"type": "function_call_output", "call_id": "move-42",
                              "output": "latest result only"}],
                   "tools": [{"type": "function", "name": "file_patch"}],
                   "reasoning": {"effort": "low"}}
        before = deepcopy(payload)
        result = pin_task_reminder(payload, reminder)
        self.assertEqual(payload, before)
        self.assertEqual(result["input"][1:], before["input"])
        self.assertEqual(result["tools"], before["tools"])
        self.assertEqual(result["reasoning"], before["reasoning"])
        self.assertIn("P2", result["input"][0]["content"][0]["text"])
        self.assertNotIn(".md", result["input"][0]["content"][0]["text"])

    def test_final_phase_preserves_native_memory_prompt_and_marks_task_as_closed(self):
        native = {"role": "developer", "content": [{"type": "input_text", "text": "native memory SOP"}]}
        result = pin_task_reminder({"input": [native]}, build_task_reminder(self.observation), finalizing=True)
        self.assertEqual(result["input"][1], native)
        self.assertIn("委托已结束", result["input"][0]["content"][0]["text"])
        self.assertIn("禁止继续游戏操作", result["input"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
