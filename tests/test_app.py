import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from app.server import HealthState, make_server


class HTTPHealthTests(unittest.TestCase):
    def request(self, path, ready=True, startup_delay=0):
        server = make_server("127.0.0.1", 0, HealthState(ready, startup_delay))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            try:
                response = urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=2)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ready_release_serves_requests(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(body["release"], "baseline")
        self.assertEqual(body["status"], "ready")

    def test_failed_readiness_returns_unavailable(self):
        self.assertEqual(self.request("/readyz", ready=False)[0], 503)

    def test_unready_release_does_not_serve_application_traffic(self):
        self.assertEqual(self.request("/", ready=False)[0], 503)

    def test_failed_readiness_does_not_fail_liveness(self):
        self.assertEqual(self.request("/livez", ready=False)[0], 200)

    def test_initialization_fails_startup_probe(self):
        self.assertEqual(self.request("/startupz", startup_delay=60)[0], 503)

    def test_initialization_blocks_readiness(self):
        self.assertEqual(self.request("/readyz", startup_delay=60)[0], 503)

    def test_initialization_does_not_fail_liveness(self):
        self.assertEqual(self.request("/livez", startup_delay=60)[0], 200)

    def test_initialized_release_passes_startup(self):
        self.assertEqual(self.request("/startupz")[0], 200)

    def test_unknown_path_returns_not_found(self):
        self.assertEqual(self.request("/does-not-exist")[0], 404)


if __name__ == "__main__":
    unittest.main()
