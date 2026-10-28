"""Electrical model v1 (P2-T3; spec docs/design/P2_ELECTRICAL_ANALYZER.md sections 1, 2 and 4). Pure Python, stdlib only.

    python -m boardgen.elec.model <project> [--net NAME] [--summary] [--json]      (cwd = tools/, or put tools/ on PYTHONPATH)
    python tools/boardgen/elec/model.py <project> --net VCC                         (same, from the repo root)

Input: the design IR (`out/design.json`, ir_version 2: parts with per-pin class / io, nets with NET_SPEC `v`, `external`).
Output: `build_model(ir)` -> `ElecModel`; `model.nets[name]` is a `NetModel` with

    interval   [lo, hi] volts (worst case over tolerances) or None
    status     "derived"      the interval was computed from sources (see `path`; `assumes` lists nets that were taken
                              from NET_SPEC without a derivation)
               "claimed-only" NET_SPEC says [a, b] and nothing derives it: kept as an assumption (INFO "assumed")
               "conflict"     NET_SPEC and the derivation disagree (the derived interval is not inside the claim)
               "NOT_JUDGED"   no derivation and no claim; `reason` says why (fail closed, spec section 4)
    path       the derivation, one line per step (what `--net` prints)
    reason     why not derived (claimed-only / NOT_JUDGED) or what disagrees (conflict)
    drivers / receivers / supply_sources / supply_sinks   terminals on the net with their classes (spec 2.3)
    pull       default state from pull resistors, {"state": "high"|"low"|None, "resistors": [...]}
    levels     {"low": [lo, hi], "high": [lo, hi]} for a net driven by a push-pull output with usable VOH/VOL data

How a rule gets it: `ctx.model` in a rule registered with `needs=("electrical", ...)` (rules/engine.py builds it lazily,
once per run); `ctx.ir["electrical"]` is `model.to_dict()`.  Direct use: `build_model(ir)`.

Sources, in order (a net takes the first definite one; claims are only a fallback): ground-class nets = 0 V;
connector pins declared in EXTERNAL with `v`; regulator outputs from the record (`electrical.regulator`), valid when the
input interval is inside the regulator's Vin range and has the dropout headroom; then propagation through passives:
0R/inductor/ferrite/fuse = same node (no drop assumed), series resistor with no DC load (drop = I*R only where the load's
record gives `load_ma`), divider (divider.py), diode/LED Vf (series or clamp against a resistor), MOSFET channel when
the gate state is fixed (both states otherwise: the drain/source is then not derived), push-pull output swing.
Capacitors are open at DC.  Dynamic behaviour (RC settling, oscillation, feedback, startup) is out of scope: SPICE.

Two passes: first only real sources are used; then NET_SPEC claims are used as ASSUMED inputs (so a net derived from an
assumed rail is "derived" with `assumes` listing the rail, and its own claim is checked against the derivation).  A claim
that two nets would derive from each other stays claimed-only (no circular "derivation").

Tolerance: resistors are +-5 % (generic default - the registry has no per-MPN tolerance; recorded in the path).  Vf lower
bound is 0 V when the record gives no minimum.  Level data (VOH/VOL) are used only when measured within 10 % of the
actual supply range, or when given as a ratio of VDD.
"""
import json
import os
import re
import sys

if __package__ in (None, ""):                                    # run as a script: python tools/boardgen/elec/model.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from boardgen.elec import divider                                # noqa: E402

R_TOL = 0.05                       # generic resistor tolerance (registry has none per MPN)
LEVEL_SUPPLY_TOL = 0.10            # a VOH/VOL datum measured at VCC counts if VCC is within 10 % of the supply interval
EPS = 1e-9
STATUSES = ("derived", "claimed-only", "conflict", "NOT_JUDGED")
HIGH_THRESHOLD_V = 1.0             # pull target at or above this = pulls HIGH; at or below LOW_THRESHOLD_V = pulls LOW
LOW_THRESHOLD_V = 0.3


# ---------------------------------------------------------------------------------------------------- intervals
def hull(a, b):
    return (min(a[0], b[0]), max(a[1], b[1]))


def contains(outer, inner):
    return outer[0] - EPS <= inner[0] and inner[1] <= outer[1] + EPS


def overlaps(a, b):
    return a[0] <= b[1] + EPS and b[0] <= a[1] + EPS


def fmt(iv):
    if iv is None:
        return "?"
    lo, hi = iv
    return "%.4g V" % lo if abs(hi - lo) < 1e-9 else "%.4g..%.4g V" % (lo, hi)


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


_RES_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmM]?)\s*(?:[RrΩ]|ohms?)?\s*(\d*)\s*$")


def parse_resistance(value):
    """'470R' '10k' '4.7k' '2k2' '1M' '0R' '100' -> ohms, None when it is not a resistance."""
    s = str(value).strip().replace("Ω", "R").replace("Ω", "R")
    m = re.match(r"^(\d+)([kKMR])(\d+)$", s)                                      # 2k2, 4R7
    if m:
        mult = {"k": 1e3, "K": 1e3, "M": 1e6, "R": 1.0}[m.group(2)]
        return float("%s.%s" % (m.group(1), m.group(3))) * mult
    m = _RES_RE.match(s)
    if not m or m.group(3):
        return None
    mult = {"": 1.0, "k": 1e3, "K": 1e3, "m": 1e-3, "M": 1e6}[m.group(2)]
    return float(m.group(1)) * mult


