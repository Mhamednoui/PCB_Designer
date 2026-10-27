"""Blinky 555 - single source of truth for schematic AND PCB.

A standalone 555 astable that blinks one LED at ~1 Hz off a 9-12 V supply.

This board exists as a PIPELINE TEST CASE (scenario A in docs/PCB_CREATION_GUIDE.md). It deliberately
differs from the two Arduino shields in the ways that matter to the generator:
  - no MCU and no shield footprint, so the board outline is a plain rectangle we choose ourselves
    rather than geometry copied out of a shield footprint's B.Fab layer
  - a real VCC rail (two power-flag nets, not just GND)
  - a multi-pin DIP IC, so pin numbers come from the symbol rather than being 1/2 by convention
  - only stock KiCad libraries: PROJECT_LIBS is empty

Pin keys are symbol pin numbers (== footprint pad numbers). Get them with
`python tools/sym_pins.py Timer:NE555P` - never off the datasheet, and never by grepping the symbol
by hand (NE555P is an alias that `extends` NE555D and declares no pins of its own).

Timing: f ~= 1.44 / ((R1 + 2*R2) * C1) = 1.44 / ((10k + 94k) * 10uF) ~= 1.4 Hz.
"""
import os
import sys
import uuid

PRJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_NAME = "blinky-555"
# Resolved once for the workspace (honours $KICAD_HOME, else the newest install) - never hardcode
# the KiCad path here again; upgrading KiCad used to mean editing 18 separate files.
# PRJ_DIR is projects/<id>, so up two more levels is the workspace root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PRJ_DIR)), "tools"))
from boardgen.kicad_paths import SHARE as KICAD_SHARE, SYMBOLS as KICAD_SYMBOLS, \
    FOOTPRINTS as KICAD_FOOTPRINTS  # noqa: E402
PROJECT_LIBS = ()          # stock libraries only - nothing to vendor into projects/blinky-555/lib

SCH_TITLE = "Blinky 555 - 1 Hz LED flasher"
SCH_SUBTITLE = "Standalone NE555 astable, 9-12 V in, through-hole"
SCH_DATE = "2026-09-17"
SCH_REV = "1.0"

_NS = uuid.UUID("4c8e1f92-7a03-4d61-b5c8-1e9f3a6d2b07")


def uid(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


# Footprints - all through-hole (the user cannot solder SMD)
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CP = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"        # polarised electrolytic
FP_LED5 = "LED_THT:LED_D5.0mm"
FP_DIP8 = "Package_DIP:DIP-8_W7.62mm"
FP_TERM2 = "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm"

LCSC = {"LED_RED": "C2895470"}

PARTS = []


def part(ref, lib_id, value, footprint, pins, group, lcsc=""):
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      pins={str(k): v for k, v in pins.items() if v},
                      group=group, lcsc=lcsc))


def R(ref, value, a, b, group):
    part(ref, "Device:R", value, FP_R, {1: a, 2: b}, group)


def C(ref, value, a, b, group, fp=FP_C):
    part(ref, "Device:C", value, fp, {1: a, 2: b}, group)


# ── 1. Power in ──
# Polarity is on the silkscreen (see make_pcb.py TEXTS) - a 2-pin terminal block gives no clue itself.
G = "power"
part("J1", "Connector:Conn_01x02_Pin", "9-12V IN", FP_TERM2, {1: "VCC", 2: "GND"}, G)
C("C3", "100nF", "VCC", "GND", G)          # decoupling, sits right at U1's pin 8

# ── 2. The 555 astable ──
# Pin numbers from `python tools/sym_pins.py Timer:NE555P`:
#   1 GND  2 TRIG  3 OUT  4 ~RST  5 CONT  6 THRES  7 DISCH  8 VCC
# RST is tied to VCC because a floating reset pin holds the timer in reset at random - the single
# most common reason a hand-wired 555 "does nothing".
G = "timer"
part("U1", "Timer:NE555P", "NE555P", FP_DIP8, {
    1: "GND", 2: "TRIG", 3: "OUT", 4: "VCC",
    5: "CONT", 6: "TRIG", 7: "DISCH", 8: "VCC",
}, G)
R("R1", "10k", "VCC", "DISCH", G)          # charge path
R("R2", "47k", "DISCH", "TRIG", G)         # charge + discharge path
C("C1", "10uF", "TRIG", "GND", G, fp=FP_CP)   # timing cap: pin 1 = +, pin 2 = -
C("C2", "10nF", "CONT", "GND", G)          # noise filter on the control pin

# ── 3. Output ──
G = "led"
R("R3", "470R", "OUT", "LED_A", G)
part("D1", "Device:LED", "RED", FP_LED5, {1: "GND", 2: "LED_A"}, G, LCSC["LED_RED"])

GROUPS = [
    ("power", "POWER IN: 9-12 V DC VIA J1"),
    ("timer", "NE555 ASTABLE: ~1.4 Hz, 50%% DUTY IS NOT EXPECTED (R1+R2 CHARGE, R2 DISCHARGES)"),
    ("led", "OUTPUT: LED VIA 470R (~15 mA AT 9 V)"),
]
POWER_FLAG_NETS = ["VCC", "GND"]

# Electrical intent, read by tools/boardgen/lint_netlist.py (v in volts: number or (min, max); i_max in A).
# OUT/TRIG are not rails: OUT swings 0..VCC (the LED is lit when it is high); TRIG ramps 1/3..2/3 VCC.
NET_SPEC = {
    "VCC": {"v": (9.0, 12.0), "i_max": 0.05},
    "GND": {"v": 0.0, "i_max": 0.05},
    "OUT": {"v": (9.0, 12.0), "i_max": 0.025},      # high level ~ VCC
    "TRIG": {"v": (3.0, 8.0)},                      # 1/3 VCC .. 2/3 VCC
}

# Transient SPICE run (tools/boardgen/make_spice.py) - this board's live simulation, since it has no
# MCU for Wokwi to run. The expectations are the design intent from the docstring above:
#   high = 0.693*(R1+R2)*C1 = 395 ms, low = 0.693*R2*C1 = 326 ms -> 1.39 Hz, 55% duty.
SPICE = {
    "supplies": {"VCC": 9.0},
    "tstop": 4.0,
    "probes": ["OUT", "TRIG", "VCC"],
    "expect": {"OUT": {"freq_hz": 1.39, "duty_pct": 55, "tol_pct": 10}},
}


def nets():
    out = {}
    for p in PARTS:
        for pin, n in p["pins"].items():
            out.setdefault(n, set()).add((p["ref"], pin))
    return out


if __name__ == "__main__":
    ns = nets()
    print("%d parts, %d nets" % (len(PARTS), len(ns)))
    for name in sorted(ns):
        pads = sorted(ns[name])
        flag = "  <-- SINGLE PIN (ERC error)" if len(pads) < 2 else ""
        print("  %-8s %s%s" % (name, pads, flag))
