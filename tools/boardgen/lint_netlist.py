"""Netlist design-rule lint (stage `lint`): `lint_netlist.py <project-id>`. Pure Python, no KiCad process.
Reads PARTS + optional NET_SPEC from netlist.py, pin types from the symbol lib, pads from the footprint.
Rules: decoupling, polarity, led, short, pads, single-pin; for parts declared through the parts registry
(`registry_part`, docs/design/P1_PARTS_REGISTRY.md): PR-REF, PR-HASH, PR-TIER, PR-SYM, PR-PAD, PR-HOLE, PR-PKG-NAME.
`PARTS_STRICT = True` in netlist.py makes any part NOT declared through the registry a PR-REF error;
otherwise those parts keep the FAMILY-map fallback. Output: `ERROR|WARN rule ref/net: message`;
unjudgeable things are WARN. Exit 1 on any unwaived ERROR. Waivers: projects/<id>/waivers.json =
[{"check":"lint","rule":..,"refs":[..] | "nets":[..],"why":".."}]; unused waivers are reported as WARN."""
import json
import math
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                    # tools/
from boardgen import project as _project                      # noqa: E402
from boardgen import waivers as _waivers                      # noqa: E402
from boardgen import parts as _parts                          # noqa: E402
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


def footprint_pad_list(NL, fp_id):
    """[(pad name, smallest drill dimension in mm or None)] for every named pad (duplicates kept: SOT-223
    has two pads "2"), or None if the footprint file is missing."""
    if fp_id in _fp_cache:
        return _fp_cache[fp_id]
    lib, name = fp_id.split(":", 1)
    base = os.path.join(NL.PRJ_DIR, "lib") if lib in NL.PROJECT_LIBS else NL.KICAD_FOOTPRINTS
    path = os.path.join(base, lib + ".pretty", name + ".kicad_mod")
    out = None
    if os.path.isfile(path):
        tree = parse(open(path, encoding="utf-8").read())
        out = []
        for p in find_all(tree, "pad"):
            if str(p[1]) == "":
                continue
            dims = []
            for d in find_all(p, "drill"):
                for x in d[1:]:
                    try:
                        dims.append(float(x))
                    except (TypeError, ValueError):
                        pass                                  # the word "oval"
            dims = [v for v in dims if v > 0]
            out.append((str(p[1]), min(dims) if dims else None))
    _fp_cache[fp_id] = out
    return out


def footprint_pads(NL, fp_id):
    """Set of pad names (non-empty) in the footprint file, or None if the file is missing.
    A set collapses duplicates; the registry rules use footprint_pad_list (a multiset) instead."""
    lst = footprint_pad_list(NL, fp_id)
    return None if lst is None else {n for n, _d in lst}


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
        self.reg_refs = {}                                    # ref -> registry record id (registry_part parts)

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


def ic_supply_pins(M):
    """Yield (ref, supply_net or None, [pins], note) per IC (ref starts with U): one item per non-ground
    power_in net; note is "nosym" (symbol missing) or "nosupply" (no such pin) with net None. Shared with
    the PCB decap-distance check (decap_check.py)."""
    for ref, p in sorted(M.parts.items()):
        if not ref.startswith("U"):
            continue
        sp = symbol_pins(M.NL, p["lib_id"])
        if sp is None:
            yield ref, None, [], "nosym"
            continue
        supply = {}
        for pin, net in p["pins"].items():
            if sp.get(pin, ("", ""))[1] == "power_in" and not M.is_ground(net):
                supply.setdefault(net, []).append(pin)
        if not supply:
            yield ref, None, [], "nosupply"
        for net, pins in sorted(supply.items()):
            yield ref, net, sorted(pins), ""


def decoupling_caps(M):
    return [p for p in M.parts.values() if p["lib_id"].startswith("Device:C") and len(p["pins"]) == 2]