def _datum_range(d, supply=None):
    """(min, max) volts from a record datum; strings 'ratio:k*vdd[+-c]' are evaluated against the supply interval
    (min field with the supply's low corner, max field with its high corner). None when not evaluable."""
    if not isinstance(d, dict):
        return None
    out = []
    for key, corner in (("min", 0), ("max", 1)):
        v = d.get(key)
        if isinstance(v, str):
            m = re.match(r"^ratio:([0-9.]+)\*vdd([+-][0-9.]+)?$", v)
            if not m or supply is None:
                return None
            v = float(m.group(1)) * supply[corner] + float(m.group(2) or 0)
        out.append(_num(v))
    return tuple(out)


# ---------------------------------------------------------------------------------------------------- element typing
_R_LIBS = ("Device:R", "Device:R_Small", "Device:R_US", "Device:R_Small_US")


def element_type(part):
    """R C L FUSE LED DIODE CLAMP REG FET CONN MECH IC OTHER for a part dict of the IR."""
    lib, ref = part.get("lib_id", ""), part.get("ref", "")
    el = part.get("electrical") or {}
    role = el.get("role")
    kind = part.get("kind")
    if kind == "mechanical":
        return "MECH"
    if lib in _R_LIBS or role == "resistor":
        return "R"
    if lib == "Device:C" or lib.startswith("Device:C_"):
        return "C"
    if lib == "Device:L" or lib.startswith("Device:L_") or lib.startswith("Device:Ferrite"):
        return "L"
    if lib.startswith("Device:Fuse") or lib.startswith("Device:Polyfuse") or role == "fuse":
        return "FUSE"
    if lib.startswith("Device:LED") or role == "led":
        return "LED"
    if lib in ("Device:D_Zener", "Device:D_TVS", "Device:D_TVS_Dual") or role == "clamp" or "TVS" in lib:
        return "CLAMP"
    if lib.startswith("Device:D") or role == "rectifier":
        return "DIODE"
    if role == "regulator":
        return "REG"
    if role == "mosfet":
        return "FET"
    if kind == "connector":
        return "CONN"
    if kind == "generic" and ref[:1] in "RCLDFQ":
        return "OTHER"
    return "IC"


def _tid(ref, pad):
    return "%s.%s" % (ref, pad)


# ---------------------------------------------------------------------------------------------------- result objects
class NetModel:
    def __init__(self, name, ir_class, claim):
        self.name, self.ir_class, self.claim = name, ir_class, claim
        self.interval = None
        self.status = "NOT_JUDGED"
        self.reason = ""
        self.reason_kind = ""              # external | divider | no-vf | driver | regulator | load | no-dc-source | upstream-unknown | circular | other
        self.path = []
        self.assumes = []
        self.source = None                 # ground | external | regulator | short | resistor | divider | diode | fet | driver | claim
        self.state_dependent = False
        self.notes = []
        self.drivers, self.receivers, self.supply_sources, self.supply_sinks = [], [], [], []
        self.unclassified = []
        self.pull = None
        self.levels = None
        self.pins = []

    def to_dict(self):
        def r(iv):
            return None if iv is None else [round(iv[0], 6), round(iv[1], 6)]
        return {"name": self.name, "class": self.ir_class, "status": self.status, "interval": r(self.interval),
                "claimed": r(self.claim), "reason": self.reason, "reason_kind": self.reason_kind, "path": list(self.path), "assumes": list(self.assumes),
                "source": self.source, "state_dependent": self.state_dependent, "notes": list(self.notes),
                "drivers": self.drivers, "receivers": self.receivers, "supply_sources": self.supply_sources,
                "supply_sinks": self.supply_sinks, "unclassified": self.unclassified, "pull": self.pull,
                "levels": {k: r(v) for k, v in self.levels.items()} if self.levels else None}


class ElecModel:
    def __init__(self, project, nets, elements):
        self.project, self.nets, self.elements = project, nets, elements

    def counts(self):
        c = {s: 0 for s in STATUSES}
        for n in self.nets.values():
            c[n.status] += 1
        return c

    def reason_counts(self, status="NOT_JUDGED"):
        """{reason kind: [net names]} for the nets with this status (NOT_JUDGED or claimed-only): what is missing."""
        out = {}
        for n in self.nets.values():
            if n.status == status:
                out.setdefault(n.reason_kind or "other", []).append(n.name)
        return dict(sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0])))

    def to_dict(self):
        return {"project": self.project, "counts": self.counts(),
                "nets": {k: self.nets[k].to_dict() for k in sorted(self.nets)}}

    def explain(self, net):
        n = self.nets.get(net)
        if n is None:
            return "no net %r (nets: %s)" % (net, ", ".join(sorted(self.nets)[:12]) + (" ..." if len(self.nets) > 12 else ""))
        out = ["net %s  [%s]  %s%s" % (n.name, n.status, fmt(n.interval) if n.interval else "no interval",
                                       "   (NET_SPEC claims %s)" % fmt(n.claim) if n.claim else "")]
        if n.status == "claimed-only":
            out.append("  INFO assumed, not derived: %s" % (n.reason or "no derivation applies"))
        elif n.status in ("NOT_JUDGED", "conflict"):
            out.append("  %s: %s" % ("NOT_JUDGED" if n.status == "NOT_JUDGED" else "CONFLICT", n.reason))
        if n.assumes:
            out.append("  assumes (taken from NET_SPEC, not derived): %s" % ", ".join(n.assumes))
        if n.state_dependent:
            out.append("  state-dependent: yes (a switch/FET state is not fixed)")
        if n.path:
            out.append("  derivation:")
            out += ["    %d. %s" % (i, s) for i, s in enumerate(n.path, 1)]
        for title, items in (("drivers", n.drivers), ("receivers", n.receivers),
                             ("supply sources", n.supply_sources), ("supply sinks", n.supply_sinks)):
            if items:
                out.append("  %s: %s" % (title, "; ".join("%s (%s)" % (t["term"], t["kind"]) for t in items)))
        if n.pull:
            out.append("  pull: %s via %s" % (n.pull["state"] or "biased/undetermined",
                                              ", ".join("%s -> %s" % (p["ref"], p["to"]) for p in n.pull["resistors"])))
        if n.levels:
            out.append("  levels: low %s, high %s" % (fmt(n.levels["low"]), fmt(n.levels["high"])))
        for s in n.notes:
            out.append("  note: " + s)
        return "\n".join(out)


