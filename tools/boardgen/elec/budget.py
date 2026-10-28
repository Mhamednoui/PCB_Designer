"""Current budget (P2-T6; spec docs/design/P2_ELECTRICAL_ANALYZER.md section 2.4). Pure Python, stdlib only.

    from boardgen.elec.budget import build_budget
    b = build_budget(ir, model)          # model = boardgen.elec.model.build_model(ir)
    b.demand("3V3")                      # {"peak": mA, "typ": mA, "unknown": [{"net","term","field","desc"}], "loads": [...]}
    python tools/boardgen/elec/budget.py <project> [--net NAME]     # prints the table (needs out/design.json)

Model.  A rail's demand = its own loads + everything fed THROUGH it from the nets below it:
  own loads    (a) IC `electrical.load_ma` {typ, peak} of a part's power_in pins; (b) resistors: rail -> R -> ground (V/R),
               rail -> R -> node with a resistor to ground (divider), rail -> R -> anything else (a pull-up, counted as if the
               line were pulled low: conservative); (c) LED chains: rail (or a push-pull driver's supply) -> R -> LED -> ground,
               I = (V - Vf)/R; (d) EXTERNAL `out` pins WITH `i` (amps) on a power-class net.  V is the high corner of the
               rail's model interval and R is -5 % for the peak figure; typ uses the interval midpoint and nominal R.
  edges        fuse / inductor / 0R link / diode: the downstream demand passes through unchanged (direction = away from the
               EXTERNAL supply pins, found by breadth-first search; a diode conducts anode -> cathode).  Regulator: an LDO
               adds its quiescent current (iq max for peak), a switcher_module draws Pout/(eff * Vin_low) (efficiency minimum
               for peak).
  unknown      every load whose current cannot be derived is listed WITH the missing field (e.g. "electrical.load_ma",
               "EXTERNAL i").  A total is therefore either complete or a LOWER BOUND; the rules treat a lower bound that already
               exceeds a limit as a definite ERROR and anything else as NOT_JUDGED.
peak = design point (spec section 8): continuous worst-case, not duty-weighted; typ is reported alongside and judged by nothing.
Not modelled: duty cycles, inrush, capacitor charging, temperature dependence of any current.
"""
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from boardgen.elec import devices as dev                         # noqa: E402
from boardgen.elec.model import R_TOL, element_type, parse_resistance   # noqa: E402

USABLE = ("derived", "claimed-only", "conflict")
SERIES = ("fuse", "ind", "link")


class Edge:
    def __init__(self, kind, ref, a, b, part=None):
        self.kind, self.ref, self.a, self.b, self.part = kind, ref, a, b, part
        self.up = self.down = None
        self.carried_peak = self.carried_typ = 0.0


