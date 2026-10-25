from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from memorybenchmark.prototypes.station_capability import StationGame, load_design
from memorybenchmark.prototypes.station_session import StationSession, serve_stdio


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "design" / "station_capability_v2.json"


class StationSessionTests(unittest.TestCase):
    def setUp(self):
        self.design = load_design(DESIGN)
        self.game = StationGame("omega_00", self.design)
        self.session = StationSession(self.game, "T1")

    def request(self, verb, target=None):
        action = {"type": verb}
        if target is not None:
            action["target"] = target
        return {"command": "action", "request_id": f"request-{self.session.revision}",
                "expected_revision": self.session.revision, "action": action}

    def test_read_is_current_task_only_and_cannot_advance_or_read_private_state(self):
        response = self.session.dispatch({"command": "read"})
        self.assertIn("当前委托 T1", response["text"])
        self.assertNotIn("omega_00", json.dumps(response))
        for command in ("start", "snapshot", "events", "world", "next_task"):
            self.assertIn("error", self.session.dispatch({"command": command}))
        self.assertIn("error", self.session.dispatch({"command": "read", "path": "private_worlds"}))
        self.assertEqual((self.game.task_id, self.game.steps, self.game.clock), ("T1", 0, 0))

    def test_exact_retry_returns_original_public_response_without_a_second_move(self):
        request = self.request("move", "J")
        first = self.session.dispatch(request)
        first["observation"]["location"] = "modified_by_client"
        replay = self.session.dispatch(request)
        self.assertEqual((replay["observation"]["location"], self.game.steps, self.session.revision), ("J", 1, 1))
        changed = deepcopy(request)
        changed["action"]["target"] = "A"
        self.assertEqual(self.session.dispatch(changed)["error"], "request_conflict")

    def test_stale_or_malformed_requests_do_not_consume_game_actions(self):
        request = self.request("move", "J")
        request["expected_revision"] = 3
        self.assertEqual(self.session.dispatch(request)["error"], "stale_revision")
        request["expected_revision"] = False
        self.assertEqual(self.session.dispatch(request)["error"], "invalid_request")
        self.assertIn("error", self.session.dispatch({"command": "action", "action": {"type": "move", "target": "J"}}))
        self.assertEqual((self.game.steps, self.game.distance), (0, 0))

    def test_data_processing_and_terminal_submission_work_through_the_adapter(self):
        for verb, target in (("move", "J"), ("move", "P"), ("move", "J"), ("move", "A"),
                             ("process", None), ("move", "J"), ("move", "C")):
            self.assertNotIn("error", self.session.dispatch(self.request(verb, target)))
        request = self.request("submit")
        result = self.session.dispatch(request)
        self.assertTrue(result["observation"]["success"])
        self.assertEqual(self.session.dispatch(request), result)
        self.assertEqual((self.game.distance, self.game.steps), (8, 8))
        self.assertIn("error", self.session.dispatch(self.request("inspect")))

    def test_new_session_does_not_replay_previous_capability_feedback(self):
        for verb, target in (("move", "J"), ("move", "A"), ("inspect", None), ("abandon", None)):
            self.session.dispatch(self.request(verb, target))
        next_session = StationSession(self.game, "T3")
        self.assertEqual(next_session.revision, 0)
        self.assertEqual(next_session.initial["feedback"], {"kind": "started"})
        self.assertEqual(next_session.requests, {})
        self.assertFalse(next_session.initial["observation"]["raw"])
        self.assertNotIn("station_information", json.dumps(next_session.initial))
        self.assertEqual(self.session.dispatch({"command": "read"})["error"], "session_closed")

    def test_json_lines_recovers_from_bad_json_without_protocol_noise(self):
        output = io.StringIO()
        serve_stdio(self.session, io.StringIO('not json\n{"command":"read"}\n{"command":"snapshot"}\n'), output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertEqual(responses[0]["error"], "invalid_json")
        self.assertEqual(responses[1]["observation"]["task"]["id"], "T1")
        self.assertIn("error", responses[2])
        self.assertEqual(self.game.steps, 0)

    def test_real_stdio_subprocess_outputs_only_public_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "stdio"
            run = subprocess.run([sys.executable, "-m", "memorybenchmark.prototypes.station_session",
                                  "--world", "omega_00", "--task", "T1", "--output", str(output)],
                                 input='{"command":"read"}\n{"command":"start","task_id":"T2"}\n',
                                 text=True, encoding="utf-8", capture_output=True, cwd=ROOT, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            responses = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(len(responses), 2)
            self.assertNotIn("omega_00", run.stdout)
            self.assertIn("error", responses[1])
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["tasks_started"], 1)

    def test_human_entry_can_play_all_eight_commissions_using_the_same_rules(self):
        stations = {"profile": "A", "shore": "B", "bearing": "D", "elevation": "E"}
        commands = []
        for task in self.design["tasks"].values():
            commands.extend(["move J", f'move {task["target"]}', "move J",
                             f'move {stations[task["required_kind"]]}', "process", "move J", "move C", "submit"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "human"
            run = subprocess.run([sys.executable, "-m", "memorybenchmark.prototypes.station_session", "--human",
                                  "--all-tasks", "--world", "omega_00", "--output", str(output)],
                                 input="\n".join(commands) + "\n", text=True, encoding="utf-8", capture_output=True, cwd=ROOT, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["tasks_started"], 8)
            self.assertTrue(summary["success"])
            events = [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(sum(e["delivered"]["feedback"]["kind"] == "submitted" for e in events), 8)


if __name__ == "__main__":
    unittest.main()
