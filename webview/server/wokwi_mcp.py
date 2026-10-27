"""Talks to a real `wokwi-cli mcp` subprocess - the actual Wokwi simulator (real compiled firmware,
real wiring), controlled over its MCP (JSON-RPC over stdio) interface. This is the "separate tool
working in the background" the platform's frontend never touches directly - it only ever calls this
module's methods through the backend's HTTP routes.

IMPORTANT: every session here spends real Wokwi simulation-minute quota for as long as it's running
(the free tier is 50 min/month). The server logs every start/stop cycle's duration to the project's own
test/wokwi/USAGE_LOG.md - the existing quota-tracking convention - not just internally. Never start a
session without the frontend user explicitly clicking "Start Simulation".

Requires WOKWI_CLI_TOKEN. It is kept as a Windows USER environment variable (HKCU\\Environment) - never
in a project file - and loaded from there below if the shell that started server.py predates it.
"""
import json
import os
import queue
import subprocess
import threading
import time

WOKWI_CLI = os.path.expanduser("~/.wokwi/bin/wokwi-cli.exe")


def _load_saved_token():
    """A terminal (or VS Code) opened before the variable was saved doesn't see it, which is exactly the
    "the simulation doesn't run" trap - so read the user-scope value from the registry directly.
    The spawned wokwi-cli inherits os.environ, so setting it here is all that's needed."""
    if os.environ.get("WOKWI_CLI_TOKEN"):
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "WOKWI_CLI_TOKEN")
        if value:
            os.environ["WOKWI_CLI_TOKEN"] = value
    except (ImportError, OSError):
        pass  # not Windows, or not saved yet - /sim/start reports it clearly


_load_saved_token()


class WokwiMcpError(Exception):
    pass


# Standard common-cathode 7-segment digit patterns (which of a..g are lit) - not project-specific;
# a project's wokwi_map.json only needs to say which physical pin drives which segment letter.
_SEVEN_SEG_DIGITS = {
    frozenset("abcdef"): 0, frozenset("bc"): 1, frozenset("abdeg"): 2, frozenset("abcdg"): 3,
    frozenset("bcfg"): 4, frozenset("acdfg"): 5, frozenset("acdefg"): 6, frozenset("abc"): 7,
    frozenset("abcdefg"): 8, frozenset("abcdfg"): 9,
}


def decode_seven_segment(segment_states):
    """segment_states: {'a': bool_or_None, ..., 'g': ...}. Returns a digit 0-9, None for blank
    (nothing lit), or '?' for a lit-but-unrecognized pattern (mid-transition read, generally harmless)."""
    lit = frozenset(k for k, v in segment_states.items() if v)
    if not lit:
        return None
    return _SEVEN_SEG_DIGITS.get(lit, "?")