class Budget:
    def __init__(self, ir, model):
        self.ir, self.model = ir, model
        self.parts = ir.get("parts", {})
        self.ext = (ir.get("external") or {}).get("pins", {})
        self.ncls = {n: v.get("class") for n, v in ir.get("nets", {}).items()}
        self.etype = {r: element_type(p) for r, p in self.parts.items()}
        self.loads, self.unknown = {}, {}                 # net -> [..]
        self.edges, self.notes = [], []
        self.res_i = {}                                   # resistor ref -> {"peak","typ","desc"} (mA) for the thermal rule
        self.sources = {}                                 # net -> {"i_ma": mA|None, "terms": [...]}
        self.parent = {}                                  # net -> Edge feeding it from the source side
        self._memo, self._busy = {}, set()
        self._consumed = set()
        self._by_net = {}                                 # net -> [(ref, pad, pin)]
        for ref, p in self.parts.items():
            for pad, pin in p.get("pins", {}).items():
                self._by_net.setdefault(pin["net"], []).append((ref, pad, pin))
        self._res = self._resistors()
        self._edges()
        self._orient()
        self._loads()

    # -- helpers ----------------------------------------------------------------------------------
    def iv(self, net):
        n = self.model.nets.get(net)
        return n.interval if n is not None and n.status in USABLE and n.interval is not None else None

    def is_ground(self, net):
        return self.ncls.get(net) == "ground" or self.iv(net) == (0.0, 0.0)

    def is_rail(self, net):
        return (not self.is_ground(net)) and self.iv(net) is not None and self.ncls.get(net) == "power"

    def add_load(self, net, term, desc, peak, typ):
        self.loads.setdefault(net, []).append({"net": net, "term": term, "desc": desc, "peak": peak, "typ": typ})

    def add_unknown(self, net, term, field, desc):
        self.unknown.setdefault(net, []).append({"net": net, "term": term, "field": field, "desc": desc})

    def _resistors(self):
        out = {}
        for ref, p in self.parts.items():
            if self.etype[ref] != "R":
                continue
            ns = [pin["net"] for _k, pin in sorted(p["pins"].items())]
            ohm = parse_resistance(p.get("value", ""))
            if len(ns) == 2 and ns[0] != ns[1] and ohm:
                out[ref] = {"nets": ns, "r": ohm, "rlo": ohm * (1 - R_TOL), "value": p.get("value", "")}
        return out

    def _res_on(self, net):
        return [r for r, d in sorted(self._res.items()) if net in d["nets"] and r not in self._consumed]

    # -- edges ------------------------------------------------------------------------------------
    def _edges(self):
        for ref, p in sorted(self.parts.items()):
            et = self.etype[ref]
            pins = [pin for _k, pin in sorted(p.get("pins", {}).items())]
            if et in ("FUSE", "L") and len(pins) == 2 and pins[0]["net"] != pins[1]["net"]:
                self.edges.append(Edge("fuse" if et == "FUSE" else "ind", ref, pins[0]["net"], pins[1]["net"], p))
            elif et == "R" and parse_resistance(p.get("value", "")) == 0 and len(pins) == 2 and pins[0]["net"] != pins[1]["net"]:
                self.edges.append(Edge("link", ref, pins[0]["net"], pins[1]["net"], p))
            elif et == "DIODE":
                by = {pin.get("name"): pin["net"] for pin in pins}
                if by.get("A") and by.get("K") and by["A"] != by["K"]:
                    e = Edge("diode", ref, by["A"], by["K"], p)
                    e.up, e.down = by["A"], by["K"]
                    self.edges.append(e)
            elif et == "REG":
                ins = sorted({pin["net"] for pin in pins if pin.get("class") == "power_in" and not self.is_ground(pin["net"])})
                outs = sorted({pin["net"] for pin in pins if pin.get("class") == "power_out"})
                if len(ins) == 1 and len(outs) == 1:
                    e = Edge("reg", ref, ins[0], outs[0], p)
                    e.up, e.down = ins[0], outs[0]
                    self.edges.append(e)
                else:
                    self.notes.append("%s: cannot identify one input and one output rail (in %s, out %s)" % (ref, ins, outs))

    def _orient(self):
        dist, queue = {}, []
        for term, e in sorted(self.ext.items()):
            if isinstance(e, dict) and e.get("dir") == "supply":
                ref, _, pad = term.partition(".")
                pin = self.parts.get(ref, {}).get("pins", {}).get(pad)
                if pin is None:
                    continue
                net = pin["net"]
                s = self.sources.setdefault(net, {"i_ma": 0.0, "terms": []})
                s["terms"].append(term)
                if e.get("i") is None or s["i_ma"] is None:
                    s["i_ma"] = None
                else:
                    s["i_ma"] += float(e["i"]) * 1000.0
                if net not in dist and not self.is_ground(net):
                    dist[net] = 0
                    queue.append(net)
        i = 0
        while i < len(queue):
            u = queue[i]
            i += 1
            for e in self.edges:
                v = None
                if e.kind in SERIES and u in (e.a, e.b):
                    v = e.b if u == e.a else e.a
                elif e.kind in ("diode", "reg") and u == e.up:
                    v = e.down
                if v is not None and v not in dist:
                    dist[v] = dist[u] + 1
                    queue.append(v)
        for e in self.edges:
            if e.kind in SERIES:
                da, db = dist.get(e.a), dist.get(e.b)
                if da is not None and db is not None and da != db:
                    e.up, e.down = (e.a, e.b) if da < db else (e.b, e.a)
                else:
                    self.notes.append("%s: direction of the %s unknown (no EXTERNAL supply reaches one side first): "
                                      "the load behind it is not attributed" % (e.ref, e.kind))
        for e in self.edges:
            if e.up is not None and e.down not in self.parent:
                self.parent[e.down] = e

    # -- loads ------------------------------------------------------------------------------------
    def source_of(self, net):
        """(v_hi, v_mid, supply_net, why) of a net that can source current: a rail, or a push-pull driver's output."""
        if self.is_rail(net):
            lo, hi = self.iv(net)
            return hi, (lo + hi) / 2.0, net, "rail %s" % net
        drv = [(r, pad, pin) for r, pad, pin in self._by_net.get(net, []) if pin.get("class") in ("output", "bidirectional")]
        if len(drv) == 1:
            r, pad, pin = drv[0]
            sp = (pin.get("io") or {}).get("supply_pin")
            sp_pin = self.parts[r]["pins"].get(str(sp)) if sp is not None else None
            if sp_pin is not None and self.iv(sp_pin["net"]) is not None:
                lo, hi = self.iv(sp_pin["net"])
                return hi, (lo + hi) / 2.0, sp_pin["net"], "%s.%s drives it from %s" % (r, pad, sp_pin["net"])
        return None

    def _loads(self):
        self._led_chains()
        self._resistor_loads()
        self._ic_loads()
        self._external_loads()

    def _led_chains(self):
        for ref, p in sorted(self.parts.items()):
            if self.etype[ref] != "LED":
                continue
            by = {pin.get("name"): pin["net"] for pin in p["pins"].values()}
            na, nk = by.get("A"), by.get("K")
            if not na or not nk:
                continue
            if self.is_ground(nk):
                side, r_net = "anode", na
            elif self.is_ground(na):
                continue
            else:
                side, r_net = "cathode", nk
            rs = self._res_on(r_net)
            if len(rs) != 1:
                continue
            rr = rs[0]
            x = [n for n in self._res[rr]["nets"] if n != r_net][0]
            if side == "anode":
                src = self.source_of(x)
            else:                                           # LED on the supply side, resistor to ground
                src = self.source_of(na) if self.is_ground(x) else None
            if src is None:
                continue
            vhi, vmid, snet, why = src
            self._consumed.add(rr)
            vfd = dev.vf(p) if p.get("electrical_status") == "ok" else None
            if vfd is None:
                self.add_unknown(snet, ref, "electrical.vf of %s (value %s not covered by its record)" % (ref, p.get("value")),
                                 "%s LED branch" % ref)
                continue
            vf_lo, vf_hi, vf_typ = vfd
            vf_peak = vf_lo if vf_lo is not None else (vf_typ if vf_typ is not None else vf_hi)
            vf_t = vf_typ if vf_typ is not None else vf_hi
            r = self._res[rr]
            ip = max(0.0, (vhi - vf_peak) / r["rlo"]) * 1000.0
            it = max(0.0, (vmid - vf_t) / r["r"]) * 1000.0
            desc = "%s + %s LED branch (%s, Vf %.3g V)" % (rr, ref, why, vf_peak)
            self.add_load(snet, ref, desc, ip, it)
            self.res_i[rr] = {"peak": ip, "typ": it, "desc": desc}

    def _resistor_loads(self):
        for rr, d in sorted(self._res.items()):
            if rr in self._consumed:
                continue
            a, b = d["nets"]
            for rail, other in ((a, b), (b, a)):
                if not self.is_rail(rail):
                    continue
                lo, hi = self.iv(rail)
                mid = (lo + hi) / 2.0
                if self.is_ground(other):
                    ip, it, how = hi / d["rlo"], mid / d["r"], "to ground"
                else:
                    gnd = [g for g in self._res_on(other) if g != rr and any(self.is_ground(n) for n in self._res[g]["nets"])]
                    if gnd:
                        g = self._res[gnd[0]]
                        ip, it, how = hi / (d["rlo"] + g["rlo"]), mid / (d["r"] + g["r"]), "divider with %s" % gnd[0]
                        self._consumed.add(gnd[0])
                        self.res_i[gnd[0]] = {"peak": ip * 1000.0, "typ": it * 1000.0, "desc": "%s %s" % (rr, how)}
                    else:
                        ip, it, how = hi / d["rlo"], mid / d["r"], "pull-up or series, counted as if the line were pulled low"
                self._consumed.add(rr)
                self.add_load(rail, rr, "%s %s (%s)" % (rr, how, d["value"]), ip * 1000.0, it * 1000.0)
                self.res_i[rr] = {"peak": ip * 1000.0, "typ": it * 1000.0, "desc": "%s %s" % (rr, how)}
                break

    def _ic_loads(self):
        for ref, p in sorted(self.parts.items()):
            if self.etype[ref] != "IC":
                continue
            rails = sorted({pin["net"] for pin in p["pins"].values()
                            if pin.get("class") == "power_in" and not self.is_ground(pin["net"])})
            if not rails:
                continue
            lm = dev.load_ma(p) if p.get("electrical_status") == "ok" else None
            if len(rails) > 1:
                for n in rails:
                    self.add_unknown(n, ref, "electrical.load_ma split across the rails %s of %s" % (", ".join(rails), ref), ref)
                continue
            if lm is None or (lm["peak"] is None and lm["typ"] is None):
                self.add_unknown(rails[0], ref, "electrical.load_ma of %s (%s)" % (ref, p.get("registry") or "no part record"), ref)
                continue
            peak = lm["peak"] if lm["peak"] is not None else lm["typ"]
            typ = lm["typ"] if lm["typ"] is not None else lm["peak"]
            self.add_load(rails[0], ref, "%s supply current (record load_ma)" % ref, peak, typ)

    def _external_loads(self):
        for term, e in sorted(self.ext.items()):
            if not isinstance(e, dict) or e.get("dir") != "out":
                continue
            ref, _, pad = term.partition(".")
            pin = self.parts.get(ref, {}).get("pins", {}).get(pad)
            if pin is None or self.ncls.get(pin["net"]) != "power" or self.is_ground(pin["net"]):
                continue
            if e.get("i") is None:
                self.add_unknown(pin["net"], term, "EXTERNAL i of %s (current the outside draws)" % term, e.get("why", ""))
            else:
                ma = float(e["i"]) * 1000.0
                self.add_load(pin["net"], term, "%s external load (EXTERNAL i): %s" % (term, e.get("why", "")), ma, ma)

    def external_current_a(self, net):
        """Sum of EXTERNAL `out` pin currents on `net` (A) and the terms that declare none -> (amps, [terms without i])."""
        tot, missing = 0.0, []
        for term, e in sorted(self.ext.items()):
            if not isinstance(e, dict) or e.get("dir") != "out":
                continue
            ref, _, pad = term.partition(".")
            pin = self.parts.get(ref, {}).get("pins", {}).get(pad)
            if pin is not None and pin["net"] == net:
                if e.get("i") is None:
                    missing.append(term)
                else:
                    tot += float(e["i"])
        return tot, missing

    # -- demand -----------------------------------------------------------------------------------
    def demand(self, net):
        if net in self._memo:
            return self._memo[net]
        if net in self._busy:
            self.notes.append("net %s: current loop in the supply tree (cycle) - the second visit is ignored" % net)
            return {"peak": 0.0, "typ": 0.0, "unknown": [], "loads": []}
        self._busy.add(net)
        loads = list(self.loads.get(net, []))
        peak, typ = sum(x["peak"] for x in loads), sum(x["typ"] for x in loads)
        unk = list(self.unknown.get(net, []))
        for e in self.edges:
            if e.up != net:
                continue
            d = self.demand(e.down)
            unk += d["unknown"]
            e.carried_peak, e.carried_typ = d["peak"], d["typ"]
            if e.kind == "reg":
                e.carried_peak, e.carried_typ = self._reg_input(e, d, unk)
            peak += e.carried_peak
            typ += e.carried_typ
        self._busy.discard(net)
        self._memo[net] = {"peak": peak, "typ": typ, "unknown": unk, "loads": loads}
        return self._memo[net]

    def _reg_input(self, e, d, unk):
        rg = dev.regulator(e.part) or {}
        if rg.get("topology") == "switcher_module":
            vout = dev.datum_value(rg.get("vout"), ("typ", "max", "min"))
            eff_min = dev.datum_value(rg.get("efficiency_pct"), ("min", "typ"))
            eff_typ = dev.datum_value(rg.get("efficiency_pct"), ("typ", "min"))
            vin = self.iv(e.up)
            if vout is None or eff_min is None or vin is None or vin[0] <= 0:
                unk.append({"net": e.up, "term": e.ref, "field": "regulator.vout / regulator.efficiency_pct of %s, or its input voltage" % e.ref,
                            "desc": "%s input current" % e.ref})
                return d["peak"], d["typ"]
            iq_p = dev.datum_value(rg.get("iq_ma"), ("max", "typ")) or 0.0
            iq_t = dev.datum_value(rg.get("iq_ma"), ("typ", "max")) or 0.0
            peak = vout * d["peak"] / ((eff_min / 100.0) * vin[0]) + iq_p
            typ = vout * d["typ"] / ((eff_typ / 100.0) * ((vin[0] + vin[1]) / 2.0)) + iq_t
            return peak, typ
        iq_p = dev.datum_value(rg.get("iq_ma"), ("max", "typ"))
        iq_t = dev.datum_value(rg.get("iq_ma"), ("typ", "max"))
        if iq_p is None:
            unk.append({"net": e.up, "term": e.ref, "field": "regulator.iq_ma of %s" % e.ref, "desc": "%s quiescent current" % e.ref})
            iq_p = iq_t = 0.0
        return d["peak"] + iq_p, d["typ"] + iq_t

    def upstream_drop(self, net):
        """Series-fuse voltage drop (V) from the supply to `net` at the peak current each fuse carries.
        -> (volts, [fuse refs whose resistance is missing], [(ref, drop)])."""
        v, missing, parts, cur, seen = 0.0, [], [], net, set()
        while cur in self.parent and cur not in seen:
            seen.add(cur)
            e = self.parent[cur]
            self.demand(e.up)
            if e.kind == "fuse":
                fd = dev.fuse(e.part) if e.part.get("electrical_status") == "ok" else None
                if fd is None or fd["r_max_ohm"] is None:
                    missing.append(e.ref)
                else:
                    dv = fd["r_max_ohm"] * e.carried_peak / 1000.0
                    v += dv
                    parts.append((e.ref, dv))
            cur = e.up
        return v, missing, parts


