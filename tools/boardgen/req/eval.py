"""Executable requirements (P2-T9; spec docs/design/P2_ELECTRICAL_ANALYZER.md section 5). Pure Python, stdlib only.

    evaluate(ir, model=None) -> [result, ...]       one result dict per requirement, in REQUIREMENTS order

result = {id, kind, text, result, measured, evidence, why}; result is one of
    PASS            the requirement holds; `evidence` says how (the path found, the interval, the current)
    FAIL            the design violates it; `why` says where
    NOT_EVALUATED   the engine cannot judge it from the data it has (never PASS; blocks a pcba release, P2-T10)
    ERROR           the requirement itself is malformed (unknown ref/pin/net/kind, missing key): a bug in netlist.py

Kinds: path, path_absent (net-element graph), net_v (model interval), rail_peak (record load_ma sum), static_logic
(DC level -> LED/FET state), net_i and spice (not evaluable yet: NOT_EVALUATED with the reason).

Graph for path / path_absent: nodes are nets; resistors, inductors/ferrites, fuses, 0R links conduct both ways, diodes and
LEDs from anode to cathode only; capacitors, ICs, connectors, clamps never conduct. A part named in `with` as "on"
conducts (a FET between drain and source, anything else between all its pins) - that is how a closed switch or a
switched-on driver is stated. Ground-class nets are not traversed (everything meets there) unless an endpoint is on one or
the requirement says `via_ground: true`. `through` is a cut test: with every matching element deleted the target must no
longer be reachable.
"""
import json
import os
import re
import sys
from collections import deque

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from boardgen.elec.model import element_type, fmt, parse_resistance, R_TOL   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = ("PASS", "FAIL", "NOT_EVALUATED", "ERROR")
I_ON_MIN_MA = 1.0                      # an LED "conducts" for static_logic when its current is at least this (spec 5)

# kind -> (required keys, optional keys); id/kind/text are always required
KINDS = {
    "path": ({"from", "to"}, {"through", "with", "via_ground"}),
    "path_absent": ({"from", "to"}, {"with", "via_ground"}),
    "net_v": ({"net"}, {"min", "max"}),
    "net_i": ({"net"}, {"min", "max"}),
    "rail_peak": ({"net", "max_mA"}, {"basis"}),
    "static_logic": ({"when", "expect"}, set()),
    "spice": ({"scenario"}, {"expect"}),
}
_CLASS_OF = {"R": "resistor", "FUSE": "fuse", "L": "inductor", "DIODE": "diode", "LED": "diode", "CLAMP": "clamp",
             "FET": "fet", "CONN": "connector", "REG": "regulator", "C": "capacitor"}


class ReqError(Exception):
    """The requirement is malformed (reported as result ERROR, not as a crash)."""


def load_schema():
    with open(os.path.join(HERE, "schema.json"), encoding="utf-8") as f:
        return json.load(f)


def validate_shape(reqs):
    """List of 'path: message' problems for the REQUIREMENTS list as a whole (schema, ids, per-kind keys)."""
    from boardgen import parts as _parts
    errs = []
    if not isinstance(reqs, list):
        return ["REQUIREMENTS must be a list"]
    _parts._check(json.loads(json.dumps(reqs, default=list)), load_schema(), "", errs)
    out = ["%s: %s" % (p or "(root)", m) for p, m in errs]
    seen = set()
    for i, r in enumerate(reqs):
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if rid in seen:
            out.append("[%d].id: duplicate id %r" % (i, rid))
        seen.add(rid)
        spec = KINDS.get(r.get("kind"))
        if spec:
            for k in sorted(spec[0] - set(r)):
                out.append("%s: kind %s needs key %r" % (rid, r["kind"], k))
            for k in sorted(set(r) - spec[0] - spec[1] - {"id", "kind", "text"}):
                out.append("%s: key %r is not valid for kind %s" % (rid, k, r["kind"]))
    return out