# ---------------------------------------------------------------------------------------------------- the builder
class _Builder:
    def __init__(self, ir):
        self.ir = ir
        self.parts = ir.get("parts", {})
        self.ext = ir.get("external") or {"declared": False, "pins": {}, "none": []}
        self.nets = {}
        for name, n in sorted(ir.get("nets", {}).items()):
            v = n.get("v")
            self.nets[name] = NetModel(name, n.get("class"), None if v is None else (float(v[0]), float(v[1])))
        self.etype = {ref: element_type(p) for ref, p in self.parts.items()}
        self.att = {name: [] for name in self.nets}           # net -> attachments
        self.res = {}                                         # ref -> {"nets", "r", "value"}
        self.short = []                                       # (ref, text, n1, n2)
        self.dio = {}                                         # ref -> {"a","k","vf","why","type","value"}
        self.fet = {}                                         # ref -> {...}
        self.reg = {}                                         # ref -> {...}
        self.fet_state = {}                                   # ref -> "on" | "off" | "both"
        self.why = {}                                         # net -> [(priority, text, kind)]
        self.use_claims = False
        self.claim_view = {}                                  # net -> True when vget used the claim (for assumes)
        self._scan()

    # -- scanning ---------------------------------------------------------------------------------------
    def _scan(self):
        for ref in sorted(self.parts):
            p = self.parts[ref]
            et = self.etype[ref]
            for pad, pin in sorted(p.get("pins", {}).items()):
                net = pin.get("net")
                if net not in self.att:
                    self.att[net] = []
                    self.nets[net] = NetModel(net, None, None)
                self.att[net].append({"ref": ref, "pad": pad, "term": _tid(ref, pad), "name": pin.get("name"),
                                      "cls": pin.get("class"), "et": et, "io": pin.get("io"), "part": p})
                self.nets[net].pins.append(_tid(ref, pad))
            if et == "R":
                self._scan_resistor(ref, p)
            elif et in ("L", "FUSE"):
                ns = [pin["net"] for _k, pin in sorted(p["pins"].items())]
                if len(ns) == 2 and ns[0] != ns[1]:
                    self.short.append((ref, "%s %s (same DC node, no drop assumed)" % (ref, "fuse" if et == "FUSE" else "inductor/ferrite"),
                                       ns[0], ns[1]))
            elif et in ("DIODE", "LED"):
                self._scan_diode(ref, p, et)
            elif et == "FET":
                self._scan_fet(ref, p)
            elif et == "REG":
                self._scan_reg(ref, p)
        self._terminals()

    def _scan_resistor(self, ref, p):
        pins = [pin for _k, pin in sorted(p["pins"].items())]
        ohm = parse_resistance(p.get("value", ""))
        if len(pins) != 2 or pins[0]["net"] == pins[1]["net"]:
            return
        if ohm is None:
            return                                           # unparseable value: stays an unknown load
        if ohm == 0:
            self.short.append((ref, "%s 0R link (same DC node)" % ref, pins[0]["net"], pins[1]["net"]))
            return
        self.res[ref] = {"nets": (pins[0]["net"], pins[1]["net"]), "r": divider.resistance(ohm, R_TOL), "value": p["value"]}

    def _scan_diode(self, ref, p, et):
        by = {pin.get("name"): pin["net"] for pin in p["pins"].values()}
        a, k = by.get("A"), by.get("K")
        d = {"a": a, "k": k, "type": et, "value": p.get("value", ""), "vf": None, "why": ""}
        el = p.get("electrical") if p.get("electrical_status") == "ok" else None
        vfs = (el or {}).get("vf") or []
        highs = [_num(x.get("max")) if _num(x.get("max")) is not None else _num(x.get("typ")) for x in vfs]
        highs = [h for h in highs if h is not None]
        lows = [_num(x.get("min")) for x in vfs if _num(x.get("min")) is not None]
        if a is None or k is None:
            d["why"] = "%s: anode/cathode pins are not named A/K" % ref
        elif not highs:
            d["why"] = "%s (%s) has no Vf in its record (%s)" % (ref, p.get("value"), "value not covered by the family record"
                                                                  if p.get("electrical_status") == "value_not_covered" else "no vf datum")
        else:
            d["vf"] = (min(lows) if lows else 0.0, max(highs))
        self.dio[ref] = d

    def _scan_fet(self, ref, p):
        by = {pin.get("name"): pin["net"] for pin in p["pins"].values()}
        vth = None
        el = p.get("electrical") if p.get("electrical_status") == "ok" else None
        d = (el or {}).get("vth")
        if isinstance(d, dict):
            lo = _num(d.get("min")) if _num(d.get("min")) is not None else _num(d.get("typ"))
            hi = _num(d.get("max")) if _num(d.get("max")) is not None else _num(d.get("typ"))
            if lo is not None and hi is not None:
                vth = (lo, hi)
        if {"G", "D", "S"} <= set(by):
            self.fet[ref] = {"g": by["G"], "d": by["D"], "s": by["S"], "vth": vth, "pol": "p" if vth and vth[1] < 0 else "n"}

    def _scan_reg(self, ref, p):
        el = p.get("electrical") if p.get("electrical_status") == "ok" else None
        rg = (el or {}).get("regulator")
        if not rg:
            return
        self.reg[ref] = {"rg": rg, "part": p}

    def _terminals(self):
        """Driver / receiver classes per net (spec 2.3)."""
        ext_pins = self.ext.get("pins", {})
        for net, atts in self.att.items():
            nm = self.nets[net]
            for a in atts:
                cls, io, p = a["cls"], a["io"] or {}, a["part"]
                base = {"term": a["term"], "name": a["name"], "class": cls}
                if a["et"] in ("R", "C", "L", "FUSE", "DIODE", "LED", "CLAMP", "OTHER", "MECH"):
                    continue
                if a["et"] == "CONN":
                    e = ext_pins.get(a["term"])
                    if e and e.get("dir") in ("supply", "in", "bidir"):
                        nm.drivers.append(dict(base, kind="external" if e["dir"] != "supply" else "external_supply"))
                    if e and e.get("dir") in ("out", "bidir"):
                        nm.receivers.append(dict(base, kind="external"))
                    if cls == "bidirectional":
                        nm.drivers.append(dict(base, kind="bidirectional"))
                        nm.receivers.append(dict(base, kind="bidirectional"))
                    continue
                if cls == "output":
                    nm.drivers.append(dict(base, kind="tristate" if io.get("tristate") else "push_pull"))
                elif cls == "open_collector":
                    nm.drivers.append(dict(base, kind="sink_only"))
                elif cls == "bidirectional":
                    nm.drivers.append(dict(base, kind="bidirectional"))
                    nm.receivers.append(dict(base, kind="bidirectional"))
                elif cls == "input":
                    nm.receivers.append(dict(base, kind=(p.get("electrical") or {}).get("input_type", "cmos")))
                elif cls == "analog":
                    nm.receivers.append(dict(base, kind="analog"))
                elif cls == "power_out":
                    nm.supply_sources.append(dict(base, kind="power_out"))
                elif cls == "power_in":
                    nm.supply_sinks.append(dict(base, kind="power_in"))
                elif cls is None and a["et"] in ("IC", "REG", "FET"):
                    nm.unclassified.append(dict(base, kind="unclassified"))

    # -- interval access ----------------------------------------------------------------------------------
    def vget(self, net):
        """(interval, assumes list) of a net: derived value, else (second pass) its NET_SPEC claim. None if unknown."""
        n = self.nets.get(net)
        if n is None:
            return None
        if n.interval is not None:
            return n.interval, list(n.assumes)
        if self.use_claims and n.claim is not None:
            return n.claim, [net]
        return None

    def _line(self, net):
        n = self.nets[net]
        return ["%s = %s (assumed: NET_SPEC claim, no derivation)" % (net, fmt(n.claim))] if n.interval is None else n.path

    def assign(self, net, iv, step, parents=(), source="derived", assumes=()):
        n = self.nets[net]
        path = []
        for pnet in parents:
            for s in self._line(pnet):
                if s not in path:
                    path.append(s)
        n.interval, n.source = (float(iv[0]), float(iv[1])), source
        n.path = path + [step]
        seen = []
        for a in list(assumes):
            if a not in seen:
                seen.append(a)
        n.assumes = seen

    def add_why(self, net, prio, text, kind="other"):
        self.why.setdefault(net, []).append((prio, text, kind))

    # -- seeds --------------------------------------------------------------------------------------------
    def seed(self):
        for name, n in sorted(self.nets.items()):
            if n.ir_class == "ground":
                self.assign(name, (0.0, 0.0), "%s: ground-class net = 0 V" % name, source="ground")
        for term, e in sorted(self.ext.get("pins", {}).items()):
            ref, _dot, pad = term.partition(".")
            pin = self.parts.get(ref, {}).get("pins", {}).get(pad)
            if pin is None:
                continue
            net = pin["net"]
            if e.get("v") is None:
                self.add_why(net, 50, "connector pin %s is declared in EXTERNAL (dir %s) but gives no voltage `v`" % (term, e.get("dir")), "external")
                continue
            iv = (float(e["v"][0]), float(e["v"][1]))
            n = self.nets[net]
            step = "EXTERNAL %s: %s%s" % (term, fmt(iv), " (%s)" % e["why"] if e.get("why") else "")
            if n.interval is not None and n.source == "external":
                n.interval = hull(n.interval, iv)
                n.path.append(step)
            else:
                self.assign(net, iv, step, source="external")
        for net, atts in sorted(self.att.items()):
            if self.nets[net].interval is None:
                for a in atts:
                    if a["et"] == "CONN":
                        if not self.ext.get("declared"):
                            self.add_why(net, 50, "connector pin %s: EXTERNAL is not declared in netlist.py" % a["term"], "external")
                        elif a["part"]["ref"] in self.ext.get("none", []):
                            self.add_why(net, 50, "connector %s is declared to have no external nets (EXTERNAL 'none')" % a["ref"], "external")
                        elif a["term"] not in self.ext.get("pins", {}):
                            self.add_why(net, 50, "connector pin %s is not listed in EXTERNAL" % a["term"], "external")

    # -- derivation rules ---------------------------------------------------------------------------------
    def derive_all(self):
        """Run the rules over every underived net until nothing changes."""
        changed = True
        while changed:
            changed = False
            for net in sorted(self.nets):
                if self.nets[net].interval is not None:
                    continue
                r = self.try_derive(net)
                if r is None:
                    continue
                if net in r["assumes"]:
                    self.add_why(net, 55, "would only follow from its own NET_SPEC claim through %s (circular, kept as claim)" % r["step"], "circular")
                    continue
                self.assign(net, r["iv"], r["step"], r["parents"], r["source"], r["assumes"])
                changed = True
            if self.decide_fets():
                changed = True

    def try_derive(self, net):
        for fn in (self.r_short, self.r_regulator, self.r_divider, self.r_diode, self.r_series, self.r_driver):
            r = fn(net)
            if r:
                return r
        return None

    # classify the non-edge attachments of a node for series / divider rules
    def _others(self, net, skip_refs):
        """-> (loads, blockers): loads = list of divider-style load dicts; blockers = reasons that rule out a pure R node."""
        loads = []
        for a in self.att[net]:
            et, cls, ref = a["et"], a["cls"], a["ref"]
            if ref in skip_refs:
                continue
            t = a["term"]
            if et in ("C", "CLAMP", "MECH"):
                loads.append({"term": t, "kind": "high_z"})
            elif et == "FET":
                f = self.fet.get(ref)
                if f and net == f["g"]:
                    loads.append({"term": t, "kind": "high_z"})
                else:
                    loads.append({"term": t, "kind": "other", "why": "MOSFET channel (state-dependent)"})
            elif et in ("IC", "REG") and cls in ("input", "analog"):
                loads.append({"term": t, "kind": cls, "leak_a": divider.leakage_a((a["io"] or {}).get("i_in_leak"))})
            elif et in ("IC", "REG") and cls == "power_in":
                loads.append({"term": t, "kind": "other", "why": "supply pin (a DC load)", "power_in": True, "part": a["part"]})
            elif et == "CONN":
                loads.append({"term": t, "kind": "other", "why": "connector pin (external, unknown)"})
            elif et in ("DIODE", "LED"):
                loads.append({"term": t, "kind": "other", "why": "diode/LED conducts"})
            elif et in ("L", "FUSE"):
                loads.append({"term": t, "kind": "other", "why": "short element to another net"})
            elif et == "R":
                loads.append({"term": t, "kind": "other", "why": "another resistor"})
            else:
                loads.append({"term": t, "kind": "other", "why": "pin class %s%s" % (cls, " (output/driver)" if cls in ("output", "open_collector", "bidirectional", "power_out") else "")})
        return loads

    def _res_edges(self, net):
        edges = []
        for ref, r in sorted(self.res.items()):
            if net in r["nets"]:
                far = r["nets"][1] if r["nets"][0] == net else r["nets"][0]
                edges.append({"ref": ref, "far": far, "r": r["r"], "value": r["value"]})
        return edges

    def r_short(self, net):
        for ref, text, a, b in self.short:
            if net in (a, b):
                far = b if net == a else a
                v = self.vget(far)
                if v:
                    return {"iv": v[0], "step": "%s: %s, same DC node as %s (%s)" % (net, text, far, fmt(v[0])),
                            "parents": [far], "source": "short", "assumes": v[1]}
        return None

    def r_regulator(self, net):
        for ref, g in sorted(self.reg.items()):
            part = g["part"]
            outs = [pad for pad, pin in part["pins"].items() if pin.get("class") == "power_out" and pin["net"] == net]
            if not outs:
                continue
            rg = g["rg"]
            vout = rg.get("vout") or {}
            lo = _num(vout.get("min")) if _num(vout.get("min")) is not None else _num(vout.get("typ"))
            hi = _num(vout.get("max")) if _num(vout.get("max")) is not None else _num(vout.get("typ"))
            if lo is None or hi is None:
                self.add_why(net, 8, "regulator %s has no fixed vout in its record (adjustable: feedback network not modelled)" % ref, "regulator")
                return None
            ins = [pin["net"] for pad, pin in part["pins"].items()
                   if pin.get("class") == "power_in" and self.nets[pin["net"]].ir_class != "ground"]
            ins = sorted(set(ins))
            if len(ins) != 1:
                self.add_why(net, 8, "regulator %s: cannot identify a single input rail (%s)" % (ref, ", ".join(ins) or "none"), "regulator")
                return None
            vin = self.vget(ins[0])
            if vin is None:
                self.add_why(net, 8, "regulator %s input %s has no known voltage" % (ref, ins[0]), "regulator")
                return None
            vi, assumes = vin
            topo = rg.get("topology", "")
            win = (_num((rg.get("vin") or {}).get("min")), _num((rg.get("vin") or {}).get("max")))
            iv, extra = (lo, hi), ""
            if win[0] is not None and vi[0] < win[0] - EPS or win[1] is not None and vi[1] > win[1] + EPS:
                self.add_why(net, 8, "regulator %s input %s %s is outside the record's Vin range %s..%s V (output not guaranteed)"
                             % (ref, ins[0], fmt(vi), win[0], win[1]), "regulator")
                return None
            if topo == "ldo":
                drops = [_num(x.get("max")) if _num(x.get("max")) is not None else _num(x.get("typ")) for x in rg.get("dropout") or []]
                drops = [d for d in drops if d is not None]
                if not drops:
                    self.add_why(net, 8, "LDO %s has no dropout datum in its record" % ref, "regulator")
                    return None
                dmax = max(drops)
                if vi[0] < hi + dmax - EPS:
                    iv = (min(lo, vi[0] - dmax), hi)
                    extra = "; DROPOUT: Vin min %.4g V < Vout max %.4g + dropout %.4g V, output may sag to %.4g V" % (vi[0], hi, dmax, iv[0])
                else:
                    extra = "; headroom ok: Vin min %.4g V >= Vout max %.4g + dropout %.4g V" % (vi[0], hi, dmax)
            return {"iv": iv, "step": "%s (%s, %s): Vout %s from the record%s; input %s = %s"
                                      % (ref, part.get("registry"), topo or "regulator", fmt((lo, hi)), extra, ins[0], fmt(vi)),
                    "parents": [ins[0]], "source": "regulator", "assumes": assumes}
        return None

    def r_divider(self, net):
        edges = self._res_edges(net)
        if len(edges) > 2:
            self.add_why(net, 10, "divider midpoint not computable: %d resistors (%s) meet at the node (a divider needs exactly 2)"
                         % (len(edges), ", ".join(e["ref"] for e in edges)), "divider")
        if len(edges) != 2:
            return None
        loads = self._others(net, {e["ref"] for e in edges})
        res = divider.evaluate(edges, loads, lambda n: (self.vget(n) or (None,))[0])
        if not res["computable"]:
            self.add_why(net, 10, res["reason"], "divider")
            return None
        assumes = []
        for f in res["far"]:
            assumes += self.vget(f)[1]
        return {"iv": res["interval"], "step": "%s: %s (resistors +-%d %% generic tolerance)" % (net, res["step"], int(R_TOL * 100)),
                "parents": res["far"], "source": "divider", "assumes": assumes}

    def r_series(self, net):
        edges = self._res_edges(net)
        if len(edges) != 1:
            return None
        e = edges[0]
        loads = self._others(net, {e["ref"]})
        far = self.vget(e["far"])
        i_ma, bad, leak_a = 0.0, [], 0.0
        for ld in loads:
            if ld["kind"] == "high_z":
                continue
            if ld["kind"] in ("input", "analog"):
                if ld.get("leak_a") is None:
                    bad.append("%s is an input/analog pin with no declared input leakage (not known to be high-Z)" % ld["term"])
                else:
                    leak_a += ld["leak_a"]
                continue
            if ld.get("power_in"):
                lm = ((ld["part"].get("electrical") or {}).get("load_ma") or {})
                vals = [_num(d.get(k)) for d in lm.values() if isinstance(d, dict) for k in ("max", "typ")]
                vals = [v for v in vals if v is not None]
                if vals:
                    i_ma += max(vals)
                    continue
                bad.append("%s draws current and its record has no load_ma" % ld["term"])
                continue
            bad.append("%s: %s" % (ld["term"], ld.get("why")))
        if bad:
            self.add_why(net, 60, "series resistor %s -> %s not applicable: %s" % (e["ref"], net, "; ".join(bad)), "load")
            return None
        if far is None:
            return None
        iv = far[0]
        drop = i_ma * 1e-3 * e["r"][1]                          # load current flows out of the node: lowers it
        wob = leak_a * e["r"][1]                                # input leakage may flow either way: widens both sides
        if drop or wob:
            iv = (iv[0] - drop - wob, iv[1] + wob)
        return {"iv": iv, "step": "%s: series resistor %s (%s) from %s %s, no DC load on %s%s"
                                  % (net, e["ref"], e["value"], e["far"], fmt(far[0]), net,
                                     "; load %.4g mA * R max %.4g ohm = %.4g V drop" % (i_ma, e["r"][1], drop) if drop else " (voltage passes unchanged)")
                                  + ("; input leakage %.3g A * %.4g ohm = +-%.3g V" % (leak_a, e["r"][1], wob) if wob else ""),
                "parents": [e["far"]], "source": "resistor", "assumes": far[1]}

    def r_diode(self, net):
        ds = [(ref, d) for ref, d in sorted(self.dio.items()) if net in (d["a"], d["k"])]
        if len(ds) != 1:
            return None
        ref, d = ds[0]
        edges = self._res_edges(net)
        if len(edges) > 1:
            return None
        far_net = d["a"] if net == d["k"] else d["k"]
        if far_net == net:
            return None
        if d["vf"] is None:
            self.add_why(net, 20, d["why"], "no-vf")
            return None
        others = [ld for ld in self._others(net, {ref} | {e["ref"] for e in edges})
                  if ld["kind"] not in ("high_z", "input", "analog") and not ld.get("power_in")]
        if others:
            self.add_why(net, 20, "diode node also has: %s" % "; ".join("%s (%s)" % (o["term"], o.get("why")) for o in others), "load")
            return None
        fv = self.vget(far_net)
        if fv is None:
            return None
        F, assumes = fv[0], list(fv[1])
        vfmin, vfmax = d["vf"]
        is_cathode = net == d["k"]
        fwd = (F[0] - vfmax, F[1] - vfmin) if is_cathode else (F[0] + vfmin, F[1] + vfmax)
        word = "%s %s: Vf %.4g..%.4g V (%s record)" % (d["type"], ref, vfmin, vfmax, d["value"])
        if not edges:
            return {"iv": fwd, "step": "%s: %s, %s is the %s so %s = %s %s Vf = %s (valid while the diode conducts into a load)"
                                       % (net, word, net, "cathode" if is_cathode else "anode", net, far_net, "-" if is_cathode else "+", fmt(fwd)),
                    "parents": [far_net], "source": "diode", "assumes": assumes}
        e = edges[0]
        gv = self.vget(e["far"])
        if gv is None:
            return None
        G = gv[0]
        assumes += gv[1]
        if is_cathode:                      # F -> diode -> net -> R -> G
            on, off = F[0] - vfmax > G[1], F[1] - vfmin <= G[0]
        else:                               # G -> R -> net -> diode -> F
            on, off = G[0] - F[1] > vfmax, G[1] - F[0] <= vfmin
        if on:
            iv, st = fwd, "diode conducts (%s -> %s drop exceeds Vf max)" % ((far_net, e["far"]) if is_cathode else (e["far"], far_net))
        elif off:
            iv, st = G, "diode cannot conduct, %s follows %s through %s" % (net, e["far"], e["ref"])
        else:
            iv, st = hull(fwd, G), "diode state not fixed by the intervals: hull of conducting and off"
            self.nets[net].state_dependent = True
        return {"iv": iv, "step": "%s: %s with %s (%s) to %s %s: %s" % (net, word, e["ref"], e["value"], e["far"], fmt(G), st),
                "parents": [far_net, e["far"]], "source": "diode", "assumes": assumes}

    def r_driver(self, net):
        drivers = [a for a in self.att[net] if a["et"] in ("IC", "REG") and a["cls"] in ("output", "open_collector", "bidirectional", "power_out")]
        if not drivers:
            return None
        if any(d["kind"].startswith("external") for d in self.nets[net].drivers):
            self.add_why(net, 25, "the net can also be driven from outside the board (EXTERNAL dir in/supply/bidir)", "driver")
            return None
        if any(a["cls"] != "output" for a in drivers):
            bad = [a for a in drivers if a["cls"] != "output"]
            self.add_why(net, 25, "driven by %s (class %s): no output-level model" % (bad[0]["term"], bad[0]["cls"]), "driver")
            return None
        lows, highs, parents, assumes, notes = [], [], [], [], []
        for a in drivers:
            io = a["io"] or {}
            sp = io.get("supply_pin")
            sup_pin = a["part"]["pins"].get(sp) if sp else None
            if sup_pin is None:
                self.add_why(net, 25, "driver %s: record names no supply pin" % a["term"], "driver")
                return None
            sv = self.vget(sup_pin["net"])
            gnds = [pin["net"] for pin in a["part"]["pins"].values()
                    if pin.get("class") == "power_in" and self.nets[pin["net"]].ir_class == "ground"]
            gv = self.vget(gnds[0]) if gnds else None
            if sv is None or gv is None:
                self.add_why(net, 25, "driver %s: supply %s or ground not known" % (a["term"], sup_pin["net"]), "driver")
                return None
            S, G = sv[0], gv[0]
            ok = False
            for key in ("voh", "vol"):
                d = io.get(key)
                if isinstance(d, dict):
                    at = _num((d.get("at") or {}).get("vcc_v"))
                    rng = _datum_range(d, S)
                    if rng is not None and (at is None or S[0] * (1 - LEVEL_SUPPLY_TOL) <= at <= S[1] * (1 + LEVEL_SUPPLY_TOL)):
                        ok = True
            if not ok:
                d = io.get("voh") or io.get("vol") or {}
                at = _num((d.get("at") or {}).get("vcc_v"))
                self.add_why(net, 25, "driver %s has no usable VOH/VOL%s" % (
                    a["term"], " (datum is measured at VCC=%s V, supply is %s)" % (at, fmt(S)) if at is not None else " in its record"), "driver")
                return None
            lows.append(G[0])
            highs.append(S[1])
            vol = _datum_range(io.get("vol") or {}, S)
            voh = _datum_range(io.get("voh") or {}, S)
            notes.append((G, S, vol, voh))
            parents += [sup_pin["net"]] + gnds[:1]
            assumes += sv[1] + gv[1]
        G, S, vol, voh = notes[0]
        n = self.nets[net]
        lowhi = G[1] + vol[1] if vol and vol[1] is not None else S[1]
        highlo = voh[0] if voh and voh[0] is not None else G[0]
        n.levels = {"low": (G[0], lowhi), "high": (highlo, S[1])}
        return {"iv": (min(lows), max(highs)),
                "step": "%s: push-pull output %s swings between ground %s and supply %s (record VOH/VOL: low <= %s, high >= %s)"
                        % (net, drivers[0]["term"], fmt(G), fmt(S), fmt((G[0], lowhi)), fmt((highlo, S[1]))),
                "parents": sorted(set(parents)), "source": "driver", "assumes": assumes}

    # -- FET states ---------------------------------------------------------------------------------------
    def decide_fets(self):
        changed = False
        for ref, f in sorted(self.fet.items()):
            if ref in self.fet_state:
                continue
            if f["vth"] is None:
                self.fet_state[ref] = "both"
                continue
            vg, vs = self.vget(f["g"]), self.vget(f["s"])
            if vg is None or vs is None:
                continue
            g, s = vg[0], vs[0]
            lo, hi = f["vth"]
            if f["pol"] == "n":
                on, off = g[0] - s[1] >= hi, g[1] - s[0] <= lo
            else:
                on, off = g[1] - s[0] <= lo, g[0] - s[1] >= hi
            if on:
                self.fet_state[ref] = "on"
                self.short.append((ref, "%s ON (gate %s %s vs source %s %s beyond Vth %.4g..%.4g V; channel ~ Rds(on))"
                                   % (ref, f["g"], fmt(g), f["s"], fmt(s), lo, hi), f["d"], f["s"]))
                changed = True
            elif off:
                self.fet_state[ref] = "off"
                self.nets[f["d"]].notes.append("%s is OFF (gate %s %s): channel open" % (ref, f["g"], fmt(g)))
                changed = True
        return changed

    # -- finish -------------------------------------------------------------------------------------------
    def run(self):
        self.seed()
        self.use_claims = False
        self.derive_all()
        self.why = {k: [w for w in v if w[2] == "external"] for k, v in self.why.items()}      # keep connector reasons only
        self.use_claims = True
        self.derive_all()
        self.finish()

    def finish(self):
        for ref, f in sorted(self.fet.items()):
            if self.fet_state.get(ref) in (None, "both"):
                for side in ("d", "s"):
                    n = self.nets[f[side]]
                    n.state_dependent = True
                    n.notes.append("%s gate %s is not fixed (%s): ON joins drain and source, OFF leaves the channel open; both states are possible"
                                   % (ref, f["g"], "no Vth in the record" if f["vth"] is None else "gate voltage straddles Vth"))
        for name, n in sorted(self.nets.items()):
            self._pull(n)
            if n.interval is not None and n.source != "claim":
                if n.claim is not None and not contains(n.claim, n.interval):
                    n.status = "conflict"
                    n.reason = "NET_SPEC claims %s but the derivation gives %s" % (fmt(n.claim), fmt(n.interval))
                else:
                    n.status = "derived"
                continue
            reason, rkind = self._why(name)
            n.reason_kind = rkind
            if n.claim is not None:
                n.interval, n.status, n.source = n.claim, "claimed-only", "claim"
                n.reason = reason
                n.path = ["%s = %s (assumed: NET_SPEC claim, no derivation)" % (name, fmt(n.claim))]
            else:
                n.status, n.reason = "NOT_JUDGED", reason
            if n.state_dependent and n.status != "derived":
                n.reason_kind = "state-dependent"
                n.reason = (n.notes[-1] if n.notes else "a switch/FET state is not fixed") + ("; " + reason if reason else "")

    def _why(self, net):
        """(reason text, reason kind) for a net nothing derived."""
        w = sorted(self.why.get(net, []), key=lambda t: t[0])
        if w:
            return w[0][1], w[0][2]
        atts = self.att.get(net, [])
        kinds = {(a["et"], a["cls"]) for a in atts}
        active = [a for a in atts if a["cls"] in ("output", "open_collector", "bidirectional", "power_out")]
        if active:
            return "driven by %s but no derivation applies" % ", ".join(a["term"] for a in active[:3]), "driver"
        if all(et in ("C", "CLAMP", "MECH") or cls in ("input", "analog") for et, cls in kinds):
            return "no DC source: only %s attached" % ", ".join(sorted({"capacitor" if et == "C" else ("%s pin" % cls if cls else et)
                                                                         for et, cls in kinds})), "no-dc-source"
        far = [(e["ref"], e["far"]) for e in self._res_edges(net)]
        if far:
            return "reached only through %s from net(s) with no known voltage" % ", ".join("%s->%s" % f for f in far), "upstream-unknown"
        return "no derivation rule applies (attached: %s)" % ", ".join(sorted({a["term"] for a in atts})[:4]), "other"

    def _pull(self, n):
        net = n.name
        if any(d["kind"] in ("push_pull", "tristate") for d in n.drivers):
            return
        atts = self.att.get(net, [])
        if any(a["et"] in ("IC", "REG", "CONN", "FET") and a["cls"] not in ("input", "open_collector", "bidirectional", "analog", None)
               and not (a["et"] == "FET" and self.fet.get(a["ref"], {}).get("g") == net) for a in atts):
            return
        pulls, states = [], set()
        for e in self._res_edges(net):
            fv = self.nets[e["far"]].interval if self.nets[e["far"]].interval is not None else None
            if fv is None:
                continue
            st = "low" if fv[1] <= LOW_THRESHOLD_V else ("high" if fv[0] >= HIGH_THRESHOLD_V else None)
            pulls.append({"ref": e["ref"], "to": e["far"], "state": st, "r_ohm": [round(e["r"][0], 4), round(e["r"][1], 4)]})
            states.add(st)
        if pulls:
            n.pull = {"state": next(iter(states)) if len(states) == 1 and None not in states else None, "resistors": pulls}


