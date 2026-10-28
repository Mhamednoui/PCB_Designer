"""EL-CONN-PROT: every net that leaves the board through a connector must show the protection its class needs
(P2-T7; spec docs/design/P2_ELECTRICAL_ANALYZER.md section 3). Reads the IR sections parts, nets and external (the
`EXTERNAL` declaration of netlist.py); pure graph analysis, no voltages.

    python tools/boardgen/elec/conn_prot.py <project-id | path/to/design.json> [--table] [--no-waivers]

Direct invocation (needs `out/design.json`, i.e. `python pipeline.py <id> --only ir` first) prints the per-net class table
(--table) and the findings, applies projects/<id>/waivers.json (check "electrical", rule EL-CONN-PROT) and exits 1 on an
unwaived ERROR. As a rule it runs wherever the engine runs it: `boardgen.rules.run(ir, only=["EL-CONN-PROT"])`; the
`electrical` stage (wired by the supervisor) simply runs all registered electrical rules, this one included.

Classification (per external net, from the connector pin's record class and the EXTERNAL `dir`):
  module   the connector pin's record class is not `passive` (an Arduino/ESP32 socket: the other side is an active board with
           its own protection): not field wiring, not required to have a clamp.
  supply   `dir: supply` on a passive connector pin (the outside powers the board). Needs, on the net or downstream of a
           fuse / ferrite / 0R: a surge clamp (TVS/zener to ground), reverse-polarity protection (a series diode or P-FET,
           or a shunt diode/TVS with its cathode on the rail DOWNSTREAM of a fuse: a crowbar that blows the fuse), and a
           fuse/PTC when the declaration gives a source current `i`.
  supply-output   a power net the board hands out (`dir: out`): reported, never an ERROR (spec only constrains inputs).
  signal   everything else. protected = a clamp (TVS/zener to ground, a diode to a rail, an ESD IC) on the net or behind
           its first resistors; isolated = the only active pins behind it are optocoupler pins; series-R-only = resistors
           but no clamp; bare = straight to the part. Anything but protected/isolated is an ERROR.
Unknown = NOT_JUDGED (fail closed): a connector with no EXTERNAL declaration, or connected non-ground pins left out of it.
"""
from boardgen.elec.model import element_type, parse_resistance  # noqa: E402
from boardgen.rules.engine import rule                           # noqa: E402

MAX_R_HOPS = 2                                                   # series resistors followed from the connector pin


class _Design:
    """The graph view of an IR: element types, terminals per net, net classes."""
    def __init__(self, ir):
        self.parts = ir.get("parts", {})
        self.nets = ir.get("nets", {})
        self.ext = ir.get("external") or {"declared": False, "pins": {}, "none": []}
        self.etype = {r: element_type(dict(p, ref=r)) for r, p in self.parts.items()}
        self.att = {}
        for ref, p in sorted(self.parts.items()):
            for pad, pin in sorted(p.get("pins", {}).items()):
                self.att.setdefault(pin["net"], []).append((ref, pad, pin))

    def nclass(self, net):
        return (self.nets.get(net) or {}).get("class")

    def is_rail(self, net):
        """A power or ground net: by IR class, or because a pin on it is a supply pin (+5V from a module is class signal)."""
        return self.nclass(net) in ("power", "ground") or any(
            pin.get("class") in ("power_in", "power_out") for _r, _p, pin in self.att.get(net, []))

    def two_pin(self, ref):
        pins = [pin for _k, pin in sorted(self.parts[ref].get("pins", {}).items())]
        return pins if len(pins) == 2 else None

    def by_name(self, ref):
        return {pin.get("name"): pin["net"] for pin in self.parts[ref].get("pins", {}).values()}

    def zero_ohm(self, ref):
        return self.etype[ref] == "R" and parse_resistance(self.parts[ref].get("value", "")) == 0


