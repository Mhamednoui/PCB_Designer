"""Transient SPICE simulation of a whole board, straight from its netlist.py.

This is the live-simulation path for boards that have NO microcontroller (Wokwi only runs firmware,
so a 555 flasher, an analog filter or a power stage can't be simulated there). It builds an LTspice
netlist from the same `netlist.py` the schematic and PCB come from, runs it in batch mode, reads the
waveforms back and measures what each probed net is actually doing (frequency, duty cycle, levels)
plus the current through every LED.

    python tools/boardgen/make_spice.py blinky-555
    python tools/boardgen/make_spice.py blinky-555 --set VCC=12 --tstop 5

A project opts in with a `SPICE` dict in its netlist.py:

    SPICE = {
        "supplies": {"VCC": 9.0},            # DC source from each net to GND (overridable with --set)
        "tstop": 3.0,                          # seconds of simulated time
        "probes": ["OUT", "TRIG"],             # nets whose voltage to record and measure
        "expect": {"OUT": {"freq_hz": 1.39, "tol_pct": 10}},   # optional pass/fail against intent
    }

Every part must map to a SPICE model (see build_circuit). Connectors are skipped on purpose - the supplies
stand in for whatever plugs into them. Any OTHER unmapped part is a hard error: silently leaving a
part out would simulate a different circuit and still report success.

Writes projects/<id>/test/spice/transient.json (metrics + uniformly resampled waveforms), which the
webview's spice service serves and the frontend plays back.
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen.project import load_netlist, PROJECTS  # noqa: E402

# A generic red/green LED: Vf ~1.95 V at 15 mA. Good enough to size a series resistor and see the
# current; it is not a specific part's datasheet curve.
LED_MODEL = ".model LED_GENERIC D(Is=1e-22 N=1.6 Rs=2 BV=5 IBV=10u Cjo=10p)"
DIODE_MODEL = ".model D_GENERIC D(Is=2.5n N=1.75 Rs=0.5 BV=100 IBV=100n Cjo=4p)"

TIMERS_555 = {"Timer:NE555P", "Timer:NE555D", "Timer:NE555", "Timer:LM555xM", "Timer:LM555xN",
              "Timer:NA555D", "Timer:SE555D", "Timer:TLC555xD", "Timer:TLC555xP"}


def spice_value(value, kind):
    """KiCad value text -> SPICE number: '10uF'->'10u', '470R'->'470', '4k7'->'4.7k', '1M'->'1Meg'."""
    v = value.strip().replace("µ", "u").replace("Ω", "")
    v = re.sub(r"(?i)(f|ohm)$", "", v)
    m = re.fullmatch(r"(\d+)([RrKkMmUuNnPp])(\d+)", v)          # 4k7 / 4R7 style
    if m:
        mult = "" if m.group(2) in "Rr" else m.group(2)
        v = "%s.%s%s" % (m.group(1), m.group(3), mult)
    v = re.sub(r"[Rr]$", "", v)
    # SPICE reads 'M' as milli. For a resistor that is never what the value text meant.
    if kind == "R" and re.search(r"M$", v):
        v = v[:-1] + "Meg"
    if not re.fullmatch(r"\d+(\.\d+)?([a-zA-Z]+)?", v):
        raise SystemExit("can't read value %r as a %s" % (value, kind))
    return v


def node(net, names):
    """SPICE node name for a net. GND is node 0; anything with odd characters gets sanitised."""
    if net == "GND":
        return "0"
    n = re.sub(r"[^A-Za-z0-9_]", "_", net)
    names[n.lower()] = net
    return n


def element(letter, ref):
    """SPICE picks the element type from the first letter: R1 stays R1, but a ref like 'RV1' or
    'U1' needs the letter in front."""
    return ref if ref.upper().startswith(letter) and not ref[1:2].isalpha() else letter + ref


def build_circuit(nl, supplies, tstop):
    names = {}
    lines, models, skipped = [], set(), []
    for p in nl.PARTS:
        lib, ref, pins = p["lib_id"], p["ref"], p["pins"]
        pin = lambda k: node(pins.get(k, "NC_%s_%s" % (ref, k)), names)  # noqa: E731
        if lib.startswith("Connector") or lib.startswith("Mechanical"):
            skipped.append(ref)
        elif lib in ("Device:R", "Device:R_Small"):
            lines.append("%s %s %s %s" % (element("R", ref), pin("1"), pin("2"), spice_value(p["value"], "R")))
        elif lib in ("Device:C", "Device:C_Small", "Device:C_Polarized", "Device:CP"):
            lines.append("%s %s %s %s" % (element("C", ref), pin("1"), pin("2"), spice_value(p["value"], "C")))
        elif lib in ("Device:LED", "Device:LED_Small"):
            # KiCad Device:LED: pin 1 = K, pin 2 = A. SPICE D: anode first.
            lines.append("%s %s %s LED_GENERIC" % (element("D", ref), pin("2"), pin("1")))
            models.add(LED_MODEL)
        elif lib in ("Device:D", "Device:D_Small"):
            lines.append("%s %s %s D_GENERIC" % (element("D", ref), pin("2"), pin("1")))
            models.add(DIODE_MODEL)
        elif lib in TIMERS_555:
            # LTspice's own NE555 subcircuit takes pins 1..8 in DIP order - same as the KiCad symbol.
            lines.append("%s %s NE555" % (element("X", ref), " ".join(pin(str(i)) for i in range(1, 9))))
            models.add(".lib NE555.sub")
        else:
            raise SystemExit(
                "no SPICE model for %s (%s). Add it to build_circuit() in tools/boardgen/make_spice.py - "
                "never drop a part, that simulates a different circuit." % (ref, lib))

    for net, volts in supplies.items():
        lines.append("V_%s %s 0 %s" % (node(net, names), node(net, names), volts))

    maxstep = tstop / 20000.0
    deck = ["* %s - generated by tools/boardgen/make_spice.py from gen/netlist.py" % nl.PRJ_NAME]
    deck += lines + sorted(models)
    deck += [".tran 0 %g 0 %g startup" % (tstop, maxstep), ".options plotwinsize=0", ".end", ""]
    return "\n".join(deck), names, skipped


def find_ltspice():
    candidates = [os.environ.get("LTSPICE_PATH", ""),
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe"),
                  r"C:\Program Files\ADI\LTspice\LTspice.exe"]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    raise SystemExit("LTspice not found - install with `winget install AnalogDevices.LTspice` "
                     "or set LTSPICE_PATH")


def read_raw(path):
    """LTspice binary .raw: UTF-16LE header, then per point a float64 time + float32 per variable
    (all float64 if the 'double' flag is set). Time can carry a sign bit as a marker - use abs()."""
    with open(path, "rb") as f:
        data = f.read()
    marker = "Binary:\n".encode("utf-16-le")
    split = data.find(marker)
    if split < 0:
        raise SystemExit("%s is not a binary LTspice raw file" % path)
    header = data[:split].decode("utf-16-le")
    body = data[split + len(marker):]
    nvars = int(re.search(r"No\. Variables:\s*(\d+)", header).group(1))
    npts = int(re.search(r"No\. Points:\s*(\d+)", header).group(1))
    double = "double" in re.search(r"Flags:(.*)", header).group(1)
    var_block = header.split("Variables:")[-1].strip().splitlines()
    var_names = [ln.split("\t")[2] if ln.startswith("\t") else ln.split()[1]
                 for ln in var_block[:nvars]]
    fmt = "<" + ("d" * nvars if double else "d" + "f" * (nvars - 1))
    size = struct.calcsize(fmt)
    cols = [[] for _ in range(nvars)]
    for i in range(npts):
        row = struct.unpack_from(fmt, body, i * size)
        cols[0].append(abs(row[0]))
        for j in range(1, nvars):
            cols[j].append(row[j])
    return {name: col for name, col in zip(var_names, cols)}


def resample(t, y, n):
    """Uniform grid for playback - the solver's own timesteps are uneven."""
    out, j, tend = [], 0, t[-1]
    for k in range(n):
        tk = tend * k / (n - 1)
        while j < len(t) - 2 and t[j + 1] < tk:
            j += 1
        t0, t1 = t[j], t[j + 1]
        a = 0.0 if t1 == t0 else (tk - t0) / (t1 - t0)
        out.append(round(y[j] + a * (y[j + 1] - y[j]), 5))
    return out


