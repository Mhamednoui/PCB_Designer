"""SPICE service - runs a board's transient simulation and hands back the waveforms for playback.

The live-simulation backend for boards with no microcontroller (Wokwi only runs firmware). The actual
work is the shared pipeline stage `tools/boardgen/make_spice.py`; this process only exposes it over
HTTP, the same way the drc service exposes kicad-cli. Reached through the core at /api/services/spice/*.

  GET  /health                       -> {status}
  GET  /result?project=<id>          -> the last run's transient.json (no re-simulation)
  POST /run {project, supplies?}     -> re-simulates (supplies overrides e.g. {"VCC": 12}), returns it
"""
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 8801
HERE = os.path.dirname(os.path.abspath(__file__))
# webview/services/spice -> three levels up is the workspace root (two only reaches webview/, which
# has its own projects/ folder - see the same note in the drc service).
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MAKE_SPICE = os.path.join(WORKSPACE_ROOT, "tools", "boardgen", "make_spice.py")
PROJECT_RE = re.compile(r"^[A-Za-z0-9_-]+$")
NET_RE = re.compile(r"^[A-Za-z0-9_+\-]+$")


def result_path(project):
    return os.path.join(WORKSPACE_ROOT, "projects", project, "test", "spice", "transient.json")


def run(project, supplies):
    cmd = [sys.executable, MAKE_SPICE, project]
    for net, volts in supplies.items():
        cmd += ["--set", "%s=%s" % (net, float(volts))]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    log = (proc.stdout + proc.stderr).strip()
    path = result_path(project)
    # exit 1 with a result file = simulated fine but an expectation failed; that's a result, not an error
    if not os.path.isfile(path) or proc.returncode not in (0, 1):
        return {"ok": False, "error": log[-2000:] or "simulation failed"}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["log"] = log
    return data


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
        url = urlparse(self.path)
        if url.path.startswith("/health"):
            return self._json({"status": "ok", "service": "spice"})
        if url.path.startswith("/result"):
            project = (parse_qs(url.query).get("project") or [""])[0]
            if not PROJECT_RE.match(project):
                return self._json({"error": "a valid 'project' is required"}, 400)
            path = result_path(project)
            if not os.path.isfile(path):
                return self._json({"error": "no simulation run yet for '%s'" % project}, 404)
            with open(path, encoding="utf-8") as f:
                return self._json(json.load(f))
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.path.startswith("/run"):
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad JSON"}, 400)
        project = body.get("project", "")
        supplies = body.get("supplies") or {}
        if not PROJECT_RE.match(project or ""):
            return self._json({"error": "a valid 'project' is required"}, 400)
        try:
            supplies = {k: float(v) for k, v in supplies.items() if NET_RE.match(k)}
        except (TypeError, ValueError):
            return self._json({"error": "supplies must be {net: volts}"}, 400)
        return self._json(run(project, supplies))


if __name__ == "__main__":
    print("spice service on http://127.0.0.1:%d/" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
