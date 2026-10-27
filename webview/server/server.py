"""PCB webview platform - local backend.

Stdlib only, on purpose (see ROADMAP.md "open questions" - stay stdlib until it's genuinely painful).
Binds 127.0.0.1 ONLY - this is a local tool for one user's machine, never expose it on a real network.

Serves:
  GET  /                                    -> app/index.html (the frontend)
  GET  /<static file under app/>            -> app/ static files (js, css, assets/icons/...)
  GET  /projects/<id>/<file>                -> webview/projects/<id>/ static files (model.glb, ...)
  GET  /api/projects                        -> [{id, name}, ...] for every project with a manifest.json
  GET  /api/projects/<id>/manifest          -> that project's manifest.json
  GET  /api/projects/<id>/log               -> run history (JSON array), oldest first
  POST /api/projects/<id>/actions/<action>  -> runs the action declared in that project's manifest,
                                                appends the result to run_log.jsonl, returns it as JSON

  Live simulation (only for projects with a wokwi_map.json - manifest.live_sim tells the frontend
  whether to show these controls at all). Every start/stop cycle spends real Wokwi quota - see
  wokwi_mcp.py and the project's own test/wokwi/USAGE_LOG.md, which this backend updates automatically.
  POST /api/projects/<id>/sim/start         -> spawns a real `wokwi-cli mcp` session, real firmware
  POST /api/projects/<id>/sim/stop          -> stops it, logs elapsed seconds to USAGE_LOG.md
  POST /api/projects/<id>/sim/press  {net}  -> pulses that input's control (press then release)
  GET  /api/projects/<id>/sim/outputs       -> {net: bool, ...} - live pin reads for the mapped outputs

Run: python server.py [port]   (default 8787; WOKWI_CLI_TOKEN is read from the Windows user env), then open http://127.0.0.1:8787/
"""
import json
import mimetypes
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actions as actions_module  # noqa: E402
import services as services_module  # noqa: E402
import vcd as vcd_module  # noqa: E402
import wokwi_mcp  # noqa: E402

WEBVIEW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(WEBVIEW_DIR)
APP_DIR = os.path.join(WEBVIEW_DIR, "app")
PROJECTS_DIR = os.path.join(WEBVIEW_DIR, "projects")

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

MIME_OVERRIDES = {".glb": "model/gltf-binary", ".svg": "image/svg+xml", ".json": "application/json"}


def guess_type(path):
    ext = os.path.splitext(path)[1].lower()
    return MIME_OVERRIDES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def safe_join(base, *parts):
    """Join and resolve, refusing to escape `base` (blocks ../ path traversal)."""
    target = os.path.realpath(os.path.join(base, *parts))
    base_real = os.path.realpath(base)
    if os.path.commonpath([target, base_real]) != base_real:
        return None
    return target


def list_projects():
    out = []
    if not os.path.isdir(PROJECTS_DIR):
        return out
    for entry in sorted(os.listdir(PROJECTS_DIR)):
        manifest_path = os.path.join(PROJECTS_DIR, entry, "manifest.json")
        if os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                name = json.load(f).get("name", entry)
            out.append({"id": entry, "name": name})
    return out


