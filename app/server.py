"""A deliberately small health-check demonstration, not an internet-facing server."""
import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthState:
    def __init__(self, ready=True, startup_delay=0, release="baseline"):
        self.ready = ready
        self.started_at = time.monotonic()
        self.startup_delay = startup_delay
        self.release = release

    @property
    def initialized(self):
        return time.monotonic() - self.started_at >= self.startup_delay


def make_server(host, port, state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/livez":
                status, message = 200, "alive"
            elif self.path == "/startupz":
                status, message = (200, "initialized") if state.initialized else (503, "starting")
            elif self.path in ("/", "/readyz"):
                status, message = (200, "ready") if state.initialized and state.ready else (503, "not-ready")
            else:
                status, message = 404, "not-found"
            body = json.dumps({"status": message, "release": state.release}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            # Keep probe logs concise; no request headers or environment values.
            print(json.dumps({"event": "request", "message": format % args}), flush=True)

    return ThreadingHTTPServer((host, port), Handler)


def main():
    state = HealthState(
        ready=os.environ.get("READY", "true").lower() == "true",
        startup_delay=float(os.environ.get("STARTUP_DELAY_SECONDS", "0")),
        release=os.environ.get("RELEASE", "baseline"),
    )
    server = make_server("0.0.0.0", int(os.environ.get("PORT", "8080")), state)

    def stop(signum, frame):
        state.ready = False
        # shutdown must run outside the serve_forever thread to avoid deadlock.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
