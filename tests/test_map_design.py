import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from memorybenchmark.adapters import GameAdapter
from memorybenchmark.game import Game
from memorybenchmark.map_design import map_design
from memorybenchmark.server import make_server


class MapDesignTests(unittest.TestCase):
    def test_full_map_and_opportunities_match_eight_task_curriculum(self):
        design = map_design("lake-easy")
        self.assertEqual(len(design["map"]["nodes"]), 31)
        self.assertEqual(len(design["map"]["edges"]), 31)
        self.assertEqual([t["id"] for t in design["tasks"]], [f"T{i}" for i in range(1, 9)])
        risks = {t["location"]: t for t in design["triggers"]}
        self.assertEqual(set(risks), {"P1", "R1"})
        self.assertEqual([o["task_id"] for o in risks["P1"]["opportunities"]], ["T1", "T2", "T5", "T7"])
        self.assertEqual([o["task_id"] for o in risks["R1"]["opportunities"]], ["T3", "T4", "T6", "T8"])
        self.assertEqual(risks["P1"]["tools"][0]["depots"], ["D1"])
        self.assertEqual(risks["R1"]["tools"][0]["depots"], ["B4"])
        self.assertEqual(risks["P1"]["opportunities"][0]["role"], "first_contact")
        self.assertTrue(all(o["role"] == "reuse_opportunity" for o in risks["P1"]["opportunities"][1:]))
        self.assertEqual([sum(t["reference"]["encounters"].values()) for t in design["tasks"]], [1, 2, 1, 2, 2, 2, 2, 2])
        design["triggers"][0]["extra_effort"] = 0
        self.assertEqual(map_design("lake-easy")["triggers"][0]["extra_effort"], 38)

    def test_dynamic_rules_are_shown_without_inventing_static_routes(self):
        design = map_design("river")
        self.assertEqual(design["reference_scope"], "unavailable_dynamic_conditions")
        self.assertTrue(all(t["reference"] is None for t in design["tasks"]))
        self.assertEqual(design["triggers"][0]["edge"], ["F", "R"])
        self.assertEqual(design["triggers"][0]["conditions"], {"weather": "rain", "period": "night"})

    def test_review_http_is_read_only_and_never_enters_agent_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            server = make_server(port=0, log_root=Path(directory), scenario="lake-easy")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(Request(root + "/api/start", data=b'{"task_id":"T1"}',
                                     headers={"Content-Type": "application/json"})) as response:
                    initial = json.load(response)
                game = server.service.adapter(initial["instance_id"]).game
                checkpoint = game.snapshot()
                with urlopen(root + "/api/design?scenario=lake-easy") as response:
                    self.assertEqual(json.load(response)["audience"], "human_design_review")
                self.assertEqual(game.snapshot(), checkpoint)
                agent = GameAdapter(game).dispatch({"command": "read"})
                encoded = json.dumps(agent, ensure_ascii=False)
                self.assertNotIn("grip_kit", encoded)
                self.assertNotIn("湿滑岩坡", encoded)
                self.assertNotIn("opportunities", encoded)
                self.assertLess(len(agent["observation"]["map"]["nodes"]), 31)
                for path in ("/design", "/design.js", "/design.css"):
                    with urlopen(root + path) as response:
                        self.assertEqual(response.status, 200)
                with self.assertRaises(HTTPError) as error:
                    urlopen(root + "/api/design?scenario=unknown")
                self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
