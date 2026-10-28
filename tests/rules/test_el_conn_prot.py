"""EL-CONN-PROT tests (P2-T7): python tests/rules/test_el_conn_prot.py   (system Python, stdlib, no KiCad). Exit 1 on failure.
Builds on the rule's green fixture and flips one thing at a time. If projects/reflex-machine/out/design.json exists
(run `python pipeline.py reflex-machine --only ir`) the same flips are applied to the real board's IR."""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from boardgen.rules import engine                                # noqa: E402
from boardgen.rules.el_conn_prot import classify                 # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "  -> " + str(detail)))
    if not cond:
        FAILS.append(name)


def run(ir):
    engine.REGISTRY.load_builtin()
    f, _s = engine.REGISTRY.run(ir, only=["EL-CONN-PROT"])
    return f


def lines(fs):
    return [x.line() for x in fs]


def pin(net, name, cls="passive"):
    return {"net": net, "name": name, "class": cls}


with open(os.path.join(ROOT, "tests", "rules", "fixtures", "EL-CONN-PROT", "green.json"), encoding="utf-8") as fh:
    GREEN = json.load(fh)["ir"]

check("green: no finding", run(GREEN) == [], lines(run(GREEN)))

ir = copy.deepcopy(GREEN)
del ir["parts"]["F1"]                                            # fuse removed: J1 now feeds VIN straight
for p in ir["parts"].values():
    for q in p["pins"].values():
        if q["net"] == "VIN_RAW":
            q["net"] = "VIN"
f = run(ir)
check("no fuse: the crowbar no longer counts (it needs a fuse) and the missing fuse is reported",
      len(f) == 2 and any("reverse-polarity" in x.why for x in f) and any("fuse/PTC" in x.why for x in f), lines(f))

ir = copy.deepcopy(GREEN)
ir["external"]["pins"]["J1.1"]["i"] = None
del ir["parts"]["F1"]
for p in ir["parts"].values():
    for q in p["pins"].values():
        if q["net"] == "VIN_RAW":
            q["net"] = "VIN"
check("no fuse and no source current declared: fuse not demanded, but the crowbar still needs one", len(run(ir)) == 1, lines(run(ir)))

ir = copy.deepcopy(GREEN)
del ir["parts"]["D2"]                                            # the signal TVS removed
f = run(ir)
check("signal without clamp: one grouped ERROR naming the net and its class",
      len(f) == 1 and f[0].where == {"ref": "J2"} and "SIG_X (bare)" in f[0].why, lines(f))

ir = copy.deepcopy(GREEN)
del ir["parts"]["D2"]
ir["parts"]["R1"] = {"kind": "generic", "lib_id": "Device:R", "value": "470R", "pins": {"1": pin("SIG_X", "~"), "2": pin("SIG_Y", "~")}}
ir["parts"]["U1"]["pins"]["1"]["net"] = "SIG_Y"
ir["nets"]["SIG_Y"] = {"class": "signal"}
f = run(ir)
check("series resistor only: class series-R-only", len(f) == 1 and "SIG_X (series-R-only)" in f[0].why, lines(f))

ir2 = copy.deepcopy(ir)                                          # a flyback-style diode to a rail behind the resistor
ir2["parts"]["D9"] = {"kind": "generic", "lib_id": "Device:D", "value": "1N4148", "pins": {"1": pin("SIG_Y", "K"), "2": pin("GND", "A")}}
check("a diode to a rail behind the series R counts as a clamp", run(ir2) == [], lines(run(ir2)))

ir = copy.deepcopy(GREEN)
del ir["parts"]["D2"]
ir["parts"]["J2"]["pins"]["1"]["class"] = "bidirectional"      # the connector is a module socket (record class not passive)
check("module-interface pin: not field wiring, no clamp required", run(ir) == [], lines(run(ir)))

ir = copy.deepcopy(GREEN)
del ir["parts"]["D2"]
ir["parts"]["U1"]["electrical"] = {"role": "optocoupler"}
check("only an optocoupler behind the net: isolated, not an ERROR", run(ir) == [], lines(run(ir)))

ir = copy.deepcopy(GREEN)
ir["external"] = {"declared": False, "none": [], "pins": {}}
f = run(ir)
check("EXTERNAL not declared: every connector NOT_JUDGED, nothing passes silently",
      sorted(x.where["ref"] for x in f) == ["J1", "J2"] and all(x.severity == "NOT_JUDGED" for x in f), lines(f))

ir = copy.deepcopy(GREEN)
ir["parts"]["J2"]["pins"]["2"] = pin("SIG_Z", "Pin_2")
ir["nets"]["SIG_Z"] = {"class": "signal"}
f = run(ir)
check("a connected pin missing from an otherwise declared connector is NOT_JUDGED",
      len(f) == 1 and f[0].severity == "NOT_JUDGED" and "SIG_Z" in f[0].nets, lines(f))

ir = copy.deepcopy(GREEN)
ir["external"]["none"] = ["J2"]
del ir["external"]["pins"]["J2.1"]
check("a connector declared 'none' is skipped", run(ir) == [], lines(run(ir)))

ir = copy.deepcopy(GREEN)
del ir["parts"]["D1"]
ir["parts"]["Q1"] = {"kind": "part", "lib_id": "Device:Q_PMOS_GSD", "value": "P-FET",
                     "pins": {"1": pin("GND", "G", "input"), "2": pin("VIN_RAW", "S", "passive"), "3": pin("VIN_FET", "D", "passive")}}
ir["nets"]["VIN_FET"] = {"class": "power"}
ir["parts"]["U1"]["pins"]["2"]["net"] = "VIN_FET"
ir["parts"]["Q1"]["electrical"] = {"role": "mosfet"}
f = run(ir)
check("P-FET in series gives reverse protection (the surge clamp is still reported missing)",
      len(f) == 1 and "clamp" in f[0].why, lines(f))

rows, _n = classify(GREEN)
check("classify: supply protected / signal protected", [(r["kind"], r["cls"]) for r in rows] == [("supply", "protected"), ("signal", "protected")],
      [(r["kind"], r["cls"]) for r in rows])

path = os.path.join(ROOT, "projects", "reflex-machine", "out", "design.json")
if os.path.isfile(path):
    with open(path, encoding="utf-8") as fh:
        real = json.load(fh)
    base = [x.where.get("ref") for x in run(real) if x.severity == "ERROR"]
    check("reflex-machine as built: the 12 V input is fine, the cable and header connectors are not",
          "J1" not in base and {"J13", "J14", "J15", "J16", "J17"} <= set(base), base)
    m = copy.deepcopy(real)
    del m["parts"]["D1"]                                         # M-prot on the real IR: the P6KE15A TVS removed
    f = [x for x in run(m) if x.where.get("ref") == "J1"]
    check("reflex-machine without D1: clamp and reverse protection reported on J1.1", len(f) == 2, lines(f))
    m = copy.deepcopy(real)
    del m["parts"]["F1"]
    for p in m["parts"].values():
        for q in p["pins"].values():
            if q["net"] == "+12V_IN":
                q["net"] = "+12V"
    f = [x for x in run(m) if x.where.get("ref") == "J1"]
    check("reflex-machine without F1: fuse and crowbar reported on J1.1", len(f) == 2, lines(f))
else:
    print("  skip reflex-machine IR checks (no out/design.json; run: python pipeline.py reflex-machine --only ir)")

print("%s: %d failure(s)" % ("test_el_conn_prot", len(FAILS)))
sys.exit(1 if FAILS else 0)
