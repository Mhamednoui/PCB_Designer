"""Requirements-engine tests (P2-T9): python tests/req/test_eval.py   (system Python, stdlib; builds the blinky-555 IR from netlist.py).

Each case states the requirement and the verdict it must give, including the fail-closed ones (unknown ref = ERROR,
unevaluable = NOT_EVALUATED, never PASS)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from boardgen.ir import from_netlist          # noqa: E402
from boardgen.req import eval as ev           # noqa: E402

FAILS = []


def run(reqs):
    ir = from_netlist.build("blinky-555")
    ir["requirements"] = reqs
    return [r["result"] for r in ev.evaluate(ir)]


def check(name, reqs, want):
    got = run(reqs)
    ok = got == want
    print("  %s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else "  -> got %s want %s" % (got, want)))
    if not ok:
        FAILS.append(name)


def r(kind, **kw):
    d = {"id": "X", "kind": kind, "text": "t"}
    d.update(kw)
    return [d]


check("path through D2 holds", r("path", **{"from": "J1.1", "to": "U1.VCC", "through": {"ref": "D2"}}), ["PASS"])
check("path through the wrong part fails", r("path", **{"from": "J1.1", "to": "U1.VCC", "through": {"ref": "R3"}}), ["FAIL"])
check("path through a class", r("path", **{"from": "J1.1", "to": "U1.VCC", "through": {"class": "diode"}}), ["PASS"])
check("reverse direction of a diode has no path", r("path", **{"from": "U1.VCC", "to": "J1.1"}), ["FAIL"])
check("path_absent violated", r("path_absent", **{"from": "J1.1", "to": "U1.VCC"}), ["FAIL"])
check("unknown ref is ERROR", r("path", **{"from": "J9.1", "to": "U1.VCC"}), ["ERROR"])
check("unknown pin is ERROR", r("path", **{"from": "J1.77", "to": "U1.VCC"}), ["ERROR"])
check("unknown net is ERROR", r("net_v", net="NOPE", min=0), ["ERROR"])
check("unknown kind is ERROR", r("magic"), ["ERROR"])
check("missing key is ERROR", r("path", **{"from": "J1.1"}), ["ERROR"])
check("net_v inside", r("net_v", net="VIN", min=9, max=12), ["PASS"])
check("net_v outside", r("net_v", net="VIN", min=10, max=12), ["FAIL"])
check("net_v on a claimed-only net is not evaluated", r("net_v", net="VCC", min=0, max=20), ["NOT_EVALUATED"])
check("static_logic LED on", r("static_logic", when={"U1.OUT": [6.5, 10.5]}, expect={"D1": "on"}), ["PASS"])
check("static_logic LED not guaranteed on", r("static_logic", when={"U1.OUT": [2.0, 2.4]}, expect={"D1": "on"}), ["FAIL"])
check("static_logic without level data", r("static_logic", when={"U1.OUT": "high"}, expect={"D1": "on"}), ["NOT_EVALUATED"])
check("rail_peak with no load data on the net", r("rail_peak", net="OUT", max_mA=500), ["NOT_EVALUATED"])
check("rail_peak within budget", r("rail_peak", net="VCC", max_mA=500), ["PASS"])
check("rail_peak over budget", r("rail_peak", net="VCC", max_mA=0.001), ["FAIL"])
check("spice is a stub", r("spice", scenario="x"), ["NOT_EVALUATED"])
check("duplicate id", r("net_v", net="VIN", min=0) + r("net_v", net="VIN", min=0), ["PASS", "ERROR"])  # the second one is flagged
print("test_eval: %s" % ("FAIL %d" % len(FAILS) if FAILS else "all passed"))
sys.exit(1 if FAILS else 0)
