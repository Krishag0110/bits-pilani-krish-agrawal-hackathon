"""Dependency-free HTTP API and static dashboard server.

Run: python3 -m src.server
Optional: PORT=8000 HOST=0.0.0.0 SIGNALSCOPE_AUTO_REFRESH_SECONDS=300
"""

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import unquote, urlsplit

from .service import ROOT, RiskApplication, utc_now


MAX_BODY_BYTES = 128_000


def make_handler(application, web_root=None):
    web_directory = (Path(web_root) if web_root else ROOT / "web").resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "SignalScope/1.0"

        def _json(self, payload, status=HTTPStatus.OK):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status, message):
            self._json({"error": str(message)}, status)

        def _body(self):
            length_text = self.headers.get("Content-Length", "0")
            try:
                length = int(length_text)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length") from exc
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("Request body exceeds 128 KB")
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("Request body must be valid JSON") from exc
            if not isinstance(data, dict):
                raise ValueError("Request body must be a JSON object")
            return data

        def _static(self, path):
            relative = Path(unquote(path).lstrip("/") or "index.html")
            candidate = (web_directory / relative).resolve()
            try:
                candidate.relative_to(web_directory)
            except ValueError:
                self._error(HTTPStatus.NOT_FOUND, "File not found")
                return
            if not candidate.is_file():
                self._error(HTTPStatus.NOT_FOUND, "File not found")
                return
            try:
                body = candidate.read_bytes()
            except OSError:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not read file")
                return
            mime = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if mime.startswith("text/") or mime in {"application/javascript", "application/json"}:
                mime += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    self._json({
                        "status": "ok",
                        "service": "SignalScope Risk Engine",
                        "version": "1.0.0",
                        "time": utc_now(),
                        "storage": "sqlite",
                        "training_examples": application.model.training_count,
                        "portfolio_positions": len(application.portfolio),
                    })
                elif path == "/api/state":
                    self._json(application.state())
                elif path.startswith("/api/"):
                    self._error(HTTPStatus.NOT_FOUND, "Unknown API route")
                else:
                    self._static(path)
            except BrokenPipeError:
                pass
            except Exception:
                logging.exception("GET %s failed", path)
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                body = self._body()
                if path == "/api/analyze":
                    self._json(application.analyze(body))
                elif path == "/api/refresh":
                    self._json(application.refresh(body.get("limit", 12)))
                elif path == "/api/stress":
                    self._json(application.stress(body.get("signal_id")))
                elif path == "/api/demo/reset":
                    self._json({"state": application.reset_demo()})
                else:
                    self._error(HTTPStatus.NOT_FOUND, "Unknown API route")
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, exc)
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, exc.args[0] if exc.args else "Not found")
            except BrokenPipeError:
                pass
            except Exception:
                logging.exception("POST %s failed", path)
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")

    return Handler


def start_auto_refresh(application, seconds):
    """Start optional immediate+periodic live polling; return a stop Event."""
    stop = threading.Event()
    if seconds <= 0:
        return stop
    interval = max(60, seconds)

    def poll():
        while not stop.is_set():
            try:
                application.refresh()
            except Exception:
                logging.exception("Automatic live refresh failed")
            stop.wait(interval)

    threading.Thread(target=poll, name="signalscope-auto-refresh", daemon=True).start()
    return stop


def main(argv=None):
    parser = argparse.ArgumentParser(description="SignalScope local risk engine")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--db", default=os.environ.get("RISK_DB", str(ROOT / "data" / "signalscope.db")))
    args = parser.parse_args(argv)
    refresh_seconds = int(os.environ.get("SIGNALSCOPE_AUTO_REFRESH_SECONDS", "0"))
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    application = RiskApplication(db_path=args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(application))
    stop = start_auto_refresh(application, refresh_seconds)
    print("SignalScope running at http://%s:%d" % (args.host, server.server_port), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