def read_log(project_id):
    log_path = os.path.join(PROJECTS_DIR, project_id, "run_log.jsonl")
    if not os.path.isfile(log_path):
        return []
    entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_log(project_id, entry):
    log_path = os.path.join(PROJECTS_DIR, project_id, "run_log.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_wokwi_map(project_id):
    path = os.path.join(PROJECTS_DIR, project_id, "wokwi_map.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# One live wokwi-cli session per project at a time. Guarded by a lock since MCP calls are
# request/response over a single stdio pipe - never let two HTTP requests race on the same session.
_sessions = {}
_sessions_lock = threading.Lock()

MONTHLY_QUOTA_S = 3000  # 50 minutes, the Wokwi free tier


def log_wokwi_quota(project_id, wmap, description, duration_s):
    """Append a row to the project's OWN test/wokwi/USAGE_LOG.md - the convention already established
    for tracking this metered resource - and recompute the running total/remaining summary line."""
    usage_path = os.path.join(WORKSPACE_ROOT, wmap["cwd"], "USAGE_LOG.md")
    if not os.path.isfile(usage_path):
        return
    with open(usage_path, encoding="utf-8") as f:
        text = f.read()

    m = re.search(r"\*\*Month: (.*?)\. Total used: (\d+)s\. Remaining: .*?\*\*", text)
    prior_total = int(m.group(2)) if m else 0
    month = m.group(1) if m else time.strftime("%B %Y")
    new_total = prior_total + round(duration_s)
    remaining_s = MONTHLY_QUOTA_S - new_total
    date = time.strftime("%Y-%m-%d")
    new_row = f"| {date} | webview platform - {description} | {round(duration_s)} | {new_total} | {remaining_s} / ~{remaining_s / 60:.1f} |\n"
    new_summary = f"**Month: {month}. Total used: {new_total}s. Remaining: ~{remaining_s / 60:.1f} min.**"

    lines = text.splitlines(keepends=True)
    table_end = next((i for i, line in enumerate(lines) if line.startswith("**Month:")), len(lines))
    lines.insert(table_end - 1 if table_end > 0 and lines[table_end - 1].strip() == "" else table_end, new_row)
    text = "".join(lines)
    if m:
        text = re.sub(r"\*\*Month: .*?\. Total used: \d+s\. Remaining: .*?\*\*", new_summary, text, count=1)
    with open(usage_path, "w", encoding="utf-8") as f:
        f.write(text)


def read_wokwi_quota(wmap):
    """Current used/remaining seconds this month, without writing anything (for the frontend's live
    'quota remaining' readout, shown before/while a session runs)."""
    usage_path = os.path.join(WORKSPACE_ROOT, wmap["cwd"], "USAGE_LOG.md")
    used = 0
    if os.path.isfile(usage_path):
        with open(usage_path, encoding="utf-8") as f:
            m = re.search(r"\*\*Month: .*?\. Total used: (\d+)s\. Remaining: .*?\*\*", f.read())
        used = int(m.group(1)) if m else 0
    return {"used_s": used, "remaining_s": MONTHLY_QUOTA_S - used, "quota_s": MONTHLY_QUOTA_S}


def _stop_session_locked(pid, wmap, description):
    """Caller must hold _sessions_lock. Stops+removes the session (if any) and logs quota. Used by both
    the manual /sim/stop route and the auto-stop timer, so both paths log identically."""
    entry = _sessions.pop(pid, None)
    if not entry:
        return None
    if entry.get("timer"):
        entry["timer"].cancel()
    elapsed = entry["session"].stop()
    log_wokwi_quota(pid, wmap, description, elapsed)
    return elapsed


def read_outputs(session, wmap):
    """Builds one pipelined, debounced batch read across every declared output - including any
    "display" (e.g. 7-segment) outputs, whose several segment pins get read in the same batch and then
    decoded. This is generic: it only depends on the shape of wmap["outputs"], never on which project."""
    specs = []
    display_keys = {}  # net -> {segment_letter: batch_key}
    for net, spec in wmap.get("outputs", {}).items():
        if "display" in spec:
            keymap = {}
            for seg, pin in spec["display"]["segments"].items():
                key = f"{net}::{seg}"
                specs.append((key, spec["display"]["part"], pin))
                keymap[seg] = key
            display_keys[net] = keymap
        else:
            specs.append((net, spec["partId"], spec["pin"]))

    raw = session.read_outputs_debounced(specs)

    values = {}
    for net, spec in wmap.get("outputs", {}).items():
        if net in display_keys:
            seg_states = {seg: raw.get(key) for seg, key in display_keys[net].items()}
            values[net] = wokwi_mcp.decode_seven_segment(seg_states)
        else:
            values[net] = raw.get(net)
    return values


def _auto_stop(pid):
    wmap = load_wokwi_map(pid)
    with _sessions_lock:
        elapsed = _stop_session_locked(pid, wmap, "live sim session (auto-stopped at time limit)")
    if elapsed is not None:
        append_log(pid, {"timestamp": time.time(), "action_id": "sim-stop", "ok": True,
                          "label": "Simulation auto-stopped (time limit reached)",
                          "output": f"Stopped after {elapsed:.1f}s - logged to test/wokwi/USAGE_LOG.md."})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not path or not os.path.isfile(path):
            self._send_json({"error": "not found"}, 404)
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", guess_type(path))
        self.send_header("Content-Length", str(len(body)))
        # Without this, browsers heuristically cache main.js/style.css (no ETag/Last-Modified is sent
        # either), so edits to the frontend silently do nothing on a normal refresh - this cost three
        # rounds of "fixed it" / "still broken" on the 3D zoom before anyone checked the headers.
        # This is a local dev tool; always serve fresh.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/projects":
            return self._send_json(list_projects())

        # Pluggable services (see server/services.py). The core knows nothing about what any service
        # does - only where it lives. New capabilities register themselves, they don't edit this file.
        if path == "/api/services":
            return self._send_json(services_module.describe_all(WEBVIEW_DIR))

        m = re.match(r"^/api/services/([^/]+)/?(.*)$", path)
        if m:
            return self._proxy_service(m.group(1), m.group(2), "GET", None)

        m = re.match(r"^/api/projects/([^/]+)/manifest$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            return self._send_file(safe_join(PROJECTS_DIR, pid, "manifest.json"))

        m = re.match(r"^/api/projects/([^/]+)/log$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            return self._send_json(read_log(pid))

        m = re.match(r"^/api/projects/([^/]+)/sim/outputs$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            with _sessions_lock:
                entry = _sessions.get(pid)
                wmap = load_wokwi_map(pid)
                if not entry or not wmap:
                    return self._send_json({})
                try:
                    return self._send_json(read_outputs(entry["session"], wmap))
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"error": str(e)}, 500)

        # Live serial output from the running firmware. This exists because a whole debugging session
        # was spent inferring firmware state from LED pins while the firmware was printing the answer
        # ("ERR:NEED2000:HAVE500") to a serial port nobody was reading.
        m = re.match(r"^/api/projects/([^/]+)/sim/serial$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            with _sessions_lock:
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"text": "", "running": False})
                try:
                    text = entry["session"].read_serial(clear=True)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"text": "", "running": True, "error": str(e)})
                return self._send_json({"text": text, "running": True})

        m = re.match(r"^/api/projects/([^/]+)/sim/status$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            with _sessions_lock:
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"running": False})
                return self._send_json({
                    "running": True,
                    "elapsed_s": entry["session"].elapsed(),
                    "limit_s": entry.get("limit_s"),
                })

        m = re.match(r"^/api/projects/([^/]+)/sim/quota$", path)
        if m:
            pid = m.group(1)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            wmap = load_wokwi_map(pid)
            if not wmap:
                return self._send_json({"error": "no live simulation configured"}, 404)
            return self._send_json(read_wokwi_quota(wmap))

        m = re.match(r"^/projects/([^/]+)/(.+)$", path)
        if m:
            pid, rest = m.group(1), m.group(2)
            if not ID_RE.match(pid):
                return self._send_json({"error": "bad project id"}, 400)
            return self._send_file(safe_join(PROJECTS_DIR, pid, rest))

        # everything else: static frontend from app/
        rel = path.lstrip("/") or "index.html"
        return self._send_file(safe_join(APP_DIR, rel))

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        parsed = urlparse(self.path)

        m = re.match(r"^/api/projects/([^/]+)/actions/([^/]+)$", parsed.path)
        if m:
            return self._handle_action(m.group(1), m.group(2))

        m = re.match(r"^/api/projects/([^/]+)/sim/(start|stop|press|input|pulse|serial|capture|shot)$",
                      parsed.path)
        if m:
            return self._handle_sim(m.group(1), m.group(2))

        m = re.match(r"^/api/projects/([^/]+)/scenario$", parsed.path)
        if m:
            return self._handle_scenario(m.group(1))

        m = re.match(r"^/api/projects/([^/]+)/io$", parsed.path)
        if m:
            return self._handle_io_edit(m.group(1))

        m = re.match(r"^/api/services/([^/]+)/?(.*)$", parsed.path)
        if m:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw_body = self.rfile.read(length) if length else None
            return self._proxy_service(m.group(1), m.group(2), "POST", raw_body)

        return self._send_json({"error": "not found"}, 404)

    def _proxy_service(self, name, path, method, body):
        if not ID_RE.match(name):
            return self._send_json({"error": "bad service name"}, 400)
        status, content_type, payload = services_module.proxy(
            WEBVIEW_DIR, name, path, method, body, self.headers,
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_action(self, pid, action_id):
        if not (ID_RE.match(pid) and ID_RE.match(action_id)):
            return self._send_json({"error": "bad id"}, 400)

        manifest_path = safe_join(PROJECTS_DIR, pid, "manifest.json")
        if not manifest_path or not os.path.isfile(manifest_path):
            return self._send_json({"error": "unknown project"}, 404)
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        action = next((a for a in manifest.get("actions", []) if a.get("id") == action_id), None)
        if not action:
            return self._send_json({"error": "unknown action"}, 404)

        result = actions_module.run_action(WORKSPACE_ROOT, action)
        entry = {"timestamp": time.time(), "action_id": action_id, "label": action.get("label"),
                  **result}
        append_log(pid, entry)
        return self._send_json(entry)

    def _handle_scenario(self, pid):
        """Save a recorded click session as a Wokwi scenario YAML.

        Turns "I pressed some things and it looked wrong" into a repeatable regression test that runs
        headless in a few seconds instead of a 60s manual session - which matters when simulation time
        is a metered resource. The file lands next to the project's diagram so `wokwi-cli --scenario`
        can run it directly.
        """
        if not ID_RE.match(pid):
            return self._send_json({"error": "bad project id"}, 400)
        body = self._read_json_body()
        steps = body.get("steps") or []
        if not steps:
            return self._send_json({"error": "nothing recorded"}, 400)

        wmap = load_wokwi_map(pid)
        if not wmap:
            return self._send_json({"error": "project has no live simulation configured"}, 404)
        inputs = wmap.get("inputs", {})

        name = re.sub(r"[^A-Za-z0-9_-]", "_", body.get("name") or "recorded")
        lines = [f"name: '{name}'", "version: 1", "author: 'webview recorder'", "steps:"]
        for step in steps:
            spec = inputs.get(step.get("net", ""))
            if not spec:
                continue
            delay = max(0, int(step.get("delay_ms", 0)))
            if delay:
                lines.append(f"  - delay: {delay}ms")
            part, control = spec["partId"], spec["control"]
            kind = step.get("kind", "press")
            if kind == "press":
                lines.append(f"  - set-control: {{ part-id: {part}, control: {control}, value: 1 }}")
                lines.append("  - delay: 80ms")
                lines.append(f"  - set-control: {{ part-id: {part}, control: {control}, value: 0 }}")
            elif kind == "pulse":
                for _ in range(max(1, int(step.get("count", 1)))):
                    lines.append(f"  - set-control: {{ part-id: {part}, control: {control}, value: 1 }}")
                    lines.append(f"  - set-control: {{ part-id: {part}, control: {control}, value: 0 }}")
            else:  # a plain value (toggle / analog)
                lines.append(
                    f"  - set-control: {{ part-id: {part}, control: {control}, value: {step.get('value', 0)} }}")

        out_dir = os.path.join(WORKSPACE_ROOT, wmap["cwd"])
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"scenario_{name}.yaml")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return self._send_json({
            "ok": True,
            "path": os.path.relpath(out_path, WORKSPACE_ROOT).replace("\\", "/"),
            "steps": len(steps),
            "hint": "replay headless: wokwi-cli --scenario <file> --diagram-file diagram.json .",
        })

    def _handle_io_edit(self, pid):
        """Change an io entry's type from inside the platform, and make it stick.

        You don't always know up front that a signal is a pulse-counting input rather than a plain
        button - you find out by watching it misbehave. This writes the change back to the project's
        io_map.json (the source of truth a human edits) AND patches manifest.json (what the frontend
        reads), so a reload keeps it without re-running the generators.
        """
        if not ID_RE.match(pid):
            return self._send_json({"error": "bad project id"}, 400)
        body = self._read_json_body()
        net, new_type = body.get("net"), body.get("type")
        if not net or not new_type:
            return self._send_json({"error": "net and type are required"}, 400)

        proj_dir = safe_join(PROJECTS_DIR, pid)
        if not proj_dir:
            return self._send_json({"error": "bad project id"}, 400)

        updated = []
        for filename, finder in (
            ("io_map.json", lambda d: d.get("inputs", []) + d.get("outputs", [])),
            ("manifest.json", lambda d: d.get("io", [])),
        ):
            path = os.path.join(proj_dir, filename)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            hit = False
            for item in finder(data):
                if isinstance(item, dict) and item.get("net") == net:
                    item["type"] = new_type
                    hit = True
            if hit:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                updated.append(filename)

        if not updated:
            return self._send_json({"error": f"net '{net}' not found in this project's io"}, 404)
        return self._send_json({"ok": True, "net": net, "type": new_type, "updated": updated})

    def _handle_sim(self, pid, verb):
        if not ID_RE.match(pid):
            return self._send_json({"error": "bad project id"}, 400)
        wmap = load_wokwi_map(pid)
        if not wmap:
            return self._send_json({"error": "project has no live simulation configured"}, 404)

        body = self._read_json_body() if verb in (
            "start", "press", "input", "pulse", "serial", "shot") else {}

        with _sessions_lock:
            if verb == "start":
                if pid in _sessions:
                    return self._send_json({"ok": False, "output": "simulation already running"})
                # Without a token wokwi-cli never answers the MCP handshake, so the request used to hang
                # until the timeout - long after the browser gave up - and the user saw no error at all.
                wokwi_mcp._load_saved_token()  # picks up a token saved after this server started
                if not os.environ.get("WOKWI_CLI_TOKEN"):
                    return self._send_json({"ok": False, "output": (
                        "WOKWI_CLI_TOKEN is not saved, so Wokwi can't run. Save it once in PowerShell: "
                        "[Environment]::SetEnvironmentVariable('WOKWI_CLI_TOKEN','<token>','User') "
                        "then press Start Simulation again - no restart needed (token from https://wokwi.com/dashboard/ci).")})
                limit_s = body.get("limit_s")
                if limit_s is not None:
                    try:
                        limit_s = max(1, min(float(limit_s), 300))  # sane bounds: 1s..5min per session
                    except (TypeError, ValueError):
                        limit_s = None
                cwd = os.path.join(WORKSPACE_ROOT, wmap["cwd"])
                try:
                    session = wokwi_mcp.WokwiSession(cwd)
                    session.start_simulation()
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                timer = None
                if limit_s:
                    timer = threading.Timer(limit_s, _auto_stop, args=(pid,))
                    timer.daemon = True
                    timer.start()
                _sessions[pid] = {"session": session, "timer": timer, "limit_s": limit_s}
                entry = {"timestamp": time.time(), "action_id": "sim-start",
                          "label": "Start live simulation", "ok": True,
                          "output": "Live simulation started - this is now spending Wokwi quota."
                                    + (f" Auto-stops after {limit_s:.0f}s." if limit_s else "")}
                append_log(pid, entry)
                return self._send_json(entry)

            if verb == "stop":
                elapsed = _stop_session_locked(pid, wmap, "live sim session (webview Start/Stop)")
                if elapsed is None:
                    return self._send_json({"ok": False, "output": "no simulation running"})
                entry = {"timestamp": time.time(), "action_id": "sim-stop",
                          "label": "Stop live simulation", "ok": True,
                          "output": f"Stopped after {elapsed:.1f}s - logged to test/wokwi/USAGE_LOG.md."}
                append_log(pid, entry)
                return self._send_json(entry)

            if verb == "capture":
                # Logic-analyzer capture -> real duty cycle / frequency per signal, instead of the
                # coin-flip you get from sampling a PWM pin (see webview/server/vcd.py).
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"error": "no simulation running"}, 409)
                out_dir = os.path.join(PROJECTS_DIR, pid)
                out_path = os.path.join(out_dir, "capture.vcd")
                try:
                    entry["session"].export_vcd(out_path)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                if not os.path.isfile(out_path):
                    return self._send_json({"ok": False,
                                            "output": "the simulator reported success but wrote no VCD file"})
                try:
                    analysis = vcd_module.analyse_file(out_path)
                except Exception as e:  # a malformed dump shouldn't take the server down
                    return self._send_json({"ok": False, "output": f"could not parse VCD: {e}"})
                return self._send_json({"ok": True, **analysis})

            if verb == "shot":
                # Screenshot a display part (7-segment, OLED, LCD) - the honest way to show what a
                # display is showing, versus decoding shift-register pins (which proved unreliable).
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"error": "no simulation running"}, 409)
                part = body.get("partId")
                if not part:
                    return self._send_json({"error": "partId is required"}, 400)
                try:
                    text = entry["session"].take_screenshot(part)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                return self._send_json({"ok": True, "output": text})

            if verb == "serial":
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"error": "no simulation running"}, 409)
                text = body.get("text", "")
                if not isinstance(text, str) or not text:
                    return self._send_json({"error": "text is required"}, 400)
                if body.get("newline", True) and not text.endswith("\n"):
                    text += "\n"   # most firmware reads a line at a time
                try:
                    entry["session"].write_serial(text)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                return self._send_json({"ok": True, "sent": text})

            if verb == "pulse":
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"error": "no simulation running"}, 409)
                spec = wmap.get("inputs", {}).get(body.get("net", ""))
                if not spec:
                    return self._send_json({"error": "unknown input net"}, 404)
                try:
                    count = int(body.get("count", 1))
                except (TypeError, ValueError):
                    return self._send_json({"error": "count must be a whole number"}, 400)
                count = max(1, min(count, 64))
                started = time.time()
                try:
                    sent = entry["session"].pulse_burst(spec["partId"], spec["control"], count)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                # Report how long the burst actually took: firmware that groups pulses by a timing
                # window (this board: 300ms) only behaves correctly if the whole burst fits inside it.
                return self._send_json({
                    "ok": True, "pulses": sent,
                    "burst_ms": round((time.time() - started) * 1000),
                })

            if verb in ("press", "input"):
                entry = _sessions.get(pid)
                if not entry:
                    return self._send_json({"error": "no simulation running"}, 409)
                spec = wmap.get("inputs", {}).get(body.get("net", ""))
                if not spec:
                    return self._send_json({"error": "unknown input net"}, 404)
                session = entry["session"]
                part, control = spec["partId"], spec["control"]
                try:
                    if verb == "press":
                        # Momentary: pulse the control and let go again.
                        session.set_control(part, control, 1)
                        time.sleep(0.08)
                        session.set_control(part, control, 0)
                        applied = None
                    else:
                        # Generic: set the control to ANY value and leave it there. Wokwi's set_control
                        # already takes a number, so this covers toggles (0/1) and analog inputs
                        # (a potentiometer's position, a sensor reading, ...) with no special casing -
                        # the input's `type` in io_map.json only decides which widget the UI shows.
                        try:
                            applied = float(body.get("value", 0))
                        except (TypeError, ValueError):
                            return self._send_json({"error": "value must be a number"}, 400)
                        if applied == int(applied):
                            applied = int(applied)
                        session.set_control(part, control, applied)
                except wokwi_mcp.WokwiMcpError as e:
                    return self._send_json({"ok": False, "output": str(e)})
                return self._send_json({"ok": True, "value": applied})

        return self._send_json({"error": "not found"}, 404)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"PCB webview platform running at http://127.0.0.1:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