class WokwiSession:
    """One live `wokwi-cli mcp <cwd>` subprocess. Not thread-safe across concurrent calls by design -
    the server only ever has one call in flight per project at a time (see server.py's lock)."""

    def __init__(self, cwd):
        self.cwd = cwd
        self.started_at = None
        self._next_id = 1
        self._queue = queue.Queue()
        self._proc = subprocess.Popen(
            [WOKWI_CLI, "mcp", "."],
            cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        self._call("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "pcb-webview", "version": "0.1"},
        })

    def _read_stdout(self):
        for line in iter(self._proc.stdout.readline, ""):
            line = line.strip()
            if line:
                self._queue.put(line)

    def _call(self, method, params, timeout=15):
        req_id = self._next_id
        self._next_id += 1
        self._proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}) + "\n")
        self._proc.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise WokwiMcpError(str(msg["error"]))
                return msg.get("result")
        raise WokwiMcpError(f"timed out waiting for response to {method}")

    def _tool(self, name, arguments, timeout=15):
        result = self._call("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
        content = result.get("content", [])
        text = content[0]["text"] if content else ""
        return text

    def start_simulation(self):
        self.started_at = time.time()
        return self._tool("wokwi_start_simulation", {"projectPath": "."}, timeout=20)

    def set_control(self, part_id, control, value):
        return self._tool("wokwi_set_control", {"partId": part_id, "control": control, "value": value})

    def read_pin(self, part_id, pin):
        text = self._tool("wokwi_read_pin", {"partId": part_id, "pin": pin})
        # "Pin 22 on mega: false (undefinedV)" - just need the boolean.
        return "true" in text.split(":", 1)[-1].split("(")[0].lower()

    def pulse_burst(self, part_id, control, count):
        """Inject a burst of `count` pulses on one control, as one atomic operation.

        WHY THIS EXISTS: pulse-counting inputs (coin acceptors, flow meters, tachometers, encoders)
        don't care that a pin went low - they care HOW MANY edges arrived INSIDE a timing window.
        This board's coin detector, for example, groups pulses separated by <300ms into one "coin" and
        values it by the count (1-2 pulses = 500, 3-5 = 1000, 6 = 2000), discarding 7+.

        A button click can never hit that window: every click is its own HTTP request plus an MCP round
        trip, so consecutive clicks land 100s of ms apart and each is read as a separate 1-pulse coin.
        So the whole burst is written here in one go - every request is pushed onto the pipe before any
        response is read - which puts all the edges back-to-back the way real hardware emits them.
        The burst then commits naturally, because nothing else follows it for >300ms.
        """
        pending = {}
        for _ in range(count):
            for value in (1, 0):  # press, release = one pulse (one falling edge for the ISR)
                req_id = self._next_id
                self._next_id += 1
                pending[req_id] = True
                self._proc.stdin.write(json.dumps({
                    "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                    "params": {"name": "wokwi_set_control",
                                "arguments": {"partId": part_id, "control": control, "value": value}},
                }) + "\n")
        self._proc.stdin.flush()

        deadline = time.time() + 15
        while pending and time.time() < deadline:
            try:
                line = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            pending.pop(msg.get("id"), None)
        return count - len(pending) // 2

    def read_pins_batch(self, specs):
        """specs: list of (key, part_id, pin). Fires every read_pin request without waiting for each
        response before sending the next (pipelined over the one stdio connection) - reading N pins
        sequentially (N round-trips) was the reason polling lagged seconds behind the 400ms interval it
        was supposed to run at. Returns {key: bool_or_None}."""
        pending = {}
        for key, part_id, pin in specs:
            req_id = self._next_id
            self._next_id += 1
            pending[req_id] = key
            self._proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                "params": {"name": "wokwi_read_pin", "arguments": {"partId": part_id, "pin": pin}},
            }) + "\n")
        self._proc.stdin.flush()

        results = {}
        deadline = time.time() + 10
        while pending and time.time() < deadline:
            try:
                line = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = msg.get("id")
            if req_id in pending:
                key = pending.pop(req_id)
                if "error" in msg:
                    results[key] = None
                else:
                    text = msg["result"]["content"][0]["text"]
                    results[key] = "true" in text.split(":", 1)[-1].split("(")[0].lower()
        for key in pending.values():
            results[key] = None
        return results

    def read_outputs_debounced(self, specs, samples=6, gap_s=0.02):
        """Several rapid pipelined samples, OR'd together, instead of one instantaneous read.
        Necessary for PWM-driven outputs (e.g. analogWrite-held magnets at partial duty cycle): a single
        sample lands at a random point in the waveform and looks like noise, not a steady "on". A few
        quick samples almost always catch at least one high phase if the output is genuinely energized,
        while a genuinely-off pin never reads high across any sample."""
        agg = {key: False for key, _, _ in specs}
        seen = {key: False for key, _, _ in specs}
        for i in range(samples):
            batch = self.read_pins_batch(specs)
            for key, value in batch.items():
                if value is None:
                    continue
                seen[key] = True
                agg[key] = agg[key] or value
            if i < samples - 1:
                time.sleep(gap_s)
        return {key: (agg[key] if seen[key] else None) for key in agg}

    def write_serial(self, text):
        """Send text to the device's serial input. Lets a project drive firmware that takes commands
        over UART (this board accepts SET:PAYMENT / SET:SPD1 / D ... from its ESP32), which is often the
        fastest way to put firmware into a specific state for testing."""
        return self._tool("wokwi_write_serial", {"text": text})

    def read_serial(self, clear=False):
        return self._tool("wokwi_read_serial", {"clear": bool(clear)})

    def take_screenshot(self, part_id):
        """Ask the simulator what a display part actually shows. More trustworthy than reconstructing
        a display from its driver pins - decoding the 74HC595 shift register that way gave a moving
        "walking ones" pattern instead of a stable digit (see ROADMAP Phase 2c)."""
        return self._tool("wokwi_take_screenshot", {"partId": part_id}, timeout=20)

    def export_vcd(self, output_path):
        """Dump the logic-analyzer trace. This is the RIGHT way to read a PWM output: sampling a pin
        that's driven at, say, 39% duty gives a coin-flip answer every time (see ROADMAP Phase 2c),
        whereas the waveform tells you the true duty cycle and exact edge timing."""
        return self._tool("wokwi_export_vcd", {"outputPath": output_path}, timeout=30)

    def get_status(self):
        return self._tool("wokwi_get_status", {})

    def elapsed(self):
        return time.time() - self.started_at if self.started_at else 0

    def stop(self):
        try:
            self._tool("wokwi_stop_simulation", {}, timeout=10)
        except WokwiMcpError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        return self.elapsed()
