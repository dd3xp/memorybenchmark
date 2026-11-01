import json
import unittest

from scripts.summarize_ga_memory_routing import lookup_flags, response_tools, verify_effort_pair


class GAMemoryRoutingTests(unittest.TestCase):
    def test_streamed_tool_is_counted_when_completed_response_output_is_empty(self):
        response = {"lines": ["data: " + json.dumps(e) for e in (
            {"type": "response.output_item.done", "item": {"type": "function_call", "call_id": "one",
                "name": "file_read", "arguments": '{"path":"../memory/game.md"}'}},
            {"type": "response.completed", "response": {"output": [], "model": "fixture"}})]}
        tools, _ = response_tools(response)
        self.assertEqual(tools, [{"name": "file_read", "arguments": {"path": "../memory/game.md"}}])

    def test_listing_is_lookup_but_does_not_claim_the_body_was_requested(self):
        tools = [{"name": "code_run", "arguments": {"script": "import os; print(os.listdir('../memory'))"}}]
        self.assertEqual(lookup_flags(tools, "game.md"), {"body_read_requested": False,
            "directory_lookup_requested": True, "memory_lookup_started": True})
        self.assertFalse(lookup_flags([{"name": "file_read", "arguments": {"path": "../memory/memory_management_sop.md"}}], "game.md")["body_read_requested"])
        self.assertFalse(lookup_flags([{"name": "code_run", "arguments": {"script": "print(open('../memory/memory_management_sop.md').read())"}}], "game.md")["body_read_requested"])

    def test_effort_comparison_rejects_other_input_changes(self):
        low = {"reasoning": {"effort": "low"}, "input": [{"role": "user", "content": "original"}]}
        high = {**low, "reasoning": {"effort": "high"}}
        verify_effort_pair(low, high)
        with self.assertRaisesRegex(ValueError, "another input field"):
            verify_effort_pair(low, {**high, "input": [{"role": "user", "content": "changed"}]})


if __name__ == "__main__":
    unittest.main()
