"""Read-only calibration summaries must keep request content private."""

import json
from pathlib import Path
import tempfile
import unittest

from operations.inspect_managed_pair import model_pairs, latest_version, last_delivery


class InspectionTests(unittest.TestCase):
    def test_summary_exposes_effort_pairing_but_never_request_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model").mkdir()
            request = {
                "model": "gpt-5.6-luna",
                "reasoning": {"effort": "high"},
                "tools": [{"type": "function", "name": "game_action"}],
                "input": [{"role": "user", "content": "DO_NOT_PRINT_PROMPT"}],
            }
            response = {
                "lines": [
                    "data: "
                    + json.dumps(
                        {
                            "type": "response.completed",
                            "response": {
                                "model": "gpt-5.6-luna",
                                "reasoning": {"effort": "high"},
                            },
                        }
                    )
                ]
            }
            (root / "model/001-request.json").write_text(
                json.dumps(request), encoding="utf-8"
            )
            (root / "model/001-response.json").write_text(
                json.dumps(response), encoding="utf-8"
            )
            rows = model_pairs(root)
            self.assertNotIn("DO_NOT_PRINT_PROMPT", json.dumps(rows))
            self.assertEqual(rows[0]["response_model"], "gpt-5.6-luna")
            self.assertTrue(rows[0]["response_received"])

    def test_incomplete_newest_receipt_does_not_hide_latest_complete_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "001.json").write_text('{"value":1}', encoding="utf-8")
            (root / "002.json").write_text("{", encoding="utf-8")
            self.assertEqual(latest_version(root), {"value": 1})

    def test_delivery_summary_does_not_republish_raw_response_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = {
                "response": {
                    "text": "PRIVATE_TEXT",
                    "observation": {"task": {"id": "T1"}, "location": "A1", "steps": 2},
                    "feedback": {"kind": "arrived"},
                }
            }
            (root / "game-deliveries.jsonl").write_text(
                json.dumps(value) + "\n", encoding="utf-8"
            )
            result = last_delivery(root)
            self.assertEqual(result["location"], "A1")
            self.assertNotIn("PRIVATE_TEXT", json.dumps(result))