def _supply_nodes(d, start):
    """Nets at the same DC node as `start` through fuses, inductors and 0R links -> {net: {fused, via}}."""
    seen = {start: {"fused": False, "via": []}}
    todo = [start]
    while todo:
        net = todo.pop()
        for ref, _pad, _pin in d.att.get(net, []):
            et = d.etype[ref]
            if not (et in ("FUSE", "L") or d.zero_ohm(ref)):
                continue
            pins = d.two_pin(ref)
            if not pins:
                continue
            a, b = pins[0]["net"], pins[1]["net"]
            other = b if a == net else a if b == net else None
            if other is None or other == net or d.nclass(other) == "ground":
                continue
            st = seen[net]
            if other not in seen:
                seen[other] = {"fused": st["fused"] or et == "FUSE", "via": st["via"] + [ref]}
                todo.append(other)
            elif et == "FUSE" and not seen[other]["fused"]:
                seen[other]["fused"] = True
    return seen


def _esd_ic(part):
    return (part.get("electrical") or {}).get("role") in ("clamp", "esd")


def _clamps(d, nodes, to_rail=False):
    """Refs of surge/ESD clamps on any of `nodes`. to_rail=False: a TVS/zener/ESD IC whose other side is ground. to_rail=True
    (signals): additionally any non-LED diode whose other pin is on a power or ground net (a flyback / steering clamp)."""
    found = []
    for net in nodes:
        for ref, _pad, _pin in d.att.get(net, []):
            et, pins = d.etype[ref], d.two_pin(ref)
            if et == "CLAMP" and pins:
                other = [p["net"] for p in pins if p["net"] != net]
                if other and d.nclass(other[0]) == "ground":
                    found.append(ref)
            elif _esd_ic(d.parts[ref]) and any(d.nclass(p["net"]) == "ground" for p in d.parts[ref]["pins"].values()):
                found.append(ref)
            elif to_rail and et == "DIODE" and pins:
                other = [p["net"] for p in pins if p["net"] != net]
                if other and d.is_rail(other[0]):
                    found.append(ref)
    return sorted(set(found))


def _only_path(d, nodes, guard, decl_pins):
    """True when `guard` (a series diode / P-FET) is the ONLY way from the supply node set to any load: everything else on
    those nets is a fuse, inductor, capacitor, clamp, 0R link, the guard itself or the declaring connector pin. A diode on a
    branch (a 1N4007 in front of a regulator while the other loads hang straight on the rail) protects nothing else."""
    for net in nodes:
        for ref, pad, _pin in d.att.get(net, []):
            if ref == guard or d.etype[ref] in ("FUSE", "L", "C", "CLAMP") or d.zero_ohm(ref) or "%s.%s" % (ref, pad) in decl_pins:
                continue
            if d.parts[ref].get("kind") == "connector" and d.nclass(d.parts[ref]["pins"][pad]["net"]) == "ground":
                continue
            return False
    return True


def _reverse_protection(d, nodes, decl_pins=()):
    """-> (kind, ref) of the first reverse-polarity protection on the supply node set, else None."""
    for net, st in sorted(nodes.items()):
        for ref, _pad, _pin in d.att.get(net, []):
            et = d.etype[ref]
            names = d.by_name(ref)
            if et in ("DIODE", "CLAMP"):
                if names.get("K") == net and d.nclass(names.get("A")) == "ground" and st["fused"]:
                    return ("crowbar behind fuse " + ", ".join(st["via"]), ref)
                if (et == "DIODE" and names.get("A") == net and names.get("K") not in nodes and d.nclass(names.get("K")) != "ground"
                        and _only_path(d, nodes, ref, decl_pins)):
                    return ("series diode", ref)
            elif et == "FET" and {"G", "D", "S"} <= set(names):
                chan = (names["D"], names["S"])
                if (net in chan and (set(chan) - set(nodes)) and d.nclass(names["G"]) == "ground"
                        and _only_path(d, nodes, ref, decl_pins)):
                    return ("series P-FET", ref)
    return None


