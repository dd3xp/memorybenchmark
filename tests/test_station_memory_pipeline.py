"""Protect semantic evidence boundaries in the retrospective memory audit."""
import unittest

from scripts.audit_linked_memory_pipeline import game_outputs, in_payload, match_facts, parsed_outputs, response_game_actions


class MemoryPipelineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.patterns = {"facts": [
            {"station": "D", "capability": "bearing",
             "alternatives": [["阶段1方位资料处理成功", "在 D 处理后直接前往 U"]]},
            {"station": "F", "capability": "lithology",
             "alternatives": [["F 站处理岩性资料成功"]]},
        ]}

    def test_route_and_success_do_not_establish_capability(self):
        self.assertEqual(match_facts("方位任务成功；从 F 经 D 返回 C。", self.patterns), {})

    def test_disconnected_entries_do_not_form_a_fact(self):
        text = "阶段1方位资料处理成功\n§\n另一次在 D 处理后直接前往 U"
        self.assertEqual(match_facts(text, self.patterns), {})
        same_entry = "阶段1方位资料处理成功；先到 R，在 D 处理后直接前往 U。"
        self.assertIn("D", match_facts(same_entry, self.patterns))

    def test_written_fact_requires_literal_delivery(self):
        fact = match_facts("F 站处理岩性资料成功", self.patterns)["F"]
        self.assertFalse(in_payload(fact, {"input": [{"role": "user", "content": "去 F 站处理岩性。"}]}))
        self.assertTrue(in_payload(fact, {"input": [{"role": "developer", "content": "F 站处理岩性资料成功"}]}))

    def test_nested_game_outputs_include_inspect_without_result(self):
        item = {"observation": {"steps": 4}, "feedback": {"kind": "station_information", "station": "F", "capability": "lithology"}}
        import json
        payload = {"input": [
            {"type": "function_call", "name": "tool_call", "call_id": "c", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "c", "output": json.dumps({"results": [item]})},
            {"type": "message", "role": "assistant", "content": "station_information"},
        ]}
        outputs = list(parsed_outputs(payload))
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0][1]["name"], "tool_call")
        self.assertEqual(list(game_outputs(outputs[0][2])), [item])

    def test_decision_attribution_checks_the_emitted_action(self):
        import json
        item = {"type": "function_call", "call_id": "a", "name": "tool_call", "arguments": json.dumps({"calls": [
            {"name": "game_action", "arguments": {"action": "move", "target": "fp1"}},
            {"name": "game_action", "arguments": {"action": "process"}},
        ]})}
        response = {"lines": [
            "data: " + json.dumps({"type": "response.output_item.done", "item": item}),
            "data: " + json.dumps({"type": "response.completed", "response": {"output": [item]}}),
            "data: [DONE]",
        ]}
        self.assertEqual(response_game_actions(response), [
            {"action": "move", "target": "fp1"}, {"action": "process"}])
        item["arguments"] = json.dumps({"name": "game_action", "arguments": {"action": "process"}})
        self.assertEqual(response_game_actions({"lines": ["data: " + json.dumps({
            "type": "response.output_item.done", "item": item})]}), [{"action": "process"}])


if __name__ == "__main__":
    unittest.main()
