from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from src.server import make_handler
from src.service import RiskApplication


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.web = Path(cls.temp.name) / "web"
        cls.web.mkdir()
        (cls.web / "index.html").write_text("<h1>SignalScope test page</h1>", encoding="utf-8")
        cls.app = RiskApplication(Path(cls.temp.name) / "signals.db")
        try:
            cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app, cls.web))
        except PermissionError:
            cls.temp.cleanup()
            raise unittest.SkipTest("Loopback sockets are blocked by this sandbox")
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.shutdown()
            cls.server.server_close()
            cls.thread.join(timeout=2)
            cls.temp.cleanup()

    def request_json(self, path, payload=None):
        if payload is None:
            request = Request(self.base + path)
        else:
            request = Request(
                self.base + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_health_state_and_static_page(self):
        status, health = self.request_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["portfolio_positions"], 12)
        status, state = self.request_json("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(
            set(state), {"signals", "portfolio", "latest_run", "runs", "source_status", "metrics"}
        )
        with urlopen(self.base + "/", timeout=3) as response:
            self.assertIn(b"SignalScope test page", response.read())

    def test_analyze_stress_reset_and_validation(self):
        status, analyzed = self.request_json("/api/analyze", {
            "source": "news", "entity": "Aster Manufacturing",
            "text": "Aster Manufacturing missed a bond interest payment and faces a credit downgrade after lenders warned of a possible default.",
        })
        self.assertEqual(status, 200)
        self.assertEqual(analyzed["signal"]["provenance"], "manual")
        self.assertEqual(analyzed["signal"]["impact_score"], 10)
        self.assertEqual(analyzed["run"]["loss_usd_m"], 57.96)
        self.assertIn("state", analyzed)
        status, stressed = self.request_json("/api/stress", {"signal_id": analyzed["signal"]["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(stressed["run"]["signal_id"], analyzed["signal"]["id"])
        status, reset = self.request_json("/api/demo/reset", {})
        self.assertEqual(status, 200)
        self.assertEqual(reset["state"]["metrics"]["manual_signals"], 0)
        with self.assertRaises(HTTPError) as error:
            self.request_json("/api/analyze", {"source": "news", "text": ""})
        self.assertEqual(error.exception.code, 400)
        with self.assertRaises(HTTPError) as error:
            self.request_json("/api/stress", {"signal_id": "missing"})
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