def _signal_class(d, net):
    """-> dict(cls, hops, protection, active) for a signal net."""
    seen, hops, todo, clamps = {net: 0}, 0, [net], []
    while todo:
        n = todo.pop(0)
        clamps += _clamps(d, [n], to_rail=True)
        for ref, _pad, _pin in d.att.get(n, []):
            if d.etype[ref] != "R" and not d.zero_ohm(ref):
                continue
            pins = d.two_pin(ref)
            if not pins:
                continue
            o = [p["net"] for p in pins if p["net"] != n]
            if not o or d.is_rail(o[0]) or o[0] in seen:
                continue                                          # a pull to a rail is not a path
            h = seen[n] + (0 if d.zero_ohm(ref) else 1)
            if h <= MAX_R_HOPS:
                seen[o[0]] = h
                hops = max(hops, h)
                todo.append(o[0])
    active = sorted({ref for n in seen for ref, _p, _pin in d.att.get(n, [])
                     if d.etype[ref] in ("IC", "REG", "FET") and d.parts[ref].get("kind") != "connector"})
    isolated = bool(active) and all((d.parts[r].get("electrical") or {}).get("role") == "optocoupler" for r in active)
    clamps = sorted(set(clamps))
    shunt = sorted({ref for n in seen if seen[n] >= 1 for ref, _p, _pin in d.att.get(n, []) if d.etype[ref] == "C"
                    and d.two_pin(ref) and any(d.nclass(q["net"]) == "ground" for q in d.two_pin(ref))})
    cls = ("protected" if clamps else "isolated" if isolated else "filtered" if (hops and shunt)
           else "series-R-only" if hops else "bare")
    return {"cls": cls, "hops": hops, "protection": clamps or shunt, "active": active}


def classify(ir):
    """Per external net: [{net, connector, pins, kind, cls, protection, missing, ...}] plus the NOT_JUDGED notes.
    -> (rows, notes). Deterministic order. Used by the rule and by the CLI table."""
    d = _Design(ir)
    rows, notes, by_net = [], [], {}
    ext = d.ext
    for ref, p in sorted(d.parts.items()):
        if p.get("kind") != "connector":
            continue
        declared = sorted(k.split(".", 1)[1] for k in ext["pins"] if k.split(".", 1)[0] == ref)
        if not ext.get("declared"):
            notes.append((ref, "connector %s: netlist.py declares no EXTERNAL at all" % ref, []))
        elif ref in ext.get("none", []):
            continue
        elif not declared:
            notes.append((ref, "connector %s has no EXTERNAL entry (declare its pins, or 'none' if nothing leaves the board)" % ref, []))
        else:
            missing = sorted(pad for pad, pin in p["pins"].items()
                             if pad not in declared and d.nclass(pin["net"]) != "ground")
            if missing:
                notes.append((ref, "connector %s: connected pin(s) %s are not in EXTERNAL" % (ref, ", ".join(missing)),
                              [p["pins"][m]["net"] for m in missing]))
    for term, e in sorted(ext["pins"].items(), key=lambda kv: (kv[0].split(".", 1)[0], kv[0])):
        ref, pad = term.split(".", 1)
        pin = d.parts[ref]["pins"][pad]
        net = pin["net"]
        if d.nclass(net) == "ground":
            continue
        module = pin.get("class") not in (None, "passive")
        row = by_net.get(net)
        if row is None:
            row = by_net[net] = {"net": net, "connector": ref, "pins": [], "dirs": set(), "module": True, "i": None}
            rows.append(row)
        row["pins"].append(term)
        if not module:
            row["dirs"].add(e.get("dir"))
            if row["module"]:
                row["connector"] = ref                            # name the field connector, not the module socket
            row["module"] = False
            if e.get("i") is not None:
                row["i"] = e["i"]
    for row in rows:
        net = row["net"]
        if row["module"]:
            row.update(kind="module", cls="module", protection=[], missing=[])
        elif "supply" in row["dirs"]:
            nodes = _supply_nodes(d, net)
            clamp = _clamps(d, nodes)
            rev = _reverse_protection(d, nodes, set(row["pins"]))
            fuses = sorted({r for st in nodes.values() for r in st["via"] if d.etype[r] == "FUSE"})
            missing = []
            if not clamp:
                missing.append("clamp")
            if rev is None:
                missing.append("reverse")
            if row["i"] is not None and not fuses:
                missing.append("fuse")
            row.update(kind="supply", cls="protected" if not missing else "unprotected", missing=missing,
                       protection=sorted(set(clamp + ([rev[1]] if rev else []) + fuses)), reverse=rev[0] if rev else None, nodes=sorted(nodes))
        elif d.is_rail(net) and row["dirs"] <= {"out", None}:
            row.update(kind="supply-output", cls="supply-output", protection=[], missing=[])
        else:
            row.update(kind="signal", missing=[], **_signal_class(d, net))
            if row["cls"] in ("bare", "series-R-only"):
                row["missing"] = ["clamp"]
            out_only = row["dirs"] <= {"out"}
            expansion = row["connector"] in ext.get("classes", {})
            row["sev"] = "WARN" if (expansion or (out_only and row["cls"] == "series-R-only")) else "ERROR"
            row["expansion"] = expansion
    return rows, notes


