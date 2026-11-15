"""Exercise the actual per-submove gate, not only the public route schema."""

import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.agent_bridge import GameTool
from memorybenchmark.decision_gate import DecisionGate, movement_action_policy
from memorybenchmark.prototypes.station_pilot import (
    StationNativeSessions,
    movement_tool,
)
from scripts.check_ga_single_action import check_boundaries
from memorybenchmark.transport_status import publish_status, read_status
from unittest.mock import patch


class RouteHostPolicyTests(unittest.TestCase):
    def test_equal_windows_clock_ticks_preserve_status_publication_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport-status.json"
            with patch(
                "memorybenchmark.transport_status.time.time_ns", return_value=123
            ):
                publish_status(path, {"kind": "request_started"})
                publish_status(path, {"kind": "request_completed"})
            self.assertEqual(read_status(path)["kind"], "request_completed")

    def test_one_native_route_reaches_all_three_host_submoves(self):
        executed = []
        gate = DecisionGate(movement_action_policy("route"))
        gate.begin_response(1)

        def rpc(request):
            if not gate.claim(request):
                return gate.rejected()
            executed.append(request["action"]["target"])
            return {"observation": {"done": False}, "feedback": {}}

        tool = GameTool(
            rpc, definition=movement_tool("route"), target_actions=("move",)
        )
        result = tool({"action": "move", "path": ["A", "B", "C"]})
        self.assertEqual(executed, ["A", "B", "C"])
        self.assertEqual(result["batch"]["executed"], 3)
        self.assertEqual(gate.rejections, 0)

    def test_route_session_selects_batch_and_rejects_incompatible_explicit_gate(self):
        session = StationNativeSessions(
            "source",
            "support",
            None,
            agent="hermes",
            game_access="native",
            movement_mode="route",
            model_alias="fixture",
            game_transport="legacy-rpc",
        )
        self.assertEqual(session.action_policy, "batch")
        with self.assertRaisesRegex(ValueError, "batch host"):
            StationNativeSessions(
                "source",
                "support",
                None,
                agent="hermes",
                game_access="native",
                movement_mode="route",
                action_policy="single",
                model_alias="fixture",
                game_transport="legacy-rpc",
            )
        self.assertEqual(movement_action_policy("step"), "single")

    def test_peer_audit_honors_the_frozen_batch_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            rows = [{"kind": "request", "method": "model", "params": {}}]
            rows += [
                {"kind": "request", "method": "game", "params": {"command": "action"}}
            ] * 3
            (folder / "audit.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
            )
            self.assertEqual(
                check_boundaries(folder, "batch")["rejected_extra_actions"], 0
            )
            with self.assertRaises(AssertionError):
                check_boundaries(folder, "single")
