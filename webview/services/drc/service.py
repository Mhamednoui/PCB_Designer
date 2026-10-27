"""DRC/ERC service - runs KiCad's own checks on a project's REAL files and returns structured results.

Its own process with its own API (see webview/server/services.py). The core backend knows only where
this lives, never what it does - so this can be rewritten, restarted or replaced without touching the
platform. Reached through the core at /api/services/drc/*.

  GET  /health          -> {status}
  POST /run {project}   -> runs DRC (and ERC when a schematic exists), returns counts + violations
"""
import json
import os
import sys
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8802
HERE = os.path.dirname(os.path.abspath(__file__))
# HERE is webview/services/drc -> up three levels is the workspace root. Two levels only reaches
# `webview/`, which ALSO has a projects/ folder (the platform's own per-project data), so getting this
# wrong silently looks in the wrong place and reports "no .kicad_pcb found".
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "tools"))
from boardgen.kicad_paths import CLI as KICAD_CLI  # noqa: E402


def find_project_files(project_id):
    base = os.path.join(WORKSPACE_ROOT, "projects", project_id)
    if not os.path.isdir(base):
        return None, None
    def pick(ext):
        hits = [f for f in os.listdir(base)
                if f.endswith(ext) and "-backup" not in f and "-routed" not in f]
        preferred = f"{project_id}{ext}"
        if preferred in hits:
            return os.path.join(base, preferred)
        return os.path.join(base, sorted(hits)[0]) if hits else None
    return pick(".kicad_pcb"), pick(".kicad_sch")


def run_check(kind, path, extra=()):
    """kind: 'drc' (pcb) or 'erc' (sch). Returns (summary_counts, violations)."""
    out = os.path.join(tempfile.gettempdir(), f"{kind}_report.json")
    cmd = [KICAD_CLI, "pcb" if kind == "drc" else "sch", kind,
           "--format", "json", "-o", out, *extra, path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if not os.path.isfile(out):
        return {"error": (proc.stderr or proc.stdout or "no report produced").strip()[:500]}, []
    with open(out, encoding="utf-8") as f:
        report = json.load(f)
    violations = []
    counts = {}
    for group in ("violations", "unconnected_items", "schematic_parity", "sheets"):
        for item in report.get(group, []) or []:
            sev = item.get("severity", "unknown")
            key = f"{group}/{sev}"
            counts[key] = counts.get(key, 0) + 1
            if len(violations) < 40:
                violations.append({
                    "group": group, "severity": sev,
                    "type": item.get("type", ""),
                    "description": (item.get("description") or "")[:200],
                })
    return counts, violations


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
            return self._json({"status": "ok", "service": "drc"})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad JSON"}, 400)
        project = body.get("project", "")
        if not re.match(r"^[A-Za-z0-9_-]+$", project or ""):
            return self._json({"error": "a valid 'project' is required"}, 400)

        pcb, sch = find_project_files(project)
        if not pcb:
            return self._json({"error": f"no .kicad_pcb found for '{project}'"}, 404)

        result = {"project": project, "pcb": os.path.basename(pcb)}
        counts, violations = run_check("drc", pcb, extra=["--schematic-parity"] if sch else ())
        result["drc"] = {"counts": counts, "violations": violations}
        if sch:
            ecounts, eviolations = run_check("erc", sch)
            result["sch"] = os.path.basename(sch)
            result["erc"] = {"counts": ecounts, "violations": eviolations}
        errors = sum(v for k, v in counts.items() if "error" in k)
        result["ok"] = errors == 0
        result["summary"] = f"DRC errors: {errors}" + (
            f" | ERC: {sum(v for k, v in ecounts.items() if 'error' in k)} errors" if sch else "")
        return self._json(result)


if __name__ == "__main__":
    print(f"drc service on http://127.0.0.1:{PORT}/")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
