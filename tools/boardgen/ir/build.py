"""Build the design IR: projects/<id>/out/design.json   (pipeline stage `ir`).

    python tools/boardgen/ir/build.py <project-id>
    python tools/boardgen/ir/build.py --selftest       (offline: schema, determinism, cross-check fault injection)

1. from_netlist.build()        meta, parts, nets, assembly, fab_profile   (netlist.py + parts registry)
2. from_kicad_pcb.parse_board()  board                                      (only when <id>.kicad_pcb exists)
3. cross_check()               the netlist's net -> pins must EQUAL the board's pad nets (independent consistency check)
4. validate against schema.json (ir_version 2)
5. write canonical JSON (sorted keys, no timestamps) - byte-identical for identical inputs.

Fail closed: any IRError, any cross-check ERROR or any schema violation prints the reasons, REMOVES a stale design.json
(an old IR must never be mistaken for the current one) and exits 1.
Cross-check ERRORs: a pad on a different net (or none) on the board than in netlist.py; a netlist pad missing on the board;
a netlist part with no footprint, or a footprint with no netlist part (unless attr board_only: mounting holes etc.);
track / via / zone on a net the netlist does not have.  WARNs (do not fail): footprint library id differs.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from boardgen.ir import IR_VERSION, IRError, canonical_json, natkey, sha256_text_file       # noqa: E402
from boardgen.ir import from_kicad_pcb, from_netlist                                        # noqa: E402

SCHEMA_PATH = os.path.join(HERE, "schema.json")


def load_schema():
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate(ir, engine=None):
    """List of 'path: message' schema violations (empty = valid). engine: "jsonschema" (when installed), "builtin" (the
    registry's own stdlib validator, same JSON-Schema subset as parts/schema.json) or None = jsonschema if available."""
    sch = load_schema()
    if engine is None:
        try:
            import jsonschema  # noqa: F401
            engine = "jsonschema"
        except ImportError:
            engine = "builtin"
    if engine == "builtin":
        from boardgen import parts as _parts
        errs = []
        _parts._check(ir, sch, "", errs)
        return ["%s: %s" % (p or "(root)", m) for p, m in errs]
    import jsonschema
    v = jsonschema.Draft7Validator(sch)
    return sorted({"%s: %s" % (".".join(str(p) for p in e.absolute_path) or "(root)", e.message[:200])
                   for e in v.iter_errors(ir)})


def cross_check(ir):
    """(errors, warnings) comparing ir['nets'] (from netlist.py) with the board's pad nets (ir['board'])."""
    board = ir["board"]
    errors, warns = [], []
    parts = ir["parts"]
    # ---- footprints <-> parts
    for ref in parts:
        if ref not in board["footprints"]:
            errors.append("part %s is in netlist.py but has no footprint on the board" % ref)
    for ref, fp in board["footprints"].items():
        if ref not in parts and "board_only" not in fp["attr"]:
            errors.append("footprint %s (%s) is on the board but not in netlist.py (and not attr board_only)"
                          % (ref, fp["lib_id"]))
        elif ref in parts and parts[ref]["footprint"] != fp["lib_id"]:
            warns.append("footprint %s: netlist.py says %s, board has %s" % (ref, parts[ref]["footprint"], fp["lib_id"]))
    # ---- net -> pins, both sides, over the parts both sides know
    board_pin_net = {}                                       # 'ref.pad' -> {nets seen} (a duplicated pad number may differ)
    for p in board["pads"].values():
        if p["ref"] in parts and p["pad"] != "":
            board_pin_net.setdefault("%s.%s" % (p["ref"], p["pad"]), set()).add(p["net"])
    nl_pin_net = {pin: name for name, n in ir["nets"].items() for pin in n["pins"]}
    for pin in sorted(set(nl_pin_net) | set(board_pin_net), key=lambda s: [natkey(x) for x in s.split(".", 1)]):
        want, got = nl_pin_net.get(pin), board_pin_net.get(pin)
        if got is None:
            errors.append("pad %s is on net %s in netlist.py but does not exist on the board" % (pin, want))
        elif got != {want}:
            show = ", ".join(sorted("no net" if g is None else g for g in got))
            errors.append("pad %s: netlist.py puts it on %s, the board has %s"
                          % (pin, want if want else "no net (not connected)", show))
    # ---- copper on nets the netlist does not know
    known = set(ir["nets"])
    for kind, nets in (("track", set(board["tracks"]) - {from_kicad_pcb.NO_NET}),
                       ("via", {v["net"] for v in board["vias"] if v["net"]}),
                       ("zone", {z["net"] for z in board["zones"] if z["net"]})):
        for n in sorted(nets - known):
            errors.append("%s on net %s, which netlist.py does not have" % (kind, n))
    return errors, warns


def build(project_id):
    """Return (ir, errors, warnings). ir is None when it cannot be built at all."""
    ir = {"ir_version": IR_VERSION, "requirements": []}
    ir.update(from_netlist.build(project_id))
    nl_dir = os.path.join(ROOT, "projects", project_id)
    pcb = os.path.join(nl_dir, project_id + ".kicad_pcb")
    if not os.path.isfile(pcb):
        from boardgen import project as _project
        prj = getattr(_project.load_netlist(project_id), "PRJ_NAME", project_id)
        pcb = os.path.join(nl_dir, prj + ".kicad_pcb")
    errors, warns = [], []
    if os.path.isfile(pcb):
        ir["board"] = from_kicad_pcb.parse_board(pcb)
        ir["meta"]["input_hashes"]["projects/%s/%s" % (project_id, os.path.basename(pcb))] = sha256_text_file(pcb)
        errors, warns = cross_check(ir)
    ir["meta"]["input_hashes"] = dict(sorted(ir["meta"]["input_hashes"].items()))
    errors += ["schema: " + e for e in validate(ir)]
    return ir, errors, warns


def out_path(project_id):
    return os.path.join(ROOT, "projects", project_id, "out", "design.json")


def selftest():
    """Offline self-test (CI): the shipped schema is valid and both validators accept/reject correctly; the blinky-555
    fixture builds, cross-checks clean and is byte-identical across two builds; cross_check() flags each injected fault.
    Returns a list of failure messages (empty = pass)."""
    import copy
    bad = []
    engines = ["builtin"]
    try:
        import jsonschema
        jsonschema.Draft7Validator.check_schema(load_schema())
        engines.append("jsonschema")
    except ImportError:
        pass
    ir, errors, warns = build("blinky-555")
    if errors:
        return ["blinky-555 IR does not build clean: %s" % errors[:3]]
    if canonical_json(build("blinky-555")[0]) != canonical_json(ir):
        bad.append("IR is not deterministic across two builds")
    for eng in engines:
        if validate(ir, eng):
            bad.append("%s rejects a valid IR: %s" % (eng, validate(ir, eng)[:2]))
        for name, mut in (("missing meta.project", lambda x: x["meta"].pop("project")),
                          ("bad net class", lambda x: x["nets"]["VCC"].update({"class": "x"})),
                          ("unknown field", lambda x: x["parts"]["R1"].update({"extra": 1})),
                          ("wrong ir_version", lambda x: x.update({"ir_version": 1}))):
            x = copy.deepcopy(ir)
            mut(x)
            if not validate(x, eng):
                bad.append("%s accepts an invalid IR (%s)" % (eng, name))
    faults = (("pad on another net", lambda x: x["board"]["pads"]["R1.2"].update({"net": "GND"})),
              ("pad not connected", lambda x: x["board"]["pads"]["R1.2"].update({"net": None})),
              ("pad missing", lambda x: x["board"]["pads"].pop("R1.2")),
              ("footprint missing", lambda x: x["board"]["footprints"].pop("R1")),
              ("extra footprint", lambda x: x["board"]["footprints"].update(
                  {"Z9": {"lib_id": "a:b", "x": 0, "y": 0, "rot": 0, "side": "front", "attr": []}})),
              ("copper on unknown net", lambda x: x["board"]["vias"].append(
                  {"x": 0, "y": 0, "net": "NOPE", "size": 0.8, "drill": 0.4, "layers": ["F.Cu", "B.Cu"]})))
    for name, mut in faults:
        x = copy.deepcopy(ir)
        mut(x)
        if not cross_check(x)[0]:
            bad.append("cross_check misses: %s" % name)
    bad += _selftest_electrical(ir)
    from boardgen.ir import coverage
    msg = coverage.check_golden()
    if msg:
        bad.append(msg)
    return bad


def _selftest_electrical(ir):
    """P2-T2: EXTERNAL grammar, pin/part electrical resolution and the schema's v2 fields."""
    import copy
    import types
    from boardgen.ir import IRError, elec
    bad = []
    parts = {"J1": {"pins": {"1": {}, "2": {}}}, "J2": {"pins": {"1": {}}}}
    nl = types.SimpleNamespace()
    if elec.parse_external(nl, parts) != {"declared": False, "pins": {}, "none": []}:
        bad.append("EXTERNAL absent must be declared=false")
    nl.EXTERNAL = {}
    if elec.parse_external(nl, parts) != {"declared": True, "pins": {}, "none": []}:
        bad.append("EXTERNAL = {} must be declared=true with nothing external")
    nl.EXTERNAL = {"J1.1": {"v": (4.4, 5.25), "i": 0.5, "dir": "supply", "why": "USB VBUS"}, "J2": "none"}
    got = elec.parse_external(nl, parts)
    if got["pins"]["J1.1"] != {"v": [4.4, 5.25], "i": 0.5, "dir": "supply", "why": "USB VBUS"} or got["none"] != ["J2"]:
        bad.append("EXTERNAL grammar not parsed: %s" % got)
    for name, ext in (("unknown ref", {"J9.1": {}}), ("unknown pad", {"J1.7": {}}), ("bare ref not none", {"J1": {}}),
                      ("bad v", {"J1.1": {"v": (5, 4)}}), ("bad dir", {"J1.1": {"dir": "x"}}), ("unknown key", {"J1.1": {"z": 1}})):
        nl.EXTERNAL = ext
        try:
            elec.parse_external(nl, parts)
            bad.append("EXTERNAL accepted: %s" % name)
        except IRError:
            pass
    u1 = ir["parts"]["U1"]["pins"]
    if not (u1["2"]["abs_max"] and u1["2"]["abs_max"]["cited"] and u1["2"]["abs_max"]["v_max"] == "pin:8+0"):
        bad.append("NE555 TRIG abs_max not carried into the IR as cited: %s" % u1["2"]["abs_max"])
    if ir["parts"]["D1"]["electrical_status"] != "ok" or not ir["parts"]["D1"]["electrical"]["vf"]:
        bad.append("RED LED family electrical data missing from the IR")
    rec = {"pins": {"1": {"name": "A", "class": "input", "abs_max": {"v_max": 5}}},
           "electrical": {"pins": {"1": {"abs_max": {"v_max": 3.6, "src": "x"}}}}}
    cls, am, io = elec.resolve_pin(rec, "1", "ok")
    if (cls, am["v_max"], am["cited"]) != ("input", 3.6, True):
        bad.append("electrical abs_max must replace the legacy one")
    cls, am, io = elec.resolve_pin(rec, "1", "value_not_covered")
    if am["cited"] or am["v_max"] != 5:
        bad.append("a value-not-covered part must fall back to the legacy abs_max as uncited")
    from boardgen import parts as _parts
    r = copy.deepcopy(_parts.get("ne555p-dip8"))
    r["electrical"]["pins"]["8"]["abs_max"].pop("src")
    if not any("no `src`" in m for m in _parts.electrical_problems(r)):
        bad.append("a record number without src must be rejected")
    return bad


def main(argv):
    if argv == ["--selftest"]:
        bad = selftest()
        for b in bad:
            print("FAIL ir selftest: " + b)
        print("ir selftest: %s" % ("FAILED (%d)" % len(bad) if bad else "ok"))
        return 1 if bad else 0
    if argv and argv[0] == "--coverage":
        if argv[1:] not in ([], ["--write-golden"]):
            print("usage: build.py --coverage [--write-golden]")
            return 2
        from boardgen.ir import coverage
        return coverage.main(write_golden=bool(argv[1:]))
    if len(argv) != 1 or argv[0].startswith("-"):
        print("usage: build.py <project-id> | --coverage [--write-golden] | --selftest")
        return 2
    pid = argv[0]
    dst = out_path(pid)
    try:
        ir, errors, warns = build(pid)
    except IRError as e:
        ir, errors, warns = None, [str(e)], []
    except SystemExit as e:                                   # project.load_netlist: unknown project
        ir, errors, warns = None, [str(e)], []
    for w in warns:
        print("WARN ir: " + w)
    if errors or ir is None:
        for e in errors:
            print("ERROR ir: " + e)
        if os.path.isfile(dst):
            os.remove(dst)
            print("removed stale %s" % os.path.relpath(dst, ROOT))
        print("FAILED: design IR for %s not written (%d error(s))" % (pid, len(errors)))
        return 1
    text = canonical_json(ir)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, dst)
    b = ir.get("board")
    print("ir %s: %d parts, %d nets%s -> %s (%d bytes)" % (
        pid, len(ir["parts"]), len(ir["nets"]),
        ", board %d footprints / %d pads / %d tracked nets / %d vias / %d zones, cross-check clean"
        % (len(b["footprints"]), len(b["pads"]), len(b["tracks"]), len(b["vias"]), len(b["zones"])) if b else ", no board",
        os.path.relpath(dst, ROOT), len(text.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