@rule(id="EL-CONN-PROT", severity="ERROR", needs=("parts", "nets", "external"), doc="docs/rules/EL-CONN-PROT.md",
      fixture="tests/rules/fixtures/EL-CONN-PROT", mutation="M-prot", applies=lambda ir: "external" in ir)
def check(ctx):
    ir = {"parts": ctx.ir["parts"], "nets": ctx.ir["nets"], "external": ctx.ir["external"]}
    d = _Design(ir)
    rows, notes = classify(ir)
    for ref, why, nets in notes:
        ctx.examined()
        yield ctx.not_judged(why, where={"ref": ref}, nets=nets, target=ref)
    fix = {"clamp": "Add a TVS/zener (cathode to the net, anode to GND) right at the connector, e.g. SMBJ/P6KE of a standoff above the working voltage.",
           "reverse": "Add reverse-polarity protection after the connector: a series Schottky/diode, a P-FET, or a TVS across the rail BEHIND the fuse.",
           "fuse": "Add a fuse or PTC between the connector and the rest of the board, rated above the load and below the connector/trace rating."}
    by_conn = {}
    for row in rows:
        ctx.examined(len(row["pins"]))
        if row["kind"] == "supply":
            term = sorted(t for t in row["pins"] if d.parts[t.split(".")[0]]["pins"][t.split(".")[1]].get("class") in (None, "passive"))[0]
            ref, pad = term.split(".", 1)
            for m in row["missing"]:
                what = {"clamp": "no surge/TVS clamp to GND on the supply input",
                        "reverse": "no reverse-polarity protection (no series diode/P-FET, no TVS crowbar behind a fuse)",
                        "fuse": "no fuse/PTC between the connector and the board (source current i = %g A declared)" % (row["i"] or 0)}[m]
                yield ctx.finding("ERROR", "external supply %s, %s" % (row["net"], what),
                                  where={"ref": ref, "pin": pad, "net": row["net"]}, nets=[row["net"]], fix=fix[m])
        elif row["kind"] == "signal" and row["missing"]:
            by_conn.setdefault((row["connector"], row["sev"]), []).append(row)
        elif row["kind"] == "signal" and row["cls"] == "filtered":
            by_conn.setdefault((row["connector"], "INFO"), []).append(row)
    for ref, sev in sorted(by_conn):
        rs = sorted(by_conn[(ref, sev)], key=lambda r: r["net"])
        listing = ", ".join("%s (%s)" % (r["net"], r["cls"]) for r in rs)
        n = len(rs)
        if sev == "INFO":
            yield ctx.finding("INFO", "%d external signal net%s protected by an RC filter (series R + shunt C to GND): %s"
                              % (n, "" if n == 1 else "s", listing), where={"ref": ref}, nets=[r["net"] for r in rs], refs=[ref])
            continue
        lead = "expansion header: protection is the user's responsibility; " if rs[0]["expansion"] else ""
        what = "driven only through a series resistor" if sev == "WARN" and not rs[0]["expansion"] else "with no clamp"
        yield ctx.finding(sev, "%s%d external signal net%s %s: %s" % (lead, n, "" if n == 1 else "s", what, listing),
                          where={"ref": ref}, nets=[r["net"] for r in rs], refs=[ref],
                          fix=fix["clamp"] + " Unprotected nets are listed with their class; a waiver needs a `why`.")
