from copy import deepcopy
import unittest

from memorybenchmark.game import Game
from memorybenchmark.ga_worker import build_task_document, pin_task_document


class TaskContextTests(unittest.TestCase):
    def setUp(self):
        self.game = Game(scenario="lake-easy")
        self.observation = self.game.start_task("T5")["observation"]

    def test_document_keeps_goals_and_submission_rules_without_experience_or_progress(self):
        o = deepcopy(self.observation)
        o.update(available_tools=[{"id": "SECRET_STOCK"}], history="SECRET_HISTORY",
                 conditions={"weather": "SECRET_WEATHER"}, future_task="SECRET_FUTURE")
        o["objective"]["targets"][0]["recorded"] = "SECRET_PROGRESS"
        o["map"]["private"] = "SECRET_MAP"
        o["recovery"]["history"] = ["SECRET_RECOVERY"]
        document = build_task_document(o)
        self.assertIn("委托：T5", document)
        self.assertIn("本次测绘目标：西岸缓坡 P2", document)
        self.assertIn("允许提交的营地：苇湾营地 C0", document)
        self.assertIn("到达目标不等于已完成委托", document)
        self.assertNotIn("SECRET_", document)
        self.assertNotIn("grip_kit", document)

    def test_sibling_conditions_do_not_leak_ids_or_memory_labels_into_task_document(self):
        sibling = deepcopy(self.observation)
        sibling.update(task_run_id="different-sibling-run", condition="clear")
        self.assertEqual(build_task_document(sibling), build_task_document(self.observation))
        legacy = Game().start_task("T1")["observation"]
        self.assertNotIn("允许提交的营地", build_task_document(legacy))

    def test_task_is_reintroduced_when_all_old_task_messages_have_been_trimmed(self):
        document = build_task_document(self.observation)
        # Only the latest tool result survives; the original task is absent.
        payload = {"input": [{"type": "function_call_output", "call_id": "move-42",
                              "output": "latest result only"}],
                   "tools": [{"type": "function", "name": "file_patch"}],
                   "reasoning": {"effort": "low"}}
        before = deepcopy(payload)
        result = pin_task_document(payload, document)
        self.assertEqual(payload, before)
        self.assertEqual(result["input"][1:], before["input"])
        self.assertEqual(result["tools"], before["tools"])
        self.assertEqual(result["reasoning"], before["reasoning"])
        self.assertIn("P2", result["input"][0]["content"][0]["text"])
        self.assertIn("/agent/temp/current_task.md", result["input"][0]["content"][0]["text"])

    def test_final_phase_preserves_native_memory_prompt_and_marks_task_as_closed(self):
        native = {"role": "developer", "content": [{"type": "input_text", "text": "native memory SOP"}]}
        result = pin_task_document({"input": [native]}, build_task_document(self.observation), finalizing=True)
        self.assertEqual(result["input"][1], native)
        self.assertIn("委托已结束", result["input"][0]["content"][0]["text"])
        self.assertIn("禁止继续游戏操作", result["input"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
