from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from baen_economy.brunnfeld_sidecar import (
    BRUNNFELD_COMMIT,
    BrunnfeldServiceClient,
    BrunnfeldSidecarError,
)


RESPONSES = {
    "/api/state": {"current_tick": 12, "economy_snapshots": []},
    "/api/economy": [{"tick": 12, "food": 91}],
    "/api/marketplace": {"orders": [{"id": "o1"}]},
    "/api/trades": [{"id": "t1", "price": 4}],
    "/api/prices": {"grain": 4},
    "/api/villages": [{"id": "brunnfeld", "agentCount": 19}],
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib handler API
        if self.path == "/api/bad-shape":
            body = json.dumps([]).encode()
            self.send_response(200)
        elif self.path in RESPONSES:
            body = json.dumps(RESPONSES[self.path]).encode()
            self.send_response(200)
        else:
            body = b'{"error":"missing"}'
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        return


class BrunnfeldSidecarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_pin_is_exact(self):
        self.assertEqual(BRUNNFELD_COMMIT, "e0656ca01630333e26c622ffd4ba4c973b79eebe")

    def test_snapshot_reads_actual_brunnfeld_published_routes(self):
        client = BrunnfeldServiceClient(self.base_url)
        snapshot = client.snapshot()
        self.assertEqual(snapshot.upstream, "Brunnfeld Agentic World")
        self.assertEqual(snapshot.upstream_commit, BRUNNFELD_COMMIT)
        self.assertEqual(snapshot.state, RESPONSES["/api/state"])
        self.assertEqual(snapshot.economy, RESPONSES["/api/economy"])
        self.assertEqual(snapshot.marketplace, RESPONSES["/api/marketplace"])
        self.assertEqual(snapshot.trades, RESPONSES["/api/trades"])
        self.assertEqual(snapshot.prices, RESPONSES["/api/prices"])
        self.assertEqual(snapshot.villages, RESPONSES["/api/villages"])
        self.assertFalse(snapshot.canonical_time_advanced)

    def test_client_has_no_mutating_product_method(self):
        client = BrunnfeldServiceClient(self.base_url)
        for name in ("start", "generate_world", "trigger_event", "whisper", "meeting"):
            self.assertFalse(hasattr(client, name), name)

    def test_http_error_is_fail_closed(self):
        client = BrunnfeldServiceClient(self.base_url)
        with self.assertRaises(BrunnfeldSidecarError):
            client._get_json("/api/not-there")

    def test_invalid_base_url_is_rejected(self):
        with self.assertRaises(ValueError):
            BrunnfeldServiceClient("file:///tmp/brunnfeld")


if __name__ == "__main__":
    unittest.main()