def rule_decoupling(M):
    caps = decoupling_caps(M)
    for ref, net, pins, note in ic_supply_pins(M):
        if note == "nosym":
            M.add("WARN", "decoupling", ref, "symbol %s not found, cannot judge supply pins" % M.parts[ref]["lib_id"],
                  refs=[ref])
        elif note == "nosupply":
            M.add("WARN", "decoupling", ref, "no power_in pin on a non-ground net, decoupling not judged",
                  refs=[ref])
        else:
            ok = any(net in c["pins"].values() and any(M.is_ground(n) for n in c["pins"].values())
                     for c in caps)
            if not ok:
                M.add("ERROR", "decoupling", "%s/%s" % (ref, net),
                      "supply pin %s on %s has no capacitor to GND" % (",".join(pins), net),
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
        if ref in M.reg_refs:
            continue                                          # registry parts: PR-* rules replace the FAMILY map
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


# ── registry rules (PR-*) ───────────────────────────────────────────────────────────────────────
HOLE_CLEARANCE_MM = 0.20                                      # drill must exceed lead size by this much
CLASS_OK = {                                                   # registry pin class -> KiCad electrical types accepted
    "power_in": {"power_in"}, "power_out": {"power_out"}, "input": {"input"}, "output": {"output", "tri_state"},
    "bidirectional": {"bidirectional", "tri_state"},
    "open_collector": {"open_collector", "output", "input", "passive"},
    "analog": {"passive", "input", "output", "bidirectional", "unspecified"}, "passive": {"passive", "unspecified"},
}


def _norm_name(n):
    return re.sub(r"[~{} ]", "", str(n)).upper()


def _squash(t):
    return re.sub(r"[-_ .]", "", t).lower()


def _plist(pins):
    return ",".join(sorted(pins, key=lambda s: (len(s), s)))


def _tht_lead(rec):
    """Lead size (mm; rectangular leads use the diagonal) or None if the record has none."""
    t = rec.get("tht") or {}
    if "lead_d_mm" in t:
        return float(t["lead_d_mm"])
    if "lead_mm" in t:
        w, th = (float(v) for v in t["lead_mm"])
        return math.hypot(w, th)
    return None


def rule_registry(M, reg_refs, rec_problems):
    """PR-REF/HASH/TIER/SYM/PAD/HOLE/PKG-NAME for every part declared through registry_part()."""
    reported = set()
    for ref in sorted(reg_refs):
        p, pid = M.parts.get(ref), reg_refs[ref]
        rec = _parts.registry().get(pid)
        if p is None or rec is None:
            continue
        for msg in rec_problems.get(pid, []):
            if (pid, msg) in reported:
                continue
            reported.add((pid, msg))
            rule = "PR-HASH" if "PR-HASH" in msg else "PR-TIER" if "PR-TIER" in msg else "PR-REF"
            M.add("ERROR", rule, pid, msg, refs=sorted(r for r, i in reg_refs.items() if i == pid))
        k = rec["kicad"]
        for what, have, want in (("symbol", p["lib_id"], k["symbol"]), ("footprint", p["footprint"], k["footprint"])):
            if have != want:
                M.add("ERROR", "PR-REF", ref, "%s %s differs from registry record %s (%s)" % (what, have, pid, want),
                      refs=[ref])
        # PR-SYM: KiCad symbol pins vs record pins
        sp = symbol_pins(M.NL, p["lib_id"])
        if sp is None:
            M.add("WARN", "PR-SYM", ref, "symbol %s not found, symbol pins not judged" % p["lib_id"], refs=[ref])
        else:
            for num, pin in sorted(rec["pins"].items(), key=lambda kv: (len(kv[0]), kv[0])):
                if num not in sp:
                    M.add("ERROR", "PR-SYM", ref, "registry (%s) has pin %s (%s) but symbol %s has no such pin"
                          % (pid, num, pin["name"], p["lib_id"]), refs=[ref])
                    continue
                sname, stype = sp[num]
                ok_names = {_norm_name(pin["name"]), _norm_name(pin.get("alias", pin["name"]))}
                if _norm_name(sname) not in ok_names:
                    M.add("ERROR", "PR-SYM", ref, "symbol pin %s is %s, registry (%s) says %s%s" % (
                        num, sname, pid, pin["name"], " (alias %s)" % pin["alias"] if pin.get("alias") else ""),
                        refs=[ref])
                elif pin.get("class") and stype not in CLASS_OK.get(pin["class"], {stype}):
                    M.add("WARN", "PR-SYM", ref, "symbol pin %s (%s) is type %s, registry says class %s"
                          % (num, sname, stype, pin["class"]), refs=[ref])
            extra = sorted(set(sp) - set(rec["pins"]))
            if extra:
                M.add("ERROR", "PR-SYM", ref, "symbol %s has pin(s) %s that registry (%s) lacks"
                      % (p["lib_id"], _plist(extra), pid), refs=[ref])
        # PR-PAD: footprint pad multiset
        fp = p["footprint"]
        pads = footprint_pad_list(M.NL, fp)
        if pads is None:
            M.add("ERROR", "PR-PAD", ref, "footprint %s not found" % fp, refs=[ref])
        else:
            have = Counter(n for n, _d in pads)
            want = Counter({n: int(k.get("fp_pad_copies", {}).get(n, 1)) for n in rec["pins"]})
            if have != want:
                def fmt(c):
                    return ",".join(n for n in sorted(c, key=lambda s: (len(s), s)) for _ in range(c[n]))
                M.add("ERROR", "PR-PAD", ref, "footprint pads %s but registry (%s) expects %s"
                      % (fmt(have), pid, fmt(want)), refs=[ref])
            missing = sorted(set(p["pins"]) - set(want))
            if missing:
                M.add("ERROR", "PR-PAD", ref, "netlist pin(s) %s are not pins of registry record %s"
                      % (_plist(missing), pid), refs=[ref])
        # PR-HOLE: THT drill vs lead
        if pads is not None and rec["package"].get("mount") == "tht" and rec["kind"] in ("part", "generic"):
            lead = _tht_lead(rec)
            if lead is None:
                M.add("WARN", "PR-HOLE", ref, "record %s is through-hole but has no lead size (tht), hole not judged"
                      % pid, refs=[ref])
            else:
                drills = [d for n, d in pads if n in rec["pins"]]
                if any(d is None for d in drills):
                    M.add("ERROR", "PR-HOLE", ref, "record %s is through-hole but footprint %s has a pad without a "
                          "drill" % (pid, fp), refs=[ref])
                elif drills and min(drills) < lead + HOLE_CLEARANCE_MM - 1e-9:
                    M.add("ERROR", "PR-HOLE", ref, "drill %.2f < lead %.2f + %.2f"
                          % (min(drills), lead, HOLE_CLEARANCE_MM), refs=[ref])
        # PR-PKG-NAME
        pkg = rec["package"].get("name", "")
        if pkg and _squash(pkg) not in _squash(fp.split(":", 1)[-1]):
            M.add("ERROR", "PR-PKG-NAME", ref, 'footprint name %s has no "%s" (record %s)'
                  % (fp.split(":", 1)[-1], pkg, pid), refs=[ref])


def rule_strict(M, reg_refs):
    for ref in sorted(set(M.parts) - set(reg_refs)):
        M.add("ERROR", "PR-REF", ref, "part %s (%s) is not declared through the registry (PARTS_STRICT)"
              % (ref, M.parts[ref]["lib_id"]), refs=[ref])


def prepare_registry():
    """Load every schema-valid record leniently into parts._registry (a record with a broken hash or tier
    stays usable so lint reports it per use instead of crashing the netlist import).
    Returns {record id: [problem messages]}."""
    recs, problems = {}, {}
    for f in sorted(_parts.RECORDS_DIR.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            errs = _parts.validate(rec, f.name)
        except ValueError as e:
            problems.setdefault(f.name, []).append("%s: (root): invalid JSON: %s" % (f.name, e))
            continue
        if errs:
            problems.setdefault(rec.get("id", f.name) if isinstance(rec, dict) else f.name, []).extend(errs)
            continue
        pid, msgs = rec["id"], []
        if rec["verification"] != "unverified" and rec.get("signed_hash") is None:
            msgs.append("%s: tier %s needs a signed_hash (PR-TIER)" % (pid, rec["verification"]))
        if rec["verification"] != "unverified" and not rec.get("evidence"):
            msgs.append("%s: tier %s needs at least one evidence entry (PR-TIER)" % (pid, rec["verification"]))
        if not _parts.hash_ok(rec):
            msgs.append("%s: signed fields changed since sign-off (PR-HASH)" % pid)
        recs.setdefault(pid, rec)
        if msgs:
            problems[pid] = msgs
    _parts._registry = recs
    return problems


class RegistryTrace:
    """Wraps parts.registry_part: remembers ref -> record id, and turns an unknown pin into a finding
    (the part dict is still built so later rules run). An unknown id is fatal: nothing to build from."""
    def __init__(self):
        self.refs, self.findings = {}, []
        self._orig = _parts.registry_part
        _parts.registry_part = self

    def __call__(self, ref, part_id, value, pins, group):
        try:
            d = self._orig(ref, part_id, value, pins, group)
        except _parts.RegistryError as e:
            rec = _parts.registry().get(part_id)
            msg = str(e) if str(e).startswith(ref + ":") else "%s: %s" % (ref, e)
            self.findings.append(Finding("ERROR", "PR-REF", ref, msg, refs=[ref]))
            if rec is None:
                raise
            d = dict(ref=ref, lib_id=rec["kicad"]["symbol"], value=value, footprint=rec["kicad"]["footprint"],
                     pins={str(k): v for k, v in pins.items() if v}, group=group,
                     lcsc=(rec.get("lcsc") or {}).get("id", ""))
        self.refs[ref] = part_id
        return d


def judged_by_family(M, ref):
    p = M.parts[ref]
    sym_lib, fp_lib = p["lib_id"].split(":", 1)[0], p["footprint"].split(":", 1)[0]
    if sym_lib in M.NL.PROJECT_LIBS or fp_lib in M.NL.PROJECT_LIBS:
        return False
    return any(re.search(rx, p["lib_id"]) for rx, _f in FAMILY)


# ── waivers ─────────────────────────────────────────────────────────────────────────────────────
def apply_waivers(project_id, findings):
    ws, problems = _waivers.load(project_id, "lint")
    extra = [Finding("ERROR", "waiver", t, m) for t, m in problems]
    for i, w in ws:
        used = False
        for f in findings:
            if f.sev == "ERROR" and f.waiver is None and _waivers.matches(w, f.rule, f.refs, f.nets):
                f.waiver, used = w, True
        if not used:
            extra.append(Finding("WARN", "waiver", "waivers.json[%d]" % i, "unused waiver (rule %r, %s)"
                                 % (w.get("rule"), _waivers.describe(w))))
    return extra


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: lint_netlist.py <project-id>")
    rec_problems = prepare_registry()
    trace = RegistryTrace()
    try:
        NL = _project.load_netlist(pid)
    except _parts.RegistryError:
        for f in trace.findings:
            print(f.line())
        print("FAILED: %d lint errors (netlist.py could not be built from the registry)" % len(trace.findings))
        return 1
    M = Model(NL)
    M.reg_refs = dict(trace.refs)
    M.findings += trace.findings
    for rule in (rule_spec, rule_decoupling, rule_polarity, rule_led, rule_short, rule_pads, rule_single_pin):
        rule(M)
    rule_registry(M, M.reg_refs, rec_problems)
    if getattr(NL, "PARTS_STRICT", False):
        rule_strict(M, M.reg_refs)
    M.findings += apply_waivers(pid, M.findings)
    for f in M.findings:
        print(f.line())
    fallback = [r for r in M.parts if r not in M.reg_refs and judged_by_family(M, r)]
    unjudged = [r for r in M.parts if r not in M.reg_refs and r not in fallback]
    print("parts examined: %d by registry, %d by FAMILY fallback, %d unjudged (no registry record, no family rule)"
          % (len(M.reg_refs), len(fallback), len(unjudged)))
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
