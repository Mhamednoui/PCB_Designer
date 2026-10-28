"""Electrical-model tests (P2-T3): python tests/elec/test_model.py [--write-golden]   (system Python, stdlib, no KiCad).

Hand calculations are written next to each assertion. Covers: divider computable vs not computable (loaded midpoint, input
without declared leakage, third resistor, unknown far net, leakage too large), blinky-555 net by net, the EXTERNAL
variants of blinky (derived / conflict), an LDO + divider + LED synthetic board (regulator-output propagation from a
record, and the AMS1117 dropout case), FET both-states, pull defaults, driver/receiver classes, the engine hook
(`ctx.model`), and that reflex-machine builds with a stable per-status count (golden: tests/elec/reflex-machine.golden.json).
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tests", "rules", "demo"))
import fixtures as fx                                           # noqa: E402
from boardgen.elec import divider                               # noqa: E402
from boardgen.elec.model import build_model, parse_resistance  # noqa: E402
from boardgen.ir import from_netlist                            # noqa: E402
from boardgen.rules import engine                               # noqa: E402

FAILS = []
GOLDEN = os.path.join(HERE, "reflex-machine.golden.json")


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "  -> " + str(detail)))
    if not cond:
        FAILS.append(name)


def near(iv, lo, hi, tol=1e-6):
    return iv is not None and abs(iv[0] - lo) <= tol and abs(iv[1] - hi) <= tol


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


def blinky_ir(declared=False):
    """blinky-555's IR. The project now declares EXTERNAL (P2-T7); these tests are about the model, so by default the
    declaration is stripped (declared=False) to keep testing the 'EXTERNAL not declared' behaviour."""
    ir = {"ir_version": 2}
    ir.update(from_netlist.build("blinky-555"))
    if not declared:
        ir["external"] = {"declared": False, "pins": {}, "none": []}
        # The hand calculations below are for blinky WITHOUT the P2-T7b reverse-polarity diode D2: remove it, merge VIN into
        # VCC and restore the original NET_SPEC claims. (The real design with D2 is checked in test_blinky_diode.)
        ir["parts"].pop("D2", None)
        for p in ir["parts"].values():
            for q in p["pins"].values():
                if q["net"] == "VIN":
                    q["net"] = "VCC"
        ir["nets"].pop("VIN", None)
        ir["nets"]["VCC"]["v"] = [9.0, 12.0]
        ir["nets"]["OUT"]["v"] = [9.0, 12.0]
        ir["nets"]["TRIG"]["v"] = [3.0, 8.0]
    return ir


# ---------------------------------------------------------------------------------------------------------------------
def test_parse():
    print("resistor values")
    for s, want in (("470R", 470.0), ("10k", 1e4), ("4.7k", 4700.0), ("2k2", 2200.0), ("1M", 1e6), ("0R", 0.0), ("100", 100.0)):
        check("parse %s" % s, parse_resistance(s) == want, parse_resistance(s))
    check("parse 100nF -> None", parse_resistance("100nF") is None)


def test_divider_pure():
    print("divider.py (pure)")
    # Hand calc: Va = 12 V through Ra = 10k+-5 % to the midpoint, Vb = 0 V through Rb = 10k+-5 %.
    #   Vmid = Va*Rb/(Ra+Rb).  min = 12*9.5/(10.5+9.5) = 5.7 V ; max = 12*10.5/(9.5+10.5) = 6.3 V.
    ra = rb = divider.resistance(10e3, 0.05)
    iv = divider.midpoint((12, 12), (0, 0), ra, rb)
    check("12 V / 0 V, 10k+-5 %: 5.7 .. 6.3 V", near(iv, 5.7, 6.3), iv)
    # Va in 11..13 V: min = 11*9.5/20 = 5.225 ; max = 13*10.5/20 = 6.825
    iv = divider.midpoint((11, 13), (0, 0), ra, rb)
    check("Va 11..13 V: 5.225 .. 6.825 V", near(iv, 5.225, 6.825), iv)
    # Vb not zero: Va=5, Vb=1, equal exact resistors -> 3 V exactly
    iv = divider.midpoint((5, 5), (1, 1), (1000, 1000), (1000, 1000))
    check("5 V / 1 V, 1k/1k exact = 3 V", near(iv, 3.0, 3.0), iv)
    check("zero resistance refused", raises(ValueError, lambda: divider.midpoint((1, 1), (0, 0), (0, 1), (1, 1))))
    check("leakage unit nA -> A", abs(divider.leakage_a({"max": 1000, "unit": "nA"}) - 1e-6) < 1e-15)
    check("leakage without unit -> None", divider.leakage_a({"max": 5}) is None)
    # evaluate(): loads
    edges = [{"ref": "R1", "far": "A", "r": ra}, {"ref": "R2", "far": "B", "r": rb}]
    v = {"A": (12.0, 12.0), "B": (0.0, 0.0)}.get
    ok = divider.evaluate(edges, [{"term": "C1.1", "kind": "high_z"}], v)
    check("cap-only midpoint is computable", ok["computable"] and near(ok["interval"], 5.7, 6.3), ok)
    # divider current (min) = 12 V / (10.5k+10.5k) = 0.571 mA ; 1 % = 5.7 uA
    ok = divider.evaluate(edges, [{"term": "U1.2", "kind": "input", "leak_a": 1e-6}], v)
    check("input with 1 uA leakage (<= 5.7 uA) is computable", ok["computable"], ok)
    bad = divider.evaluate(edges, [{"term": "U1.2", "kind": "input", "leak_a": 100e-6}], v)
    check("input with 100 uA leakage is not computable", not bad["computable"] and "leakage" in bad["reason"], bad)
    bad = divider.evaluate(edges, [{"term": "U1.2", "kind": "input", "leak_a": None}], v)
    check("input without declared leakage is not computable", not bad["computable"] and "no declared input leakage" in bad["reason"], bad)
    bad = divider.evaluate(edges, [{"term": "U1.3", "kind": "other", "why": "pin class output"}], v)
    check("an output on the midpoint is not computable", not bad["computable"] and "U1.3" in bad["reason"], bad)
    bad = divider.evaluate(edges[:1], [], v)
    check("one resistor is not a divider", not bad["computable"] and "exactly 2" in bad["reason"], bad)
    bad = divider.evaluate(edges, [], {"A": (12.0, 12.0)}.get)
    check("unknown far net is not computable", not bad["computable"] and "no known voltage" in bad["reason"], bad)


def test_divider_model():
    print("divider through the model (synthetic boards)")
    m = build_model(fx.divider_fixture())
    n = m.nets["MID"]
    check("computable: MID derived 5.7..6.3 V", n.status == "derived" and near(n.interval, 5.7, 6.3), (n.status, n.interval, n.reason))
    check("computable: path names the divider formula", any("divider" in s for s in n.path), n.path)
    check("TOP is derived from EXTERNAL J1.1", m.nets["TOP"].status == "derived" and m.nets["TOP"].source == "external")

    # loaded midpoint: a third resistor to a LED on MID -> not computable
    m = build_model(fx.divider_fixture(extra=[fx.R("R3", "1k", "MID", "LED_A"), fx.LED("D1", "RED", "LED_A", "GND")]))
    n = m.nets["MID"]
    check("loaded midpoint (third resistor): NOT_JUDGED / divider", n.status == "NOT_JUDGED" and n.reason_kind == "divider"
          and "divider midpoint not computable" in n.reason, (n.status, n.reason_kind, n.reason))
    # loaded midpoint: an output pin on MID (74HC595 output QB = pad 1)
    out_pin = fx.rec_part("U1", "74hc595n-dip16", "74HC595N", {1: "MID", 16: "TOP", 8: "GND"}, "74xx:74HC595")
    m = build_model(fx.divider_fixture(extra=[out_pin]))
    n = m.nets["MID"]
    check("loaded midpoint (output pin): NOT_JUDGED naming the pin", n.status == "NOT_JUDGED" and "U1.1" in n.reason, (n.status, n.reason))
    # input pin with declared leakage: 74HC595 SER (pad 14) leaks <= 1 uA
    in_pin = fx.rec_part("U1", "74hc595n-dip16", "74HC595N", {14: "MID", 16: "TOP", 8: "GND"}, "74xx:74HC595")
    m = build_model(fx.divider_fixture(extra=[in_pin]))
    n = m.nets["MID"]
    check("midpoint with a CMOS input (1 uA leak): still computable", n.status == "derived" and near(n.interval, 5.7, 6.3), (n.status, n.reason))
    check("... and that input is listed as a receiver", [r["term"] for r in n.receivers] == ["U1.14"], n.receivers)
    # large resistors -> divider current 12/(2*1M) = 6 uA, 1 % = 60 nA < 1 uA leak -> not computable
    m = build_model(fx.divider_fixture(r1="1M", r2="1M", extra=[in_pin]))
    check("megaohm divider with a 1 uA input: not computable (leakage > 1 % of 5.7 uA)",
          m.nets["MID"].status == "NOT_JUDGED" and "leakage" in m.nets["MID"].reason, m.nets["MID"].reason)
    # far net unknown (no EXTERNAL) -> not computable
    ir = fx.divider_fixture()
    ir["external"] = {"declared": False, "pins": {}, "none": []}
    m = build_model(ir)
    check("far net unknown: MID NOT_JUDGED", m.nets["MID"].status == "NOT_JUDGED", (m.nets["MID"].status, m.nets["MID"].reason))
    # NET_SPEC claim on MID: contained -> derived ; not contained -> conflict
    m = build_model(fx.divider_fixture(claims={"MID": (5.0, 7.0)}))
    check("claim 5..7 contains 5.7..6.3: derived", m.nets["MID"].status == "derived", m.nets["MID"].status)
    m = build_model(fx.divider_fixture(claims={"MID": (6.0, 6.0)}))
    n = m.nets["MID"]
    check("claim 6.0 vs derived 5.7..6.3: conflict, interval stays the derived one",
          n.status == "conflict" and near(n.interval, 5.7, 6.3) and "claims 6 V" in n.reason, (n.status, n.interval, n.reason))


def test_blinky():
    print("blinky-555, net by net")
    ir = blinky_ir()
    m = build_model(ir)
    st = {k: n.status for k, n in m.nets.items()}
    # Hand calculation (R/C/LED values from netlist.py; records: ne555p, led-5mm, tb-maixu):
    #  GND    ground-class net                                     -> derived 0 V
    #  VCC    NET_SPEC (9,12); J1 is a connector and netlist.py declares no EXTERNAL -> nothing derives it
    #         -> claimed-only 9..12 V (INFO "assumed")
    #  OUT    NET_SPEC (9,12) = active level; driven by U1.3 (push-pull) but the record's VOH/VOL are measured at VCC = 5 V
    #         and the supply is 9..12 V -> datum unusable -> claimed-only 9..12 V
    #  TRIG   NET_SPEC (3,8); only R2 leads to DISCH (not derived) -> claimed-only 3..8 V
    #  DISCH  R1 (10k) to VCC and R2 (47k) to TRIG meet here BUT U1.7 (open-collector discharge transistor) also loads the node
    #         -> divider midpoint not computable -> NOT_JUDGED
    #  CONT   only C2 (open at DC) and U1.5 (analog) -> no DC source -> NOT_JUDGED
    #  LED_A  R3 (470R) from OUT (assumed 9..12 V) to D1 anode, D1 cathode on GND, Vf = 0..2.5 V (led-5mm RED: max 2.5 V,
    #         no minimum in the record -> 0). OUT.min 9 V - 0 V = 9 V > 2.5 V so the LED conducts: LED_A = GND + Vf = 0..2.5 V
    #         -> derived, assumes OUT
    want = {"GND": "derived", "VCC": "claimed-only", "OUT": "claimed-only", "TRIG": "claimed-only", "DISCH": "NOT_JUDGED",
            "CONT": "NOT_JUDGED", "LED_A": "derived"}
    check("statuses", st == want, st)
    check("GND = 0 V", near(m.nets["GND"].interval, 0, 0))
    check("VCC claimed-only 9..12 V, reason = EXTERNAL not declared", near(m.nets["VCC"].interval, 9, 12) and m.nets["VCC"].reason_kind == "external",
          (m.nets["VCC"].interval, m.nets["VCC"].reason_kind))
    check("OUT claimed-only 9..12 V because the VOH datum is at VCC=5 V", near(m.nets["OUT"].interval, 9, 12)
          and "VCC=5" in m.nets["OUT"].reason, m.nets["OUT"].reason)
    check("TRIG claimed-only 3..8 V", near(m.nets["TRIG"].interval, 3, 8))
    check("DISCH NOT_JUDGED: loaded by U1.7", m.nets["DISCH"].reason_kind == "divider" and "U1.7" in m.nets["DISCH"].reason, m.nets["DISCH"].reason)
    check("CONT NOT_JUDGED: no DC source", m.nets["CONT"].reason_kind == "no-dc-source", m.nets["CONT"].reason)
    n = m.nets["LED_A"]
    check("LED_A derived 0..2.5 V assuming OUT", near(n.interval, 0.0, 2.5) and n.assumes == ["OUT"], (n.interval, n.assumes))
    # driver / receiver classes (pin classes of the ne555p record)
    d = lambda net, k: sorted((t["term"], t["kind"]) for t in getattr(m.nets[net], k))     # noqa: E731
    check("OUT drivers = U1.3 push_pull", d("OUT", "drivers") == [("U1.3", "push_pull")], d("OUT", "drivers"))
    check("DISCH drivers = U1.7 sink_only", d("DISCH", "drivers") == [("U1.7", "sink_only")], d("DISCH", "drivers"))
    check("TRIG receivers = U1.2, U1.6 (cmos)", d("TRIG", "receivers") == [("U1.2", "cmos"), ("U1.6", "cmos")], d("TRIG", "receivers"))
    check("CONT receivers = U1.5 analog", d("CONT", "receivers") == [("U1.5", "analog")], d("CONT", "receivers"))
    check("VCC: U1.8 supply sink, U1.4 (RESET) receiver", d("VCC", "supply_sinks") == [("U1.8", "power_in")]
          and d("VCC", "receivers") == [("U1.4", "cmos")], (d("VCC", "supply_sinks"), d("VCC", "receivers")))

    # the project's own EXTERNAL (netlist.py, P2-T7): J1.1 supply 9..12 V -> VCC derived, no claim conflict
    mr = build_model(blinky_ir(declared=True))
    check("blinky's real EXTERNAL + D2: VIN derived 9..12 V, VCC behind D2 stays 8..12 V (model cannot derive through a loaded diode)",
          mr.nets["VIN"].status == "derived" and near(mr.nets["VIN"].interval, 9, 12) and mr.nets["VCC"].status in ("derived", "claimed-only")
          and mr.nets["VCC"].interval[1] <= 12.0 and mr.nets["VCC"].interval[0] >= 7.9, (mr.nets["VIN"].interval, mr.nets["VCC"].interval))
    # J1 declared in EXTERNAL with v = 9..12 V -> VCC becomes derived; the claim 9..12 contains it
    ir2 = copy.deepcopy(ir)
    ir2["external"] = {"declared": True, "none": [], "pins": {
        "J1.1": {"v": [9.0, 12.0], "i": 0.05, "dir": "supply", "why": "bench supply"},
        "J1.2": {"v": [0.0, 0.0], "i": None, "dir": "supply", "why": "return"}}}
    m2 = build_model(ir2)
    check("with EXTERNAL J1.1 = 9..12 V: VCC derived 9..12", m2.nets["VCC"].status == "derived" and near(m2.nets["VCC"].interval, 9, 12)
          and m2.nets["VCC"].source == "external", (m2.nets["VCC"].status, m2.nets["VCC"].source))
    check("... its path cites EXTERNAL J1.1", any("EXTERNAL J1.1" in s for s in m2.nets["VCC"].path), m2.nets["VCC"].path)
    check("... DISCH is still loaded by U1.7", m2.nets["DISCH"].status == "NOT_JUDGED")
    # EXTERNAL says 9..14 V but NET_SPEC claims 9..12 V -> conflict
    ir3 = copy.deepcopy(ir2)
    ir3["external"]["pins"]["J1.1"]["v"] = [9.0, 14.0]
    m3 = build_model(ir3)
    check("EXTERNAL 9..14 V vs claim 9..12 V: conflict", m3.nets["VCC"].status == "conflict" and near(m3.nets["VCC"].interval, 9, 14),
          (m3.nets["VCC"].status, m3.nets["VCC"].interval))
    # pull: RESET is tied to VCC directly (not a resistor) -> no pull entry anywhere on blinky except none
    check("no net of blinky has a pull default (no pull resistors to a rail on input-only nets)",
          all(n.pull is None or n.pull["state"] is None for n in m.nets.values() if n.name not in ("TRIG", "DISCH")), [n.name for n in m.nets.values() if n.pull])
    # explain output
    text = m.explain("LED_A")
    check("--net explain lists the derivation", "OUT = 9..12 V (assumed" in text and "diode conducts" in text, text)
    check("--net on an unknown net says so", "no net" in m.explain("NOPE"))
    check("to_dict is JSON-serialisable and deterministic", json.dumps(m.to_dict(), sort_keys=True) == json.dumps(build_model(ir).to_dict(), sort_keys=True))


def test_ldo_chain():
    print("synthetic LDO + divider + LED (regulator output from a record)")
    # Hand calc, LDL1117S33R record: Vout 3.201 .. 3.399 V (3.3 V -3 %/+3 %), dropout max 0.6 V @ 1.2 A, Vin 2.6 .. 18 V.
    #  VBUS  EXTERNAL J1.1 = 4.4 .. 5.25 V
    #  3V3   Vin min 4.4 >= Vout max 3.399 + dropout 0.6 = 3.999 -> regulating: 3.201 .. 3.399 V (claim 3.0..3.6 contains it)
    #  MID   10k/10k (+-5 %) from 3V3 to GND: min = 3.201*9.5/20 = 1.520475 V ; max = 3.399*10.5/20 = 1.784475 V
    #  LED_A 330R from 3V3 into a RED LED to GND (Vf max 2.5 V): 3V3 min 3.201 - 0 > 2.5 -> LED conducts: 0 .. 2.5 V
    m = build_model(fx.ldo_divider_led())
    check("VBUS derived 4.4..5.25 from EXTERNAL", m.nets["VBUS"].status == "derived" and near(m.nets["VBUS"].interval, 4.4, 5.25))
    n = m.nets["3V3"]
    check("3V3 derived 3.201..3.399 from the LDL1117 record", n.status == "derived" and near(n.interval, 3.201, 3.399) and n.source == "regulator",
          (n.status, n.interval, n.source))
    check("... path shows the headroom check", any("headroom ok" in s for s in n.path), n.path)
    check("... no assumptions (everything from EXTERNAL + record)", n.assumes == [], n.assumes)
    check("3V3 supply source U1.2 / VBUS supply sink U1.3", [t["term"] for t in n.supply_sources] == ["U1.2"]
          and [t["term"] for t in m.nets["VBUS"].supply_sinks] == ["U1.3"])
    n = m.nets["MID"]
    check("MID derived 1.520475..1.784475 V", n.status == "derived" and near(n.interval, 3.201 * 9.5 / 20, 3.399 * 10.5 / 20), (n.status, n.interval, n.reason))
    n = m.nets["LED_A"]
    check("LED_A derived 0..2.5 V, no assumptions", n.status == "derived" and near(n.interval, 0.0, 2.5) and n.assumes == [], (n.status, n.interval, n.assumes))
    # claim 3.3 +-0 vs derived 3.201..3.399 -> conflict (spec example: "declared 3.3 but derived ...")
    m = build_model(fx.ldo_divider_led(claim_3v3=(3.3, 3.3)))
    check("claim 3.3 V vs derived 3.201..3.399: conflict", m.nets["3V3"].status == "conflict", m.nets["3V3"].status)
    # AMS1117: dropout max 1.3 V -> 4.4 < 3.399 + 1.3 = 4.699 -> dropout-limited: lower bound = min(3.201, 4.4 - 1.3 = 3.1) = 3.1 V
    m = build_model(fx.ldo_divider_led(ldo="ams1117-3.3"))
    n = m.nets["3V3"]
    check("AMS1117 at Vin min 4.4 V: dropout-limited, 3.1 .. 3.399 V", near(n.interval, 3.1, 3.399) and any("DROPOUT" in s for s in n.path),
          (n.interval, n.path))
    # regulator input unknown (no EXTERNAL) -> 3V3 not derived: claimed-only, reason says why
    ir = fx.ldo_divider_led()
    ir["external"] = {"declared": False, "pins": {}, "none": []}
    m = build_model(ir)
    n = m.nets["3V3"]
    check("regulator input unknown (VBUS has no EXTERNAL, no claim) -> 3V3 claimed-only 3.0..3.6, reason kind regulator",
          n.status == "claimed-only" and near(n.interval, 3.0, 3.6) and n.reason_kind == "regulator" and m.nets["VBUS"].status == "NOT_JUDGED",
          (n.status, n.interval, n.reason_kind, m.nets["VBUS"].status))


def test_fet():
    print("MOSFET states")
    # IRLZ44N record: Vth 1..2 V. Source on GND (0 V).
    #  gate 5 V : Vgs min 5 >= Vth max 2 -> ON: drain joined to source -> DRAIN = 0 V (derived, claim 0 agrees)
    m = build_model(fx.fet_fixture((5.0, 5.0)))
    n = m.nets["DRAIN"]
    check("gate 5 V: Q1 ON, DRAIN derived 0 V", m.elements["fet_states"] == {"Q1": "on"} and n.status == "derived" and near(n.interval, 0, 0),
          (m.elements["fet_states"], n.status, n.interval))
    #  gate 0..0.2 V : Vgs max 0.2 <= Vth min 1 -> OFF: channel open, DRAIN undriven -> only the claim remains
    m = build_model(fx.fet_fixture((0.0, 0.2)))
    n = m.nets["DRAIN"]
    check("gate 0..0.2 V: Q1 OFF, DRAIN not derived (claimed-only)", m.elements["fet_states"] == {"Q1": "off"} and n.status == "claimed-only"
          and not n.state_dependent, (m.elements["fet_states"], n.status))
    #  gate 0..5 V : straddles Vth -> both states, drain is state-dependent
    m = build_model(fx.fet_fixture((0.0, 5.0)))
    n = m.nets["DRAIN"]
    check("gate 0..5 V: both states, DRAIN state-dependent and not derived", n.state_dependent and n.status == "claimed-only"
          and n.reason_kind == "state-dependent", (n.state_dependent, n.status, n.reason_kind))


def test_pull():
    print("pull defaults")
    m = build_model(fx.pull_fixture())
    up, dn = m.nets["SIG_UP"], m.nets["SIG_DN"]
    check("10k to 3V3 on a CMOS input: default HIGH", up.pull and up.pull["state"] == "high" and up.pull["resistors"][0]["ref"] == "R1", up.pull)
    check("10k to GND on a CMOS input: default LOW", dn.pull and dn.pull["state"] == "low", dn.pull)
    # Hand calc: the 74HC595 input leaks <= 1 uA either way; through 10k+5 % = 10.5k that is +-10.5 mV.
    #   SIG_UP = 3V3 (3.135..3.465, EXTERNAL) +- 0.0105 = 3.1245 .. 3.4755 V ; SIG_DN = 0 +- 0.0105 V
    check("pull nets are derived through the series resistor, widened by the declared input leakage",
          up.status == "derived" and near(up.interval, 3.1245, 3.4755) and dn.status == "derived" and near(dn.interval, -0.0105, 0.0105),
          (up.status, up.interval, dn.status, dn.interval))


def test_engine_hook():
    print("rule engine hook (ctx.model)")
    demo_dir = os.path.join(ROOT, "tests", "rules", "demo")
    reg = engine.Registry(root=demo_dir, mutation_ids={"M-demo-negative"})
    seen = {}

    @reg.rule(id="ZZ-MODEL", severity="ERROR", needs=("electrical",), doc="DEMO-NEGATIVE.md", fixture="fixtures/DEMO-NEGATIVE",
              mutation="M-demo-negative")
    def uses_model(ctx):
        ctx.examined()
        seen["status"] = ctx.model.nets["MID"].status
        seen["dict"] = ctx.ir["electrical"]["nets"]["MID"]["status"]
        seen["same"] = ctx.model is ctx.model
        return []

    @reg.rule(id="ZZ-NOMODEL", severity="ERROR", needs=("nets",), doc="DEMO-NEGATIVE.md", fixture="fixtures/DEMO-NEGATIVE",
              mutation="M-demo-negative")
    def no_model(ctx):
        return [ctx.model]

    ir = fx.divider_fixture()
    reg.run(ir, only=["ZZ-MODEL"])
    check("a rule with needs=('electrical',) gets ctx.model and ctx.ir['electrical']", seen == {"status": "derived", "dict": "derived", "same": True}, seen)
    check("a rule without 'electrical' in needs cannot use ctx.model", raises(KeyError, lambda: reg.run(ir, only=["ZZ-NOMODEL"])))
    import boardgen.elec.model as em
    calls, real = [], em.build_model
    em.build_model = lambda i: (calls.append(1), real(i))[1]
    try:
        reg.rule(id="ZZ-MODEL2", severity="ERROR", needs=("electrical",), doc="DEMO-NEGATIVE.md", fixture="fixtures/DEMO-NEGATIVE",
                 mutation="M-demo-negative")(lambda ctx: [ctx.model] and [])
        reg.run(ir, only=["ZZ-MODEL", "ZZ-MODEL2"])
    finally:
        em.build_model = real
    check("the model is built once per run and shared by the rules", len(calls) == 1, calls)


def test_reflex():
    print("reflex-machine builds")
    ir = {"ir_version": 2}
    ir.update(from_netlist.build("reflex-machine"))
    m = build_model(ir)
    c = m.counts()
    reasons = {st: {k: len(v) for k, v in m.reason_counts(st).items()} for st in ("NOT_JUDGED", "claimed-only")}
    cur = {"nets": len(m.nets), "counts": c, "reasons": reasons}
    check("every net has a status and the counts add up", sum(c.values()) == len(m.nets) == len(ir["nets"]), (c, len(m.nets)))
    check("every non-derived net says why", all(n.reason for n in m.nets.values() if n.status != "derived"),
          [n.name for n in m.nets.values() if n.status != "derived" and not n.reason])
    check("+5V comes from the K7805 module record and conflicts with the point claim 5 V",
          m.nets["+5V"].status == "conflict" and near(m.nets["+5V"].interval, 4.85, 5.15), (m.nets["+5V"].status, m.nets["+5V"].interval))
    check("the 12 V chain is explained (fuse, series diode)", any("fuse" in s for s in m.nets["+12V_REG"].path) and any("DIODE D2" in s for s in m.nets["+12V_REG"].path))
    both = sorted(n.name for n in m.nets.values() if n.state_dependent and n.name.endswith("_OUT"))
    check("the 10 MOSFET drains (MAGn_OUT) are state-dependent: gates are driven by the MCU, not fixed",
          m.elements["fet_states"] == {} and len(both) == 10, (m.elements["fet_states"], both))
    print("  counts: %s  nets=%d" % (c, len(m.nets)))
    if "--write-golden" in sys.argv:
        with open(GOLDEN, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cur, f, indent=1, sort_keys=True)
            f.write("\n")
        print("  wrote " + GOLDEN)
        return
    with open(GOLDEN, encoding="utf-8") as f:
        gold = json.load(f)
    check("per-status counts equal the golden (regenerate with --write-golden after a deliberate data change)", cur == gold, "\n   have %s\n   want %s" % (cur, gold))


def main():
    for t in (test_parse, test_divider_pure, test_divider_model, test_blinky, test_ldo_chain, test_fet, test_pull, test_engine_hook, test_reflex):
        t()
    print("\n%s" % ("%d FAILED: %s" % (len(FAILS), FAILS) if FAILS else "all electrical-model tests passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