# ---------------------------------------------------------------------------------------------------- the graph
class Graph:
    def __init__(self, ir, with_state):
        self.ir = ir
        self.parts = ir.get("parts", {})
        self.nets = ir.get("nets", {})
        self.edges = []                    # (ref, a, b, directed)
        for ref, p in self.parts.items():
            et = element_type(p)
            pins = [pin for _k, pin in sorted(p.get("pins", {}).items())]
            nets = [pin["net"] for pin in pins]
            state = with_state.get(ref)
            if state == "on":
                if et == "FET":
                    by = {pin.get("name"): pin["net"] for pin in pins}
                    if "D" in by and "S" in by:
                        self.edges.append((ref, by["D"], by["S"], False))
                else:
                    for i in range(len(nets)):
                        for j in range(i + 1, len(nets)):
                            self.edges.append((ref, nets[i], nets[j], False))
                continue
            if state == "off":
                continue
            if et in ("R", "L", "FUSE") and len(nets) == 2:
                self.edges.append((ref, nets[0], nets[1], False))
            elif et in ("DIODE", "LED") and len(nets) == 2:
                by = {pin.get("name"): pin["net"] for pin in pins}
                if "A" in by and "K" in by:
                    self.edges.append((ref, by["A"], by["K"], True))
                else:
                    self.edges.append((ref, nets[0], nets[1], False))

    def element_matches(self, ref, through):
        p = self.parts[ref]
        if isinstance(through, str):
            return ref == through
        if "ref" in through and ref == through["ref"]:
            return True
        if "refs" in through and ref in through["refs"]:
            return True
        c = through.get("class")
        if c is None:
            return False
        if c.startswith("ic:"):
            return p.get("registry") == c[3:]
        et = element_type(p)
        return c == _CLASS_OF.get(et) or (c == "led" and et == "LED")

    def reach(self, sources, skip, drop=None):
        """BFS over nets; returns parent map {net: (prev_net, ref) | None}. `drop(ref)` True = element deleted."""
        adj = {}
        for ref, a, b, directed in self.edges:
            if drop and drop(ref):
                continue
            adj.setdefault(a, []).append((b, ref))
            if not directed:
                adj.setdefault(b, []).append((a, ref))
        parent = {s: None for s in sources}
        q = deque(sources)
        while q:
            n = q.popleft()
            for m, ref in adj.get(n, []):
                if m in parent or m in skip:
                    continue
                parent[m] = (n, ref)
                q.append(m)
        return parent

    @staticmethod
    def trace(parent, end):
        steps = []
        n = end
        while parent[n] is not None:
            prev, ref = parent[n]
            steps.append("%s -[%s]-> %s" % (prev, ref, n))
            n = prev
        return list(reversed(steps))


def _endpoint(ir, ep):
    """Set of nets an endpoint ('ref.pin' by pad number or pin name, or a net name) stands for. ReqError when unknown."""
    if not isinstance(ep, str):
        raise ReqError("endpoint %r must be a string" % (ep,))
    nets = ir.get("nets", {})
    if ep in nets:
        return {ep}
    if "." in ep:
        ref, pin = ep.split(".", 1)
        part = ir.get("parts", {}).get(ref)
        if part is None:
            raise ReqError("endpoint %r: no part %s in the design" % (ep, ref))
        hit = {p["net"] for pad, p in part.get("pins", {}).items() if pad == pin}
        hit = hit or {p["net"] for p in part.get("pins", {}).values() if p.get("name") == pin}
        if not hit:
            raise ReqError("endpoint %r: %s has no pin %r (pads %s)" % (ep, ref, pin, ", ".join(sorted(part.get("pins", {})))))
        return hit
    raise ReqError("endpoint %r is neither a net of the design nor ref.pin" % ep)


def _with_state(ir, r):
    w = r.get("with") or {}
    for ref in w:
        if ref not in ir.get("parts", {}):
            raise ReqError("with: no part %s in the design" % ref)
    return w


def _through_check(ir, through):
    if isinstance(through, str):
        through = {"ref": through}
    if not isinstance(through, dict) or not (set(through) & {"class", "ref", "refs"}):
        raise ReqError("through must be {class: ...} or {ref: ...} or a ref string")
    for ref in ([through["ref"]] if "ref" in through else []) + list(through.get("refs", [])):
        if ref not in ir.get("parts", {}):
            raise ReqError("through: no part %s in the design" % ref)
    return through


def _skip_nets(ir, r, endpoints):
    if r.get("via_ground"):
        return set()
    return {n for n, d in ir.get("nets", {}).items() if d.get("class") == "ground"} - endpoints


