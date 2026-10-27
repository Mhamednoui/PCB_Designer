"""Uno Toggle - single source of truth for schematic AND PCB.

Two buttons, two LEDs, on an Arduino Uno R3 shield. Press a button -> its LED toggles.
Pin keys are symbol pin numbers (== footprint pad numbers). See ../DESIGN_BRIEF.md for the decisions.
Firmware pin map: ../firmware/uno_toggle.ino - keep the two in step (test/pinmap.py checks this).
"""
import os
import sys
import uuid

PRJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_NAME = "uno-toggle"
# Resolved once for the workspace (honours $KICAD_HOME, else the newest install) - never hardcode
# the KiCad path here again; upgrading KiCad used to mean editing 18 separate files.
# PRJ_DIR is projects/<id>, so up two more levels is the workspace root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PRJ_DIR)), "tools"))
from boardgen.kicad_paths import SHARE as KICAD_SHARE, SYMBOLS as KICAD_SYMBOLS, \
    FOOTPRINTS as KICAD_FOOTPRINTS  # noqa: E402
PROJECT_LIBS = ("arduino-library",)

# Schematic title block (read by make_sch.py - keeps that script board-agnostic)
SCH_TITLE = "Uno Toggle - 2 buttons, 2 LEDs"
SCH_SUBTITLE = "Arduino Uno R3 shield - press a button to toggle its LED"
SCH_DATE = "2026-09-17"
SCH_REV = "1.0"

_NS = uuid.UUID("9d2a7c61-4f0b-4a8e-9c31-2f7b6d5e8a44")


def uid(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


# ── Footprints (all through-hole - the user cannot solder SMD) ──
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_LED5 = "LED_THT:LED_D5.0mm"
FP_SW = "Button_Switch_THT:SW_PUSH_6mm"
FP_UNO = "arduino-library:Arduino_Uno_R3_Shield"

# ── LCSC part numbers (left blank = hand-solder / not ordered assembled) ──
LCSC = {
    "330R": "", "100nF": "", "LED_RED": "C2895470", "LED_GREEN": "",
}

PARTS = []


def part(ref, lib_id, value, footprint, pins, group, lcsc=""):
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      pins={str(k): v for k, v in pins.items() if v},
                      group=group, lcsc=lcsc))


def R(ref, value, a, b, group):
    part(ref, "Device:R", value, FP_R, {1: a, 2: b}, group, LCSC.get(value, ""))


def C(ref, value, a, b, group, fp=FP_C):
    part(ref, "Device:C", value, fp, {1: a, 2: b}, group, LCSC.get(value, ""))


def LED(ref, color, cathode, anode, group, fp=FP_LED5):
    part(ref, "Device:LED", color, fp, {1: cathode, 2: anode}, group, LCSC["LED_" + color])


# ── 1. Controller (the shield headers that plug into the Uno) ──
# Only the pins we actually use are connected; the rest stay unconnected on purpose.
G = "mcu"
# Note: the 5V pin is deliberately NOT connected. Nothing on this board uses the rail - the LEDs are
# driven straight from the digital pins and the buttons use the AVR's internal pull-ups. Wiring 5V
# anyway would create a single-pin net, which is an ERC error for no benefit.
part("A1", "arduino-library:Arduino_Uno_R3_Shield", "Arduino Uno R3", FP_UNO, {
    "D2": "BTN1", "D3": "BTN2",
    "D8": "LED1", "D9": "LED2",
    "GND1": "GND", "GND2": "GND", "GND3": "GND",
}, G)

# ── 2. Buttons: to GND, using the AVR's internal pull-ups (pressed = LOW) ──
# The 100nF across each switch is hardware debounce - the Reflex Machine taught us not to feed a
# raw mechanical switch straight into a pin (see docs/LESSONS_LEARNED.md).
G = "buttons"
part("SW1", "Switch:SW_Push", "BTN1", FP_SW, {1: "BTN1", 2: "GND"}, G)
part("SW2", "Switch:SW_Push", "BTN2", FP_SW, {1: "BTN2", 2: "GND"}, G)
C("C1", "100nF", "BTN1", "GND", G)
C("C2", "100nF", "BTN2", "GND", G)

# ── 3. LEDs: pin -> 330R -> LED anode, cathode to GND (~10mA at 5V) ──
G = "leds"
R("R1", "330R", "LED1", "LED1_A", G)
LED("D1", "RED", "GND", "LED1_A", G)
R("R2", "330R", "LED2", "LED2_A", G)
LED("D2", "GREEN", "GND", "LED2_A", G)

GROUPS = [
    ("mcu", "ARDUINO UNO R3 SHIELD HEADERS"),
    ("buttons", "BUTTONS: BTN1 (D2) / BTN2 (D3), INPUT_PULLUP TO GND + 100nF DEBOUNCE"),
    ("leds", "LEDS: LED1 (D8) / LED2 (D9) VIA 330R"),
]
POWER_FLAG_NETS = ["GND"]


# Electrical intent, read by tools/boardgen/lint_netlist.py (v in volts: number or (min, max); i_max in A).
# LED1/LED2 are the Uno's GPIO outputs: their level when driven HIGH (5 V), ~10 mA each through 330R.
NET_SPEC = {
    "GND": {"v": 0.0, "i_max": 0.05},
    "LED1": {"v": 5.0, "i_max": 0.02},
    "LED2": {"v": 5.0, "i_max": 0.02},
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
        print("  %-10s %s" % (name, sorted(ns[name])))
