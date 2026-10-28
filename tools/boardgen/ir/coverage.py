"""Electrical-data coverage table (P2-T2): which required electrical fields each project's parts have, and which the
analyzer would have to report NOT_JUDGED (docs/design/P2_ELECTRICAL_ANALYZER.md 4.1, 4.2).

    python tools/boardgen/ir/build.py --coverage                  print the table for every project with a netlist.py
    python tools/boardgen/ir/build.py --coverage --write-golden   rewrite tests/ir/elec_coverage.golden.txt
    python tools/boardgen/ir/build.py --selftest                  compares the table with the golden file (CI)

Stdlib only, no KiCad: it reads netlist.py + the parts registry through from_netlist.build(), exactly what the IR holds.
Deterministic (sorted, no dates, no counts that depend on stock/price). A field counts as PRESENT only when the datasheet
number is cited (record electrical block with `src`); the legacy signed pins.*.abs_max count as NOT cited (cited=false) -
they are agent-read / illustrative (parts notes), so for the pcba tier they are NOT_JUDGED, as spec 4.3 says.

Required fields per part (tier hand = needed for a hand-assembled release, pcba = needed for a pcba release; hand is a
subset of pcba):
  every registered active part (kind part)   class on every pin, cited abs_max (v_min or v_max) on every pin that is not
                                             passive/nc/ground                                                      pcba
  regulator (role regulator)                 regulator.vout, regulator.dropout (ldo only), theta_ja, tj_max         hand+pcba
  logic / mcu / sensor                       vih+vil on input pins, voh+vol on output/bidirectional pins, vol on open_collector
                                             pins, load_ma.typ and load_ma.peak                                     pcba
  mosfet                                     rds_on, vth, theta_ja, tj_max                                          pcba
  optocoupler                                vf, ctr_pct                                                            pcba
  led / rectifier                            vf                                                                     pcba
  resistor                                   p_max_mw                                                               pcba
  clamp (TVS/ESD)                            clamp.v_breakdown, clamp.v_clamp                                       pcba
  every connector                            an EXTERNAL declaration (a pin entry or 'none')                        hand+pcba
  every part with no registry record         the record itself                                                      pcba
Parts that are plain passives with no role (capacitors, switches, mechanical) need nothing in this version.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
GOLDEN = os.path.join(ROOT, "tests", "ir", "elec_coverage.golden.txt")
GROUND_PIN = re.compile(r"^(GND|AGND|DGND|PGND|GNDA|GNDD|VSS|EPAD|0V)$", re.I)

REGISTRY_REPORT = ("esp32-s3-wroom-1-n8", "ldl1117s33r-sot2234", "ams1117-3.3", "usblc6-2sc6", "sht30-dis-b2.5ks-dfn8ep2.5x2.5")


def _present(d):
    """A datum / datum list is present when some number in it is non-null."""
    if isinstance(d, list):
        return any(_present(x) for x in d)
    return isinstance(d, dict) and any(d.get(k) is not None for k in ("min", "typ", "max"))


def _pin_items(part, ground_pins):
    """Per-pin required items: (field, tier, ok, pin)."""
    out = []
    el = part.get("electrical") or {}
    role = el.get("role")
    for pad, pin in part["pins"].items():
        cls = pin["class"]
        out.append(("pin.class", "pcba", cls is not None, pad))
        if cls in ("passive", "nc") or pad in ground_pins:
            continue
        am = pin["abs_max"]
        out.append(("pin.abs_max", "pcba", bool(am and am["cited"] and (am["v_min"] is not None or am["v_max"] is not None)), pad))
        io = pin["io"] or {}
        if role in ("logic", "mcu", "sensor"):
            if cls == "input":
                out.append(("pin.vih", "pcba", _present(io.get("vih")), pad))
                out.append(("pin.vil", "pcba", _present(io.get("vil")), pad))
            elif cls in ("output", "bidirectional"):
                out.append(("pin.voh", "pcba", _present(io.get("voh")), pad))
                out.append(("pin.vol", "pcba", _present(io.get("vol")), pad))
            elif cls == "open_collector":
                out.append(("pin.vol", "pcba", _present(io.get("vol")), pad))
    return out


def part_items(part, ground_pins, external):
    """[(field, tier, ok, pin_or_None)] for one IR part."""
    kind, el = part["kind"], part.get("electrical") or {}
    role = el.get("role")
    covered = part["electrical_status"] == "ok"
    if kind == "unregistered":
        return [("registry record", "pcba", False, None)]
    if kind == "mechanical":
        return []
    if kind == "connector":
        ok = part["ref"] in external["none"] or any(k.split(".", 1)[0] == part["ref"] for k in external["pins"])
        return [("EXTERNAL declaration", "hand", ok, None)]

    def has(*path):
        cur = el if covered else {}
        for p in path:
            cur = cur.get(p) if isinstance(cur, dict) else None
        return _present(cur)

    items = []
    if kind == "part":
        items += _pin_items(part, ground_pins)
    if role == "regulator":
        items.append(("regulator.vout", "hand", has("regulator", "vout"), None))
        if (el.get("regulator") or {}).get("topology") != "switcher_module":      # an LDO (or unknown) must state dropout
            items.append(("regulator.dropout", "hand", has("regulator", "dropout"), None))
        items.append(("theta_ja", "hand", has("theta_ja"), None))
        items.append(("tj_max", "hand", has("tj_max"), None))
    elif role in ("logic", "mcu", "sensor"):
        items.append(("load_ma.typ", "pcba", has("load_ma", "typ"), None))
        items.append(("load_ma.peak", "pcba", has("load_ma", "peak"), None))
    elif role == "mosfet":
        items += [("rds_on", "pcba", has("rds_on"), None), ("vth", "pcba", has("vth"), None),
                  ("theta_ja", "pcba", has("theta_ja"), None), ("tj_max", "pcba", has("tj_max"), None)]
    elif role == "optocoupler":
        items += [("vf", "pcba", has("vf"), None), ("ctr_pct", "pcba", has("ctr_pct"), None)]
    elif role in ("led", "rectifier"):
        items.append(("vf", "pcba", has("vf"), None))
    elif role == "resistor":
        items.append(("p_max_mw", "pcba", has("p_max_mw"), None))
    elif role == "clamp":
        items += [("clamp.v_breakdown", "pcba", has("clamp", "v_breakdown"), None),
                  ("clamp.v_clamp", "pcba", has("clamp", "v_clamp"), None)]
    return items


def _ground_pins(part, nets):
    return {pad for pad, pin in part["pins"].items()
            if nets.get(pin["net"], {}).get("class") == "ground" or (pin["name"] and GROUND_PIN.match(pin["name"]))}


def _project_table(ir):
    nets = ir["nets"]
    rows = []                                    # (key, field, tier, ok, ref, pin)
    for ref, part in ir["parts"].items():
        key = part["registry"] or ref
        if part["electrical_status"] == "value_not_covered":
            key = "%s (value %s not covered)" % (key, part["value"])
        for field, tier, ok, pin in part_items(part, _ground_pins(part, nets), ir["external"]):
            rows.append((key, field, tier, ok, ref, pin))
    return rows


def _fmt(rows, title):
    lines = [title]
    for tier in ("hand", "pcba"):
        sel = [r for r in rows if tier == "pcba" or r[2] == "hand"]
        ok = sum(1 for r in sel if r[3])
        lines.append("  %-5s required %4d   present %4d   NOT_JUDGED %4d" % (tier, len(sel), ok, len(sel) - ok))
    bad = {}
    for key, field, tier, ok, ref, pin in rows:
        if not ok:
            e = bad.setdefault((key, field, tier), {"refs": set(), "pins": set()})
            e["refs"].add(ref)
            if pin is not None:
                e["pins"].add(pin)
    if bad:
        lines.append("  NOT_JUDGED (part, field, tier first needed, refs, pins):")
    from boardgen.ir import natkey
    for (key, field, tier), e in sorted(bad.items()):
        refs = ",".join(sorted(e["refs"], key=natkey))
        pins = (" pins " + ",".join(sorted(e["pins"], key=natkey))) if e["pins"] else ""
        lines.append("    %s | %s | %s | %s%s" % (key, field, tier, refs, pins))
    return lines


def _registry_rows(rid):
    """Pseudo-part rows for a registry record that no project uses yet (ref-esp32 parts)."""
    from boardgen import parts as _parts
    from boardgen.ir import elec as _elec, natkey
    rec = _parts.get(rid)
    status, block = _elec.part_electrical(rec, "")
    pins = {}
    for pad in sorted(rec["pins"], key=natkey):
        cls, am, io = _elec.resolve_pin(rec, pad, status)
        pins[pad] = {"name": rec["pins"][pad]["name"], "net": "?", "class": cls, "abs_max": am, "io": io}
    part = {"ref": rid, "registry": rid, "kind": rec["kind"], "pins": pins, "electrical": block, "electrical_status": status}
    gp = {pad for pad, p in pins.items() if p["name"] and GROUND_PIN.match(p["name"])}
    return [(rid, f, t, ok, rid, pin) for f, t, ok, pin in part_items(part, gp, {"none": [], "pins": {}})]


def projects_with_netlist():
    out = []
    pdir = os.path.join(ROOT, "projects")
    for name in sorted(os.listdir(pdir)):
        if os.path.isfile(os.path.join(pdir, name, "gen", "netlist.py")):
            out.append(name)
    return out


def table():
    """The whole coverage report as text (deterministic)."""
    if os.path.join(ROOT, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
    from boardgen.ir import from_netlist
    lines = ["# electrical data coverage (P2-T2): required fields present vs NOT_JUDGED, per project",
             "# tier hand = needed for a hand-assembled release, pcba = needed for a pcba release (superset). See tools/boardgen/ir/coverage.py", ""]
    for pid in projects_with_netlist():
        ir = from_netlist.build(pid)
        lines += _fmt(_project_table(ir), "project %s (%d parts)" % (pid, len(ir["parts"]))) + [""]
    rows = []
    for rid in REGISTRY_REPORT:
        rows += _registry_rows(rid)
    lines += _fmt(rows, "registry records not yet used by a project (ref-esp32 parts; one pseudo-part each, nets unknown)")
    return "\n".join(lines) + "\n"


def main(write_golden=False):
    text = table()
    if write_golden:
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s" % os.path.relpath(GOLDEN, ROOT))
    sys.stdout.write(text)
    return 0


def check_golden():
    """Failure message or None: the coverage table must equal the committed golden (data changes are deliberate)."""
    if not os.path.isfile(GOLDEN):
        return "missing %s (run: python tools/boardgen/ir/build.py --coverage --write-golden)" % os.path.relpath(GOLDEN, ROOT)
    with open(GOLDEN, encoding="utf-8", newline="") as f:
        want = f.read().replace("\r\n", "\n")
    if table() != want:
        return ("electrical coverage differs from %s: if the change is intended run "
                "'python tools/boardgen/ir/build.py --coverage --write-golden' and review the diff" % os.path.relpath(GOLDEN, ROOT))
    return None