def measure(t, y):
    # Levels come from the settled second half - the power-up transient (every node starting at 0 V)
    # would otherwise drag min and the switching threshold down, e.g. a 3-6 V timing ramp reads 0-6 V.
    settled = [v for tv, v in zip(t, y) if tv >= t[-1] / 2] or y
    lo, hi = min(settled), max(settled)
    m = {"min": round(lo, 4), "max": round(hi, 4)}
    if hi - lo < 1e-3:
        return m
    th = (lo + hi) / 2
    rises, falls = [], []
    for i in range(1, len(y)):
        if y[i - 1] < th <= y[i]:
            rises.append(t[i])
        elif y[i - 1] >= th > y[i]:
            falls.append(t[i])
    m["edges"] = len(rises) + len(falls)
    # The first cycle after power-up is longer (the timing cap starts from 0 V), so measure only
    # whole cycles after the first rising edge.
    if len(rises) >= 3:
        periods = [b - a for a, b in zip(rises[1:], rises[2:])]
        period = sum(periods) / len(periods)
        highs = [next((f for f in falls if f > r), None) for r in rises[1:-1]]
        highs = [f - r for r, f in zip(rises[1:-1], highs) if f]
        m["freq_hz"] = round(1 / period, 4)
        m["period_ms"] = round(period * 1000, 2)
        if highs:
            h = sum(highs) / len(highs)
            m["high_ms"] = round(h * 1000, 2)
            m["low_ms"] = round((period - h) * 1000, 2)
            m["duty_pct"] = round(100 * h / period, 1)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--set", action="append", default=[], metavar="NET=VOLTS",
                    help="override a supply voltage for this run")
    ap.add_argument("--tstop", type=float)
    ap.add_argument("--points", type=int, default=1500, help="resampled points per trace")
    args = ap.parse_args()

    nl = load_netlist(args.project)
    cfg = getattr(nl, "SPICE", None)
    if not cfg:
        raise SystemExit("project %r has no SPICE = {...} block in gen/netlist.py" % args.project)
    supplies = dict(cfg.get("supplies", {}))
    for s in args.set:
        net, _, volts = s.partition("=")
        if net not in supplies:
            raise SystemExit("--set %s: not a supply net (supplies: %s)" % (net, ", ".join(supplies)))
        supplies[net] = float(volts)
    tstop = args.tstop or float(cfg.get("tstop", 1.0))

    deck, names, skipped = build_circuit(nl, supplies, tstop)
    work = os.path.join(PROJECTS, args.project, "test", "spice")
    os.makedirs(work, exist_ok=True)
    cir = os.path.join(work, "transient.cir")
    with open(cir, "w", encoding="ascii") as f:
        f.write(deck)

    proc = subprocess.run([find_ltspice(), "-b", cir], capture_output=True, timeout=300)
    raw = os.path.splitext(cir)[0] + ".raw"
    if not os.path.isfile(raw):
        log = os.path.splitext(cir)[0] + ".log"
        detail = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
        raise SystemExit("LTspice produced no waveforms (exit %s)\n%s" % (proc.returncode, detail))
    vectors = read_raw(raw)
    # a few MB each and fully reproducible - transient.json is what's kept
    for leftover in (raw, os.path.splitext(cir)[0] + ".op.raw"):
        if os.path.isfile(leftover):
            os.remove(leftover)
    lookup = {k.lower(): k for k in vectors}
    t = vectors["time"]

    traces, metrics = {}, {}
    for net in cfg.get("probes", []):
        key = lookup.get("v(%s)" % node(net, names).lower())
        if not key:
            raise SystemExit("probe %r is not a node in the simulated circuit" % net)
        traces[net] = resample(t, vectors[key], args.points)
        metrics[net] = measure(t, vectors[key])
        metrics[net]["unit"] = "V"
    for p in nl.PARTS:
        if p["lib_id"] in ("Device:LED", "Device:LED_Small"):
            key = lookup.get("i(%s)" % element("D", p["ref"]).lower())
            if key:
                amps = [abs(a) * 1000 for a in vectors[key]]
                traces["I(%s)" % p["ref"]] = resample(t, amps, args.points)
                metrics["I(%s)" % p["ref"]] = {"peak_ma": round(max(amps), 2), "unit": "mA"}

    checks = []
    for net, want in cfg.get("expect", {}).items():
        got = metrics.get(net, {})
        for field, target in want.items():
            if field == "tol_pct":
                continue
            value = got.get(field)
            tol = want.get("tol_pct", 10)
            ok = value is not None and abs(value - target) <= abs(target) * tol / 100
            checks.append({"net": net, "field": field, "target": target, "value": value,
                           "tol_pct": tol, "ok": ok})

    result = {
        "project": args.project, "tstop_s": tstop, "points": args.points,
        "supplies": supplies, "skipped_parts": skipped,
        "metrics": metrics, "checks": checks, "ok": all(c["ok"] for c in checks),
        "traces": traces,
    }
    with open(os.path.join(work, "transient.json"), "w", encoding="utf-8") as f:
        json.dump(result, f)

    print("simulated %gs, supplies %s, connectors skipped: %s"
          % (tstop, supplies, ", ".join(skipped) or "none"))
    for net, m in metrics.items():
        print("  %-8s %s" % (net, {k: v for k, v in m.items() if k != "unit"}))
    for c in checks:
        print("  %s %s.%s = %s (target %s +/-%s%%)" % ("PASS" if c["ok"] else "FAIL", c["net"],
              c["field"], c["value"], c["target"], c["tol_pct"]))
    print("wrote %s" % os.path.join(work, "transient.json"))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
