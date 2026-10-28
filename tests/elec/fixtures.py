"""Synthetic IR fixtures for the electrical-model tests (P2-T3). Stdlib only, no KiCad.

`design(parts, claims=None, external=None)` builds a minimal IR v2 dict {meta, parts, nets, external}; the part
helpers take their pin classes / io / electrical blocks from the REAL registry records (parts/records/*.json) through the
same resolver the `ir` stage uses (boardgen.ir.elec), so a fixture cannot drift from the shipped data.

    R(ref, value, a, b)                       generic resistor (Device:R)
    C(ref, value, a, b)                       generic capacitor (Device:C)
    LED(ref, value, anode, cathode)           led-5mm record (Vf only for value RED)
    rec_part(ref, record_id, value, pins, lib_id, kind)   any registry record; pins = {pad: net}
    conn(ref, {pad: net})                     connector (passive pins, kind connector)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from boardgen.ir import elec as _elec                          # noqa: E402


def record(rec_id):
    with open(os.path.join(ROOT, "parts", "records", rec_id + ".json"), encoding="utf-8") as f:
        return json.load(f)


def rec_part(ref, rec_id, value, pins, lib_id, kind="part"):
    """An IR part built from a registry record. pins {pad: net}."""
    rec = record(rec_id)
    status, block = _elec.part_electrical(rec, value)
    out = {}
    for pad, net in pins.items():
        pad = str(pad)
        cls, abs_max, io = _elec.resolve_pin(rec, pad, status)
        out[pad] = {"name": rec["pins"][pad].get("name"), "net": net, "class": cls, "abs_max": abs_max, "io": io}
    return {"ref": ref, "registry": rec_id, "kind": kind, "lib_id": lib_id, "footprint": "", "value": value, "lcsc": "",
            "group": None, "pins": out, "nc": [], "electrical": block, "electrical_status": status}


def _plain(ref, lib_id, value, pins, kind="generic", names=("~", "~")):
    return {"ref": ref, "registry": None, "kind": kind, "lib_id": lib_id, "footprint": "", "value": value, "lcsc": "",
            "group": None, "nc": [], "electrical": None, "electrical_status": "none",
            "pins": {str(p): {"name": names[i], "net": n, "class": "passive", "abs_max": None, "io": None}
                     for i, (p, n) in enumerate(pins)}}


def R(ref, value, a, b):
    return _plain(ref, "Device:R", value, [(1, a), (2, b)])


def C(ref, value, a, b):
    return _plain(ref, "Device:C", value, [(1, a), (2, b)])


def LED(ref, value, anode, cathode):
    return rec_part(ref, "led-5mm", value, {1: cathode, 2: anode}, "Device:LED", kind="generic")


def conn(ref, pins):
    return _plain(ref, "Connector:Conn", ref, [(p, n) for p, n in sorted(pins.items())], kind="connector",
                  names=tuple("Pin_%s" % p for p in sorted(pins)))


def design(parts, claims=None, external=None, project="fixture"):
    """Minimal IR v2. claims {net: (lo, hi)} = NET_SPEC; external {"J1.1": (lo, hi) | None, ...} = EXTERNAL v (dir supply)."""
    claims = claims or {}
    nets = {}
    for p in parts:
        for pad, pin in p["pins"].items():
            n = pin["net"]
            e = nets.setdefault(n, {"v": None, "i_max": None, "class": "signal", "pins": []})
            e["pins"].append("%s.%s" % (p["ref"], pad))
            if n == "GND":
                e["class"], e["v"] = "ground", [0.0, 0.0]
            elif pin["class"] in ("power_in", "power_out") and e["class"] != "ground":
                e["class"] = "power"
    for n, v in claims.items():
        nets[n]["v"] = [float(v[0]), float(v[1])]
    ext = {"declared": False, "pins": {}, "none": []}
    if external is not None:
        ext = {"declared": True, "none": [],
               "pins": {k: {"v": None if v is None else [float(v[0]), float(v[1])], "i": None, "dir": "supply", "why": "fixture"}
                        for k, v in external.items()}}
    return {"ir_version": 2, "meta": {"project": project, "source": "netlist", "git_commit": None, "input_hashes": {}},
            "parts": {p["ref"]: p for p in parts}, "nets": nets, "external": ext, "assembly": {"mode": None, "boards": None},
            "fab_profile": {"name": "x", "declared": False}, "requirements": []}


# ---------------------------------------------------------------------------------------------------- named fixtures
def divider_fixture(top_v=(12.0, 12.0), r1="10k", r2="10k", extra=None, claims=None):
    """J1 supplies TOP (EXTERNAL), R1 TOP-MID, R2 MID-GND, a 100 nF capacitor on MID. `extra`: more parts on MID."""
    parts = [conn("J1", {1: "TOP", 2: "GND"}), R("R1", r1, "TOP", "MID"), R("R2", r2, "MID", "GND"), C("C1", "100nF", "MID", "GND")]
    parts += extra or []
    return design(parts, claims=claims, external={"J1.1": top_v, "J1.2": (0.0, 0.0)})


def ldo_divider_led(ldo="ldl1117s33r-sot2234", claim_3v3=(3.0, 3.6), vbus=(4.4, 5.25)):
    """USB-ish 4.4..5.25 V -> 3.3 V LDO (record) -> 10k/10k divider -> and a 330R + red LED to ground.
    Hand calc: see tests/elec/test_model.py (test_ldo_chain)."""
    ldo_lib = {"ldl1117s33r-sot2234": "Regulator_Linear:LDL1117S33R", "ams1117-3.3": "Regulator_Linear:AMS1117-3.3"}[ldo]
    parts = [conn("J1", {1: "VBUS", 2: "GND"}),
             rec_part("U1", ldo, "3V3 LDO", {1: "GND", 2: "3V3", 3: "VBUS"}, ldo_lib),
             R("R1", "10k", "3V3", "MID"), R("R2", "10k", "MID", "GND"), C("C1", "100nF", "MID", "GND"),
             R("R3", "330R", "3V3", "LED_A"), LED("D1", "RED", "LED_A", "GND")]
    return design(parts, claims={"3V3": claim_3v3}, external={"J1.1": vbus, "J1.2": (0.0, 0.0)})


def fet_fixture(gate_v):
    """N-MOSFET (irlz44npbf record) source on GND, gate driven by connector J1.1 with EXTERNAL v = gate_v, drain on J2.1."""
    parts = [conn("J1", {1: "GATE", 2: "GND"}), conn("J2", {1: "DRAIN", 2: "GND"}),
             rec_part("Q1", "irlz44npbf-to220ab", "IRLZ44N", {1: "GATE", 2: "DRAIN", 3: "GND"}, "Transistor_FET:IRLZ44N")]
    return design(parts, claims={"DRAIN": (0.0, 0.0)}, external={"J1.1": gate_v, "J1.2": (0.0, 0.0)})


def pull_fixture():
    """Input net SIG_UP pulled up to 3V3 by 10k, input net SIG_DN pulled down by 10k, both only on 74HC595 inputs."""
    parts = [conn("J1", {1: "3V3", 2: "GND"}),
             rec_part("U1", "74hc595n-dip16", "74HC595N", {14: "SIG_UP", 11: "SIG_DN", 16: "3V3", 8: "GND"}, "74xx:74HC595"),
             R("R1", "10k", "3V3", "SIG_UP"), R("R2", "10k", "SIG_DN", "GND")]
    return design(parts, external={"J1.1": (3.135, 3.465), "J1.2": (0.0, 0.0)})