def build_model(ir):
    """The derived electrical model of a design IR (see the module docstring)."""
    b = _Builder(ir)
    b.run()
    elements = {"resistors": len(b.res), "shorts": len(b.short), "diodes": len(b.dio), "fets": len(b.fet),
                "regulators": len(b.reg), "fet_states": dict(sorted(b.fet_state.items()))}
    return ElecModel((ir.get("meta") or {}).get("project"), dict(sorted(b.nets.items())), elements)


# ---------------------------------------------------------------------------------------------------- CLI
def _load_ir(arg):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    path = arg if arg.endswith(".json") else os.path.join(root, "projects", arg, "out", "design.json")
    if not os.path.isfile(path):
        raise SystemExit("no IR at %s - run: python tools/boardgen/ir/build.py %s" % (path, arg))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    net, as_json, summary, proj = None, False, False, None
    it = iter(argv)
    for a in it:
        if a == "--net":
            net = next(it, None)
        elif a == "--json":
            as_json = True
        elif a == "--summary":
            summary = True
        elif not a.startswith("-"):
            proj = a
    if not proj:
        print(__doc__)
        return 2
    m = build_model(_load_ir(proj))
    if as_json:
        print(json.dumps(m.to_dict(), indent=1, sort_keys=True))
    elif net:
        print(m.explain(net))
    else:
        c = m.counts()
        print("%s: %d nets - %s" % (m.project or proj, len(m.nets), ", ".join("%d %s" % (c[s], s) for s in STATUSES)))
        for n in m.nets.values():
            print("  %-14s %-12s %-16s %s" % (n.name, n.status, fmt(n.interval) if n.interval else "-",
                                              ("" if n.status == "derived" else n.reason)[:100]))
        if summary:
            for st in ("NOT_JUDGED", "claimed-only"):
                for kind, nets in m.reason_counts(st).items():
                    print("  %s x%d by reason '%s': %s%s" % (st, len(nets), kind, ", ".join(nets[:5]), " ..." if len(nets) > 5 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