# ---------------------------------------------------------------------------------------------------- kinds
def _path(ir, r, absent):
    src, dst = _endpoint(ir, r["from"]), _endpoint(ir, r["to"])
    g = Graph(ir, _with_state(ir, r))
    skip = _skip_nets(ir, r, src | dst)
    parent = g.reach(sorted(src), skip)
    hit = sorted(n for n in dst if n in parent)
    if absent:
        if hit:
            steps = g.trace(parent, hit[0])
            return "FAIL", None, "; ".join(steps) or "same net", "%s and %s are connected: %s" % (
                r["from"], r["to"], " ; ".join(steps) or "they are on the same net")
        return "PASS", None, "no conducting path: %d nets reachable from %s, none is %s" % (len(parent), r["from"], r["to"]), ""
    if not hit:
        return "FAIL", None, "", "no conducting path from %s to %s (%d nets reachable from the start)" % (r["from"], r["to"], len(parent))
    steps = g.trace(parent, hit[0])
    ev = " ; ".join(steps) or "same net"
    if "through" in r:
        th = _through_check(ir, r["through"])
        p2 = g.reach(sorted(src), skip, drop=lambda ref: g.element_matches(ref, th))
        bypass = sorted(n for n in dst if n in p2)
        if bypass:
            return "FAIL", None, ev, "a path from %s to %s avoids %s: %s" % (r["from"], r["to"], r["through"], " ; ".join(g.trace(p2, bypass[0])) or "same net")
        ev += "  (every path crosses %s)" % json.dumps(r["through"], sort_keys=True)
    return "PASS", None, ev, ""


def _net_v(ir, r, model):
    net = r["net"]
    if net not in ir.get("nets", {}):
        raise ReqError("net_v: no net %s in the design" % net)
    lo_ok, hi_ok = r.get("min"), r.get("max")
    if lo_ok is None and hi_ok is None:
        raise ReqError("net_v needs min and/or max")
    nm = model.nets[net]
    if nm.interval is None or nm.status == "NOT_JUDGED":
        return "NOT_EVALUATED", None, "", "net %s has no derived voltage (%s)" % (net, nm.reason or "model could not derive it")
    if nm.status == "claimed-only":
        return "NOT_EVALUATED", nm.interval, "", "net %s voltage is only NET_SPEC's claim %s, nothing derives it (%s)" % (net, fmt(nm.interval), nm.reason)
    iv = nm.interval
    bad = (lo_ok is not None and iv[0] < lo_ok - 1e-9) or (hi_ok is not None and iv[1] > hi_ok + 1e-9)
    ev = "model interval %s (%s)" % (fmt(iv), nm.status)
    if bad:
        return "FAIL", iv, ev, "net %s spans %s, outside the required %s..%s V" % (net, fmt(iv), lo_ok, hi_ok)
    return "PASS", iv, ev + " within %s..%s V" % (lo_ok, hi_ok), ""


def _rail_peak(ir, r):
    net = r["net"]
    if net not in ir.get("nets", {}):
        raise ReqError("rail_peak: no net %s in the design" % net)
    key = "peak" if r.get("basis", "peak") == "peak" else "typ"
    total, known, unknown = 0.0, [], []
    for pin in ir["nets"][net]["pins"]:
        ref, pad = pin.split(".", 1)
        part = ir["parts"][ref]
        if part["pins"][pad].get("class") != "power_in" or ref in [k[0] for k in known] or ref in unknown:
            continue
        lm = ((part.get("electrical") or {}).get("load_ma") or {}) if part.get("electrical_status") == "ok" else {}
        vals = [lm[k].get("max", lm[k].get("typ")) if isinstance(lm.get(k), dict) else None for k in (key, "typ")]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if vals:
            known.append((ref, vals[0]))
            total += vals[0]
        else:
            unknown.append(ref)
    ev = "sum of record load_ma (%s): %s = %.4g mA" % (key, " + ".join("%s %.4g" % kv for kv in known) or "none", total)
    if total > r["max_mA"] + 1e-9:
        return "FAIL", total, ev, "%.4g mA exceeds the %.4g mA budget on %s" % (total, r["max_mA"], net)
    if unknown or not known:
        return "NOT_EVALUATED", total, ev, "no load_ma in the record of %s: the sum is incomplete (so far %.4g mA of %.4g)" % (
            ", ".join(unknown) or "any part on the net", total, r["max_mA"])
    return "PASS", total, ev + " <= %.4g mA" % r["max_mA"], ""


def _level_of(ir, model, ep, want):
    nets = _endpoint(ir, ep)
    if len(nets) != 1:
        raise ReqError("when: %s names several nets" % ep)
    net = next(iter(nets))
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        return net, (float(want), float(want)), "%s = %.4g V (stated)" % (net, want)
    if isinstance(want, list) and len(want) == 2 and all(isinstance(x, (int, float)) for x in want):
        return net, (float(want[0]), float(want[1])), "%s = %s V (stated)" % (net, fmt(tuple(want)))
    if want not in ("high", "low"):
        raise ReqError("when: %s must be high, low, a voltage or [min, max]" % ep)
    lv = (model.nets[net].levels or {}).get(want)
    if lv is None:
        return net, None, "net %s has no %s level in the model (%s)" % (net, want, model.nets[net].reason or "driver has no usable VOH/VOL")
    return net, tuple(lv), "%s %s = %s (driver VOH/VOL)" % (net, want, fmt(tuple(lv)))


