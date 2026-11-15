import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from memorybenchmark.server import make_server


class FakeExperiments:
    def __init__(self):
        self.created = []

    def options(self):
        return {"models": [{"id": "gpt-5.6-luna"}], "maps": []}

    def listing(self):
        return []

    def preview(self, request):
        return {"total_tasks": 32}

    def create(self, request):
        self.created.append(request)
        return {
            "id": "paired-job",
            "jobs": [{"condition": "retain"}, {"condition": "clear"}],
        }


class ExperimentHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.experiments = FakeExperiments()
        self.server = make_server(
            port=0,
            log_root=Path(self.temporary.name),
            experiment_service=self.experiments,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def request(self, method, path, body=None, origin=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        client.request(
            method, path, None if body is None else json.dumps(body), headers
        )
        response = client.getresponse()
        data = response.read()
        status = response.status
        client.close()
        return status, data

    def test_creation_page_and_scripts_are_served(self):
        status, body = self.request("GET", "/experiments/new")
        self.assertEqual(status, 200)
        self.assertIn(b'id="experiment-dialog"', body)
        self.assertIn("启动实验".encode(), body)
        self.assertIn(b'id="viewer-loading"', body)
        self.assertNotIn(b'href="/experiments/new"', body)
        self.assertEqual(self.request("GET", "/experiments")[1], body)
        self.assertEqual(self.request("GET", "/ui-state.js")[0], 200)
        self.assertEqual(self.request("GET", "/new-experiment.js")[0], 200)

    def test_preview_does_not_dispatch(self):
        status, body = self.request("POST", "/api/experiments/preview", {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total_tasks"], 32)
        self.assertEqual(self.experiments.created, [])

    def test_cross_origin_creation_is_rejected_even_on_local_development_server(self):
        status, _ = self.request(
            "POST", "/api/experiments/create", {}, "https://outside.invalid"
        )
        self.assertEqual(status, 403)
        self.assertEqual(self.experiments.created, [])

    def test_valid_creation_returns_both_memory_conditions(self):
        status, body = self.request(
            "POST", "/api/experiments/create", {"request_id": "explicit-click"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            {j["condition"] for j in json.loads(body)["jobs"]}, {"retain", "clear"}
        )

    def test_managed_listing_is_read_only(self):
        status, body = self.request("GET", "/api/experiments/managed")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"pairs": []})
        self.assertEqual(self.experiments.created, [])


if __name__ == "__main__":
    unittest.main()
