"""Tests for the current budget and the rules on it (P2-T6): reproduces the hand calculation of projects/ref-esp32/ARCHITECTURE.md
section 2.2-2.4 on the synthetic power-path fixture (tests/rules/fixtures/EL-THERMAL/red.json holds the synth-ldo IR unchanged).

    python tests/elec/test_budget.py        (stdlib only, no KiCad; exit 0 = all pass)
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from boardgen.elec.budget import build_budget, ldo_power_w      # noqa: E402
from boardgen.elec.model import build_model                      # noqa: E402
from boardgen.rules import engine                                # noqa: E402
import fixtures as F                                             # noqa: E402

FAILED = []


def check(name, ok, detail=""):
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, (" - " + detail) if detail else ""))
    if not ok:
        FAILED.append(name)


def within(v, want, tol=0.02):
    return abs(v - want) <= tol * abs(want)


def load_ir():
    with open(os.path.join(ROOT, "tests", "rules", "fixtures", "EL-THERMAL", "red.json"), encoding="utf-8") as f:
        return json.load(f)["ir"]


def run(ir, rid):
    engine.REGISTRY.load_builtin()
    findings, _ = engine.REGISTRY.run(ir, only=[rid])
    return findings


def main():
    ir = load_ir()
    b = build_budget(ir, build_model(ir))
    print("ref-esp32 3V3 budget (ARCHITECTURE 2.2: ~463 -> 465 mA)")
    d = b.demand("3V3")
    check("3V3 peak within 2 pct of 465 mA", within(d["peak"], 465.0), "%.1f mA" % d["peak"])
    check("no unknown loads on 3V3", not d["unknown"], str(d["unknown"]))
    by = {x["term"]: x["peak"] for x in d["loads"]}
    check("module TX 355 mA", within(by["U1"], 355.0, 0.001))
    check("external allowance 100 mA", within(by["J2.1"], 100.0, 0.001))
    print("VBUS total (ARCHITECTURE 2.4: ~500 mA)")
    v = b.demand("VBUS_F")
    check("VBUS_F peak within 2 pct of 500 mA", within(v["peak"], 500.0), "%.1f mA" % v["peak"])
    print("LDO dissipation (ARCHITECTURE 2.3: 0.74 / 0.85 / 0.91 W)")
    for label, vbus, i_ma, want in (("peak, nominal USB", 5.00, 465.0, 0.74), ("peak, high USB", 5.25, 465.0, 0.85),
                                    ("500 mA cap, high USB", 5.25, 500.0, 0.91)):
        p = ldo_power_w(vbus - i_ma / 1000.0 * 0.25, 3.3, i_ma)
        check("%s -> %.3f W (doc %.2f)" % (label, p, want), within(p, want))
    fl = run(ir, "EL-THERMAL")
    tj = [f for f in fl if f.where.get("ref") == "U2"]
    check("EL-THERMAL U2: Tj 142 C > 125 C raised", len(tj) == 1 and tj[0].severity == "ERROR" and within(tj[0].measured["value"], 142.0, 0.01),
          tj[0].line()[:90] if tj else "no finding")
    check("finding states the copper-dependence of theta_JA", bool(tj) and "copper-dependent" in tj[0].why)
    print("EL-DROPOUT (LDL1117 passes, AMS1117 fails)")
    check("LDL1117 passes at the USB low corner", not run(ir, "EL-DROPOUT"))
    ams = copy.deepcopy(ir)
    p = F.rec_part("U2", "ams1117-3.3", "3V3 LDO", {1: "GND", 2: "3V3", 3: "VBUS_F"}, "Regulator_Linear:AMS1117-3.3")
    p["group"] = "power"
    ams["parts"]["U2"] = p
    fl = run(ams, "EL-DROPOUT")
    check("AMS1117-3.3 fails EL-DROPOUT", len(fl) == 1 and fl[0].severity == "ERROR", fl[0].line()[:110] if fl else "no finding")
    print("fail closed")
    nl = copy.deepcopy(ir)
    del nl["parts"]["U1"]["electrical"]["load_ma"]
    fl = run(nl, "EL-BUDGET")
    check("missing load_ma -> NOT_JUDGED naming the field",
          any(f.severity == "NOT_JUDGED" and "electrical.load_ma of U1" in f.why for f in fl), "; ".join(f.line()[:80] for f in fl[:2]))
    check("never a pass on missing data", not any(f.severity == "INFO" for f in fl))
    nd = copy.deepcopy(ir)
    del nd["parts"]["U2"]["electrical"]["regulator"]["dropout"]
    fl = run(nd, "EL-DROPOUT")
    check("missing dropout row -> NOT_JUDGED", len(fl) == 1 and fl[0].severity == "NOT_JUDGED" and "dropout" in fl[0].why,
          fl[0].line()[:100] if fl else "no finding")
    nt = copy.deepcopy(ir)
    del nt["parts"]["U2"]["electrical"]["theta_ja"]
    fl = [f for f in run(nt, "EL-THERMAL") if f.where.get("ref") == "U2"]
    check("missing theta_ja -> NOT_JUDGED naming electrical.theta_ja", len(fl) == 1 and fl[0].severity == "NOT_JUDGED" and "electrical.theta_ja" in fl[0].why)
    print("a lower bound above a limit is an ERROR, not NOT_JUDGED")
    ov = copy.deepcopy(ir)
    ov["external"]["pins"]["J2.1"]["i"] = 2.0
    del ov["parts"]["U3"]["electrical"]["load_ma"]
    fl = run(ov, "EL-BUDGET")
    check("overload with an unknown load still ERRORs", any(f.severity == "ERROR" for f in fl) and any(f.severity == "NOT_JUDGED" for f in fl))
    print("\n%s" % ("FAILED: " + ", ".join(FAILED) if FAILED else "all budget tests passed"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
