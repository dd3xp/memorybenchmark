import json
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.ga_experiment import NativeGASessions
from memorybenchmark.ga_runtime import changed_files, copy_memory, decode_state, encode_state, memory_manifest, state_digest
from memorybenchmark.game import Game


class SessionBoundaryTests(unittest.TestCase):
    def test_checkpoint_roundtrip_keeps_requests_edges_and_evidence(self):
        game=Game()
        adapter=GameAdapter(game)
        adapter.dispatch({"command":"start","task_id":"T1"})
        adapter.action("move","J"); adapter.action("move","A"); adapter.action("submit")
        before=game.snapshot()
        restored=decode_state(json.loads(json.dumps(encode_state(before))))
        self.assertEqual(restored,before)
        self.assertEqual(state_digest(restored),state_digest(before))
        branch=Game(); branch.restore(restored)
        branch.start_task("T2")
        self.assertEqual(branch.clock,game.clock)
        self.assertEqual(branch.inventory,set())
        self.assertEqual(branch.surveyed,{"S"})
        self.assertEqual(branch.evidence,game.evidence)

    def test_memory_reset_uses_complete_baseline_and_detects_deleted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            baseline=root/"baseline"; baseline.mkdir()
            (baseline/"memory_management_sop.md").write_text("native SOP")
            initial=copy_memory(baseline,root/"learned")
            (root/"learned"/"experience.md").write_text("agent-owned experience")
            (root/"learned"/"memory_management_sop.md").write_text("modified SOP")
            retained=copy_memory(root/"learned",root/"retained")
            cleared=copy_memory(baseline,root/"cleared")
            self.assertEqual(cleared,initial)
            self.assertNotEqual(retained,cleared)
            self.assertEqual(changed_files(retained,cleared),["experience.md","memory_management_sop.md"])

    def test_memory_snapshot_rejects_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"source").mkdir(); (root/"secret").write_text("outside")
            try: (root/"source"/"link").symlink_to(root/"secret")
            except OSError: self.skipTest("symlink creation unavailable")
            with self.assertRaises(ValueError): memory_manifest(root/"source")

    def test_worker_cannot_start_or_select_future_game(self):
        game=Game(); adapter=GameAdapter(game)
        adapter.dispatch({"command":"start","task_id":"T1"})
        before=game.snapshot()
        for request in ({"command":"start","task_id":"T6"}, {"command":"read","instance_id":"sibling"}):
            self.assertIn("error",NativeGASessions._game(adapter,request))
        self.assertEqual(game.snapshot(),before)

    def test_pipe_replays_preserve_revision_and_stale_requests_do_not_execute(self):
        game=Game(); adapter=GameAdapter(game)
        game.start_task("T1")
        request={"command":"action","request_id":"move-1","action":{"type":"move","target":"J"}}
        result=NativeGASessions._game(adapter,request)
        self.assertEqual(NativeGASessions._game(adapter,request),result)
        self.assertEqual(game.steps,1)
        stale={"command":"action","request_id":"stale","expected_revision":1,
               "action":{"type":"move","target":"A"}}
        self.assertIn("error",NativeGASessions._game(adapter,stale))
        self.assertEqual(game.steps,1)

    def test_incomplete_session_is_not_a_fabricated_agent_abandon(self):
        game=Game(); game.start_task("T1")
        response=game.finish_incomplete("model_budget")
        self.assertFalse(response["observation"]["success"])
        self.assertTrue(response["observation"]["done"])
        self.assertEqual(game.steps,0)
        self.assertEqual(game.events[-1]["kind"],"runner_termination")
        self.assertNotIn("action",game.events[-1])
        game.start_task("T2")
        self.assertEqual(game.task_id,"T2")


if __name__ == "__main__": unittest.main()