def _static_logic(ir, r, model):
    drive, notes = {}, []
    for ep, want in r["when"].items():
        net, iv, note = _level_of(ir, model, ep, want)
        if iv is None:
            return "NOT_EVALUATED", None, "", note
        drive[net] = iv
        notes.append(note)
    res, ev = "PASS", list(notes)
    for ref, state in sorted(r["expect"].items()):
        if ref not in ir["parts"]:
            raise ReqError("expect: no part %s in the design" % ref)
        et = element_type(ir["parts"][ref])
        if et == "LED":
            verdict, line = _led_state(ir, model, ref, state, drive)
        elif et == "FET":
            verdict, line = _fet_state(ir, model, ref, state, drive)
        else:
            raise ReqError("expect: %s is a %s; static_logic judges LEDs and FETs" % (ref, et))
        ev.append(line)
        if verdict == "FAIL":
            return "FAIL", None, "; ".join(ev), line
        if verdict == "NOT_EVALUATED":
            res = "NOT_EVALUATED"
    if res == "NOT_EVALUATED":
        return res, None, "; ".join(ev), ev[-1]
    return res, None, "; ".join(ev), ""


def _volt(model, drive, net):
    """(interval, series-ohm interval) of the source behind `net` in a series chain, or None."""
    if net in drive:
        return drive[net]
    nm = model.nets.get(net)
    if nm is not None and nm.interval is not None and nm.status == "derived" and nm.ir_class in ("ground", "power"):
        return nm.interval
    return None


def _side(ir, model, drive, net, skip_ref):
    """The source behind an LED terminal net: directly, or through exactly one resistor. -> (iv, (rmin, rmax), text) | None"""
    v = _volt(model, drive, net)
    if v is not None:
        return v, (0.0, 0.0), net
    rs = []
    for pin in ir["nets"][net]["pins"]:
        ref = pin.split(".", 1)[0]
        if ref != skip_ref and element_type(ir["parts"][ref]) == "R" and ref not in [x[0] for x in rs]:
            ohm = parse_resistance(ir["parts"][ref].get("value", ""))
            pads = ir["parts"][ref]["pins"]
            far = [p["net"] for p in pads.values() if p["net"] != net]
            if ohm and len(far) == 1:
                rs.append((ref, ohm, far[0]))
    if len(rs) != 1:
        return None
    ref, ohm, far = rs[0]
    v = _volt(model, drive, far)
    if v is None:
        return None
    return v, (ohm * (1 - R_TOL), ohm * (1 + R_TOL)), "%s via %s (%s)" % (far, ref, ir["parts"][ref]["value"])


def _led_state(ir, model, ref, state, drive):
    part = ir["parts"][ref]
    by = {p.get("name"): p["net"] for p in part["pins"].values()}
    if "A" not in by or "K" not in by:
        return "NOT_EVALUATED", "%s: anode/cathode pins not named A/K" % ref
    el = part.get("electrical") if part.get("electrical_status") == "ok" else None
    vfs = (el or {}).get("vf") or []
    hi = [x.get("max", x.get("typ")) for x in vfs if isinstance(x.get("max", x.get("typ")), (int, float))]
    lo = [x["min"] for x in vfs if isinstance(x.get("min"), (int, float))]
    if not hi:
        return "NOT_EVALUATED", "%s (%s) has no Vf in its record" % (ref, part.get("value"))
    vfmin, vfmax = (min(lo) if lo else 0.0), max(hi)
    a, k = _side(ir, model, drive, by["A"], ref), _side(ir, model, drive, by["K"], ref)
    if a is None or k is None:
        return "NOT_EVALUATED", "%s: cannot find the source behind its %s (needs a driven or derived net directly or through one resistor)" % (
            ref, "anode" if a is None else "cathode")
    rmin, rmax = a[1][0] + k[1][0], a[1][1] + k[1][1]
    if rmax <= 0:
        return "NOT_EVALUATED", "%s has no series resistor: the current is not defined by the DC levels" % ref
    i_min = max(0.0, (a[0][0] - vfmax - k[0][1]) / rmax * 1000.0)
    i_max = max(0.0, (a[0][1] - vfmin - k[0][0]) / max(rmin, 1e-9) * 1000.0)
    txt = "%s from %s to %s: I = %.3g..%.3g mA (Vf %.3g..%.3g V, R %.0f..%.0f ohm)" % (ref, a[2], k[2], i_min, i_max, vfmin, vfmax, rmin, rmax)
    if state == "on":
        if i_min >= I_ON_MIN_MA:
            return "PASS", txt + " >= %g mA: conducts" % I_ON_MIN_MA
        return "FAIL", txt + " does not reach %g mA at its worst corner: not guaranteed on" % I_ON_MIN_MA
    if i_max < 0.1:
        return "PASS", txt + " < 0.1 mA: off"
    return "FAIL", txt + " can still conduct: not off"