def build_budget(ir, model):
    return Budget(ir, model)


def ldo_power_w(vin, vout, i_out_ma, iq_ma=0.0):
    """Linear regulator dissipation: Vin*(Iout+Iq) - Vout*Iout (the (Vin - Vout)*Iout of ARCHITECTURE 2.3 plus Vin*Iq)."""
    return vin * (i_out_ma + iq_ma) / 1000.0 - vout * i_out_ma / 1000.0


def main(argv):
    from boardgen.elec.model import build_model, _load_ir
    if not argv:
        raise SystemExit("usage: budget.py <project|design.json> [--net NAME]")
    ir = _load_ir(argv[0])
    b = build_budget(ir, build_model(ir))
    want = argv[argv.index("--net") + 1] if "--net" in argv else None
    nets = [want] if want else sorted(n for n in ir["nets"] if b.loads.get(n) or b.unknown.get(n) or any(e.up == n for e in b.edges))
    for n in nets:
        d = b.demand(n)
        print("%-12s peak %9.1f mA  typ %9.1f mA  (%d unknown)" % (n, d["peak"], d["typ"], len(d["unknown"])))
        for x in d["loads"]:
            print("    %9.2f mA  %s" % (x["peak"], x["desc"]))
        for x in d["unknown"]:
            print("    ?          %s" % x["field"])
    for note in b.notes:
        print("note:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
