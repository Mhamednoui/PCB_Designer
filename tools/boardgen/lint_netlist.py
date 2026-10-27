"""Netlist design-rule lint (stage `lint`): `lint_netlist.py <project-id>`. Pure Python, no KiCad process.
Reads PARTS + optional NET_SPEC from netlist.py, pin types from the symbol lib, pads from the footprint.
Rules: decoupling, polarity, led, short, pads, single-pin. Output: `ERROR|WARN rule ref/net: message`;
unjudgeable things are WARN. Exit 1 on any unwaived ERROR. Waivers: projects/<id>/waivers.json =
[{"check":"lint","rule":..,"refs":[..] | "nets":[..],"why":".."}]; unused waivers are reported as WARN."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                    # tools/
from boardgen import project as _project                      # noqa: E402
from boardgen.sexp import parse, find_all                      # noqa: E402
from sym_pins import _block                                    # noqa: E402

VF = 2.0                          # assumed LED forward voltage (V)
I_MIN_MA, I_MAX_MA = 1.0, 25.0
GROUND_RE = re.compile(r"^(GND|AGND|DGND|PGND|GNDA|GNDD|VSS|0V)$", re.I)
VOLT_RE = re.compile(r"^\+?(\d+)V(\d*)(?:_.*)?$", re.I)      # +5V, +3V3, +12V_REG ...

# (lib_id regex, allowed footprint-library regex): a symbol must not sit on a foreign footprint family.
FAMILY = [
    (r"^Device:R(_.*)?$", r"^Resistor_"),
    (r"^Device:C(_.*)?$", r"^Capacitor_"),
    (r"^Device:LED.*$", r"^LED_"),
    (r"^Device:D(_.*)?$", r"^Diode_"),
    (r"^Device:Fuse.*$", r"^Fuse"),
    (r"^Switch:", r"^Button_Switch_"),
    (r"^Connector", r"^(TerminalBlock|Connector)"),
    (r"^Transistor_", r"^Package_TO_SOT"),
    (r"^(Timer|74xx|Isolator|Amplifier_|Regulator_|Comparator|Interface_|MCU_)", r"^Package_"),
    (r"^Converter_DCDC:", r"^Converter_DCDC"),
]


class Finding:
    def __init__(self, sev, rule, target, msg, refs=(), nets=()):
        self.sev, self.rule, self.target, self.msg = sev, rule, target, msg
        self.refs, self.nets = set(refs), set(nets)
        self.waiver = None

    def line(self):
        tag = "WAIVED" if self.waiver is not None else self.sev
        tail = "  [waiver: %s]" % self.waiver["why"] if self.waiver is not None else ""
        return "%s %s %s: %s%s" % (tag, self.rule, self.target, self.msg, tail)


# ── library data ────────────────────────────────────────────────────────────────────────────────
_sym_cache, _fp_cache = {}, {}


def symbol_pins(NL, lib_id):
    """{pin number: (name, electrical type)} for lib_id; follows `extends`; None if not found."""
    if lib_id in _sym_cache:
        return _sym_cache[lib_id]
    lib, name = lib_id.split(":", 1)
    base = os.path.join(NL.PRJ_DIR, "lib") if lib in NL.PROJECT_LIBS else NL.KICAD_SYMBOLS
    path = os.path.join(base, lib + ".kicad_sym")
    out = None
    if os.path.isfile(path):
        text = open(path, encoding="utf-8").read()
        for _ in range(4):                                    # extends chain
            blk = _block(text, name)
            if blk is None:
                break
            ext = re.search(r'\(extends "([^"]+)"\)', blk)
            if ext:
                name = ext.group(1)
                continue
            out = {}
            starts = [m for m in re.finditer(r"\(pin\s+(\w+)\s+\w+", blk)]
            for i, m in enumerate(starts):
                seg = blk[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(blk)]
                n = re.search(r'\(number\s+"([^"]*)"', seg)
                nm = re.search(r'\(name\s+"([^"]*)"', seg)
                if n:
                    out[n.group(1)] = (nm.group(1) if nm else "", m.group(1))
            break
    _sym_cache[lib_id] = out
    return out


def footprint_pads(NL, fp_id):
    """Set of pad names (non-empty) in the footprint file, or None if the file is missing."""
    if fp_id in _fp_cache:
        return _fp_cache[fp_id]
    lib, name = fp_id.split(":", 1)
    base = os.path.join(NL.PRJ_DIR, "lib") if lib in NL.PROJECT_LIBS else NL.KICAD_FOOTPRINTS
    path = os.path.join(base, lib + ".pretty", name + ".kicad_mod")
    out = None
    if os.path.isfile(path):
        tree = parse(open(path, encoding="utf-8").read())
        out = {str(p[1]) for p in find_all(tree, "pad") if str(p[1]) != ""}
    _fp_cache[fp_id] = out
    return out


# ── electrical model ────────────────────────────────────────────────────────────────────────────
def parse_ohms(s):
    s = str(s).strip().replace("Ω", "R").replace(" ", "")
    m = re.fullmatch(r"(\d+)([kKMRr])(\d+)", s)               # 4k7, 2R2
    if m:
        v, mult = float("%s.%s" % (m.group(1), m.group(3))), m.group(2)
    else:
        m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKMRr]?)", s)
        if not m:
            return None
        v, mult = float(m.group(1)), m.group(2)
    return v * {"k": 1e3, "K": 1e3, "M": 1e6}.get(mult, 1.0)


class Model:
    def __init__(self, NL):
        self.NL = NL
        self.parts = {p["ref"]: p for p in NL.PARTS}
        self.nets = NL.nets()
        self.spec = getattr(NL, "NET_SPEC", {}) or {}
        self.findings = []

    def add(self, *a, **k):
        self.findings.append(Finding(*a, **k))

    def volts(self, net):
        """(lo, hi) volts for a net from NET_SPEC, else inferred from its name, else None."""
        s = self.spec.get(net)
        if isinstance(s, dict) and "v" in s:
            v = s["v"]
            if isinstance(v, (int, float)):
                return (float(v), float(v))
            if isinstance(v, (tuple, list)) and len(v) == 2:
                return (float(v[0]), float(v[1]))
        if GROUND_RE.match(net):
            return (0.0, 0.0)
        m = VOLT_RE.match(net)
        if m:
            x = float("%s.%s" % (m.group(1), m.group(2))) if m.group(2) else float(m.group(1))
            return (x, x)
        return None

    def is_ground(self, net):
        return bool(GROUND_RE.match(net))

    def is_resistor(self, ref):
        return self.parts[ref]["lib_id"].startswith("Device:R") and len(self.parts[ref]["pins"]) == 2

    def other_net(self, ref, net):
        for n in self.parts[ref]["pins"].values():
            if n != net:
                return n
        return net


# ── rules ───────────────────────────────────────────────────────────────────────────────────────
def rule_spec(M):
    for net, s in M.spec.items():
        if net not in M.nets:
            M.add("WARN", "spec", net, "NET_SPEC names a net that does not exist (typo?)", nets=[net])
        if not isinstance(s, dict):
            M.add("WARN", "spec", net, "NET_SPEC entry is not a dict, ignored", nets=[net])
            continue
        v = s.get("v")
        if v is not None and not (isinstance(v, (int, float)) or (
                isinstance(v, (tuple, list)) and len(v) == 2 and v[0] <= v[1])):
            M.add("WARN", "spec", net, "NET_SPEC 'v' must be a number or (min, max), ignored", nets=[net])


def rule_decoupling(M):
    caps = [p for p in M.parts.values() if p["lib_id"].startswith("Device:C") and len(p["pins"]) == 2]
    for ref, p in sorted(M.parts.items()):
        if not ref.startswith("U"):
            continue
        sp = symbol_pins(M.NL, p["lib_id"])
        if sp is None:
            M.add("WARN", "decoupling", ref, "symbol %s not found, cannot judge supply pins" % p["lib_id"],
                  refs=[ref])
            continue
        supply = {}
        for pin, net in p["pins"].items():
            if sp.get(pin, ("", ""))[1] == "power_in" and not M.is_ground(net):
                supply.setdefault(net, []).append(pin)
        if not supply:
            M.add("WARN", "decoupling", ref, "no power_in pin on a non-ground net, decoupling not judged",
                  refs=[ref])
        for net, pins in sorted(supply.items()):
            ok = any(net in c["pins"].values() and any(M.is_ground(n) for n in c["pins"].values())
                     for c in caps)
            if not ok:
                M.add("ERROR", "decoupling", "%s/%s" % (ref, net),
                      "supply pin %s on %s has no capacitor to GND" % (",".join(sorted(pins)), net),
                      refs=[ref], nets=[net])


def rule_polarity(M):
    for ref, p in sorted(M.parts.items()):
        fp = p["footprint"].split(":", 1)[-1]
        polar = p["lib_id"].startswith("Device:C_Polarized") or fp.startswith(("CP_", "C_Elec", "CP1_"))
        if not polar or len(p["pins"]) != 2:
            continue
        a, b = p["pins"].get("1"), p["pins"].get("2")        # pin/pad 1 is + in both symbol and CP_ footprints
        va, vb = M.volts(a) if a else None, M.volts(b) if b else None
        if va is None or vb is None:
            M.add("WARN", "polarity", ref, "voltage of %s unknown (declare it in NET_SPEC), polarity not judged"
                  % (a if va is None else b), refs=[ref], nets=[a, b])
        elif va[1] < vb[0]:
            M.add("ERROR", "polarity", ref, "+ pin 1 is on %s (%.3g V) but - pin 2 is on %s (%.3g V): reversed"
                  % (a, va[1], b, vb[0]), refs=[ref], nets=[a, b])


def _resolve(M, start, led_ref):
    """Walk from an LED terminal through lone series resistors to a net of known voltage.
    Returns ((lo, hi), ohms, chain) or (None, reason)."""
    net, ohms, seen, chain = start, 0.0, {led_ref}, []
    for _ in range(8):
        v = M.volts(net)
        if v:
            return v, ohms, chain
        others = [(r, pin) for r, pin in sorted(M.nets[net]) if r not in seen]
        if len(others) != 1 or not M.is_resistor(others[0][0]):
            return None, "net %s has no known voltage and is not a lone series resistor" % net, chain
        r = others[0][0]
        val = parse_ohms(M.parts[r]["value"])
        if val is None:
            return None, "resistor %s value %r not understood" % (r, M.parts[r]["value"]), chain
        ohms += val
        seen.add(r)
        chain.append(r)
        net = M.other_net(r, net)
    return None, "series chain too long", chain


def rule_led(M):
    for ref, p in sorted(M.parts.items()):
        if not p["lib_id"].startswith("Device:LED"):
            continue
        sp = symbol_pins(M.NL, p["lib_id"]) or {}
        anode = next((n for n, (nm, _t) in sp.items() if nm == "A"), "2")
        cath = next((n for n, (nm, _t) in sp.items() if nm == "K"), "1")
        an, cn = p["pins"].get(anode), p["pins"].get(cath)
        if not an or not cn:
            M.add("WARN", "led", ref, "anode/cathode pin not connected, LED not judged", refs=[ref])
            continue
        ra, rc = _resolve(M, an, ref), _resolve(M, cn, ref)
        bad = [r for r in (ra, rc) if r[0] is None]
        if bad:
            M.add("WARN", "led", ref, "cannot judge LED: " + bad[0][1] + " (declare it in NET_SPEC)",
                  refs=[ref], nets=[an, cn])
            continue
        (va, oa, ca), (vc, oc, cc) = ra, rc
        nets = [an, cn]
        if va[1] <= vc[0]:
            M.add("ERROR", "led", ref, "anode side (%s, <=%.3g V) is not above cathode side (%s, >=%.3g V): "
                  "LED reversed or never lit" % (an, va[1], cn, vc[0]), refs=[ref], nets=nets)
            continue
        total = oa + oc
        if total <= 0:
            M.add("ERROR", "led", ref, "no series resistor: LED sits directly between %s and %s" % (an, cn),
                  refs=[ref], nets=nets)
            continue
        i_hi = (va[1] - vc[0] - VF) / total * 1000.0
        i_lo = (va[0] - vc[1] - VF) / total * 1000.0
        path = "+".join(ca + cc) or "-"
        if i_hi > I_MAX_MA:
            M.add("ERROR", "led", ref, "estimated %.1f mA through %s (limit %g mA) at %.3g V over %g ohm"
                  % (i_hi, path, I_MAX_MA, va[1] - vc[0], total), refs=[ref] + ca + cc, nets=nets)
        elif i_hi < I_MIN_MA:
            M.add("ERROR", "led", ref, "estimated %.2f mA through %s (below %g mA, too dim)"
                  % (i_hi, path, I_MIN_MA), refs=[ref] + ca + cc, nets=nets)
        elif i_lo < I_MIN_MA:
            M.add("WARN", "led", ref, "at minimum supply the current drops to %.2f mA (below %g mA)"
                  % (i_lo, I_MIN_MA), refs=[ref], nets=nets)


def rule_short(M):
    for ref, p in sorted(M.parts.items()):
        if len(p["pins"]) >= 2 and len(set(p["pins"].values())) == 1:
            net = next(iter(p["pins"].values()))
            M.add("ERROR", "short", ref, "all %d connected pins are on net %s (part is shorted)"
                  % (len(p["pins"]), net), refs=[ref], nets=[net])


def rule_pads(M):
    unmapped = {}
    for ref, p in sorted(M.parts.items()):
        fp = p["footprint"]
        pads = footprint_pads(M.NL, fp)
        if pads is None:
            M.add("ERROR", "pads", ref, "footprint %s not found" % fp, refs=[ref])
            continue
        missing = sorted(set(p["pins"]) - pads)
        if missing:
            M.add("ERROR", "pads", ref, "pin(s) %s do not exist as pads in %s (has %s)"
                  % (",".join(missing), fp, ",".join(sorted(pads, key=lambda s: (len(s), s)))), refs=[ref])
        sp = symbol_pins(M.NL, p["lib_id"])
        if sp is None:
            M.add("WARN", "pads", ref, "symbol %s not found, pad count not judged" % p["lib_id"], refs=[ref])
        elif len(pads) < len(sp):
            M.add("ERROR", "pads", ref, "footprint %s has %d pads but symbol %s has %d pins"
                  % (fp, len(pads), p["lib_id"], len(sp)), refs=[ref])
        sym_lib, fp_lib = p["lib_id"].split(":", 1)[0], fp.split(":", 1)[0]
        if sym_lib in M.NL.PROJECT_LIBS or fp_lib in M.NL.PROJECT_LIBS:
            continue                                          # project-defined parts: pads checked above
        fam = next((f for rx, f in FAMILY if re.search(rx, p["lib_id"])), None)
        if fam is None:
            unmapped.setdefault(p["lib_id"], []).append(ref)
        elif not re.search(fam, fp_lib):
            M.add("ERROR", "pads", ref, "footprint %s is the wrong family for symbol %s (expected %s)"
                  % (fp, p["lib_id"], fam), refs=[ref])
    for lib_id, refs in sorted(unmapped.items()):
        M.add("WARN", "pads", ",".join(refs), "no footprint-family rule for %s (pad numbers/count still checked)"
              % lib_id, refs=refs)


def rule_single_pin(M):
    for net, members in sorted(M.nets.items()):
        if len(members) == 1:
            ref, pin = next(iter(members))
            M.add("ERROR", "single-pin", "%s/%s" % (ref, net),
                  "net %s touches only %s.%s" % (net, ref, pin), refs=[ref], nets=[net])


# ── waivers ─────────────────────────────────────────────────────────────────────────────────────
def apply_waivers(project_id, findings):
    path = os.path.join(_project.PROJECTS, project_id, "waivers.json")
    if not os.path.isfile(path):
        return []
    try:
        waivers = json.load(open(path, encoding="utf-8"))
        assert isinstance(waivers, list)
    except (ValueError, AssertionError) as e:
        return [Finding("ERROR", "waiver", "waivers.json", "unreadable or not a list: %s" % e)]
    extra = []
    for i, w in enumerate(waivers):
        if not isinstance(w, dict) or w.get("check", "lint") != "lint":
            continue
        tag = "waivers.json[%d]" % i
        if not str(w.get("why", "")).strip():
            extra.append(Finding("ERROR", "waiver", tag, "waiver for rule %r has no 'why'" % w.get("rule")))
            continue
        refs, nets = set(w.get("refs") or []), set(w.get("nets") or [])
        used = False
        for f in findings:
            if f.sev == "ERROR" and f.waiver is None and f.rule == w.get("rule") and \
                    ((refs and refs & f.refs) or (nets and nets & f.nets) or (not refs and not nets)):
                f.waiver, used = w, True
        if not used:
            extra.append(Finding("WARN", "waiver", tag, "unused waiver (rule %r, %s)"
                                 % (w.get("rule"), sorted(refs | nets) or "all")))
    return extra


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: lint_netlist.py <project-id>")
    M = Model(_project.load_netlist(pid))
    for rule in (rule_spec, rule_decoupling, rule_polarity, rule_led, rule_short, rule_pads, rule_single_pin):
        rule(M)
    M.findings += apply_waivers(pid, M.findings)
    for f in M.findings:
        print(f.line())
    errors = [f for f in M.findings if f.sev == "ERROR" and f.waiver is None]
    warns = [f for f in M.findings if f.sev == "WARN"]
    if errors:
        print("FAILED: %d lint errors" % len(errors))
        return 1
    print("lint OK: %s (%d parts, %d nets, %d warnings, %d waived)" % (
        pid, len(M.parts), len(M.nets), len(warns), sum(1 for f in M.findings if f.waiver is not None)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