def _fet_state(ir, model, ref, state, drive):
    part = ir["parts"][ref]
    by = {p.get("name"): p["net"] for p in part["pins"].values()}
    el = part.get("electrical") if part.get("electrical_status") == "ok" else None
    vth = (el or {}).get("vth")
    lo = vth.get("min", vth.get("typ")) if isinstance(vth, dict) else None
    hi = vth.get("max", vth.get("typ")) if isinstance(vth, dict) else None
    if lo is None or hi is None or not {"G", "S"} <= set(by):
        return "NOT_EVALUATED", "%s has no gate threshold in its record" % ref
    g, s = _volt(model, drive, by["G"]), _volt(model, drive, by["S"])
    if g is None or s is None:
        return "NOT_EVALUATED", "%s: gate or source voltage is not known" % ref
    vgs = (g[0] - s[1], g[1] - s[0])
    txt = "%s Vgs = %.3g..%.3g V, Vth %.3g..%.3g V" % (ref, vgs[0], vgs[1], lo, hi)
    if state == "on":
        return ("PASS", txt + ": on") if vgs[0] > hi else ("FAIL", txt + ": not guaranteed on")
    return ("PASS", txt + ": off") if vgs[1] < lo else ("FAIL", txt + ": not guaranteed off")


# ---------------------------------------------------------------------------------------------------- entry point
def evaluate_one(ir, r, model):
    kind = r["kind"]
    if kind == "path":
        return _path(ir, r, False)
    if kind == "path_absent":
        return _path(ir, r, True)
    if kind == "net_v":
        return _net_v(ir, r, model)
    if kind == "rail_peak":
        return _rail_peak(ir, r)
    if kind == "static_logic":
        return _static_logic(ir, r, model)
    if kind == "net_i":
        if r["net"] not in ir.get("nets", {}):
            raise ReqError("net_i: no net %s in the design" % r["net"])
        return "NOT_EVALUATED", None, "", "net_i needs the current model (P2-T6 budget); not evaluable yet"
    if kind == "spice":
        return "NOT_EVALUATED", None, "", "spice requirements are a stub: delegate to make_spice once a scenario exists"
    raise ReqError("unknown kind %r" % kind)


def evaluate(ir, model=None):
    """Evaluate every requirement of `ir['requirements']`; never raises for a bad requirement (that is result ERROR)."""
    from boardgen.elec.model import build_model
    reqs = ir.get("requirements") or []
    if model is None:
        model = build_model(ir)
    shape = validate_shape(reqs)
    bad_idx = set()
    for msg in shape:
        m = re.match(r"\[(\d+)\]", msg)
        if m:
            bad_idx.add(int(m.group(1)))
    out = []
    for i, r in enumerate(reqs):
        res = {"id": r.get("id", "#%d" % i) if isinstance(r, dict) else "#%d" % i,
               "kind": r.get("kind") if isinstance(r, dict) else None,
               "text": r.get("text", "") if isinstance(r, dict) else "", "result": "ERROR", "measured": None,
               "evidence": "", "why": ""}
        mine = [m for m in shape if m.startswith("[%d]" % i) or m.startswith(res["id"] + ":")]
        if not isinstance(r, dict):
            mine = ["requirement must be an object"]
        if mine or i in bad_idx:
            res["why"] = "malformed: " + "; ".join(mine)
            out.append(res)
            continue
        try:
            verdict, measured, evidence, why = evaluate_one(ir, r, model)
            res.update(result=verdict, measured=measured, evidence=evidence, why=why)
        except ReqError as e:
            res["why"] = "malformed: %s" % e
        out.append(res)
    return out


def summary(results):
    return {k: sum(1 for x in results if x["result"] == k) for k in RESULTS}
