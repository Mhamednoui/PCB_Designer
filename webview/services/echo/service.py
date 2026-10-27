"""Smallest possible service that honours the contract in server/services.py.

Copy this folder as the starting point for a real capability (SPICE runner, DRC runner, BOM pricing,
review agent, ...). The core backend needs no changes - it discovers this via service.json and proxies
/api/services/echo/* here.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8801


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._json({"status": "ok", "service": "echo"})
        return self._json({"service": "echo", "method": "GET", "path": self.path})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {"_raw": raw.decode("utf-8", "replace")}
        return self._json({"service": "echo", "method": "POST", "path": self.path, "received": payload})


if __name__ == "__main__":
    print(f"echo service on http://127.0.0.1:{PORT}/")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
