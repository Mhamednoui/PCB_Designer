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
from boardgen import netlist_ext as X  # noqa: E402
from boardgen import parts as _parts  # noqa: E402
PROJECT_LIBS = ("arduino-library",)

# Schematic title block (read by make_sch.py - keeps that script board-agnostic)
SCH_TITLE = "Uno Toggle - 2 buttons, 2 LEDs"
SCH_SUBTITLE = "Arduino Uno R3 shield - press a button to toggle its LED"
SCH_DATE = "2026-09-17"
SCH_REV = "1.0"

_NS = uuid.UUID("9d2a7c61-4f0b-4a8e-9c31-2f7b6d5e8a44")


def uid(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


PARTS_STRICT = True        # every part must be declared through the registry (lint rule PR-REF)

# Symbol, footprint and LCSC id of each part come from its registry record, parts/records/<id>.json
# (all through-hole - the user cannot solder SMD). Generic 2-pin passives, the switches and the shield
# have unnamed or board-position pins: pad numbers. Diodes/LEDs are polarised: pins by function (K / A).
R_ID, C_ID, LED_ID = "res-axial-0207-p10.16", "cap-disc-5mm-p5.00", "led-5mm"
SW_ID, UNO_ID = "sw-push-6mm-tht", "arduino-uno-r3-shield"

PARTS = []


def R(ref, value, a, b, group):
    PARTS.append(_parts.registry_part(ref, R_ID, value, {1: a, 2: b}, group))


def C(ref, value, a, b, group):
    PARTS.append(_parts.registry_part(ref, C_ID, value, {1: a, 2: b}, group))


def LED(ref, color, cathode, anode, group, lcsc=None):
    PARTS.append(_parts.registry_part(ref, LED_ID, color, {"K": cathode, "A": anode}, group, lcsc=lcsc))


# ── 1. Controller (the shield headers that plug into the Uno) ──
# Only the pins we actually use are connected; every other shield pin is unconnected on purpose
# (nc="rest" is allowed for connector records only).
G = "mcu"
# Note: the 5V pin is deliberately NOT connected. Nothing on this board uses the rail - the LEDs are
# driven straight from the digital pins and the buttons use the AVR's internal pull-ups. Wiring 5V
# anyway would create a single-pin net, which is an ERC error for no benefit.
PARTS.append(_parts.registry_part("A1", UNO_ID, "Arduino Uno R3", {
    "D2": "BTN1", "D3": "BTN2",
    "D8": "LED1", "D9": "LED2",
    "GND1": "GND", "GND2": "GND", "GND3": "GND",
}, G, nc="rest"))

# ── 2. Buttons: to GND, using the AVR's internal pull-ups (pressed = LOW) ──
# The 100nF across each switch is hardware debounce - the Reflex Machine taught us not to feed a
# raw mechanical switch straight into a pin (see docs/LESSONS_LEARNED.md).
G = "buttons"
PARTS.append(_parts.registry_part("SW1", SW_ID, "BTN1", {1: "BTN1", 2: "GND"}, G))
PARTS.append(_parts.registry_part("SW2", SW_ID, "BTN2", {1: "BTN2", 2: "GND"}, G))
C("C1", "100nF", "BTN1", "GND", G)
C("C2", "100nF", "BTN2", "GND", G)

# ── 3. LEDs: pin -> 330R -> LED anode, cathode to GND (~10mA at 5V) ──
G = "leds"
R("R1", "330R", "LED1", "LED1_A", G)
LED("D1", "RED", "GND", "LED1_A", G, lcsc="C2895470")
R("R2", "330R", "LED2", "LED2_A", G)
LED("D2", "GREEN", "GND", "LED2_A", G)

# Through-hole board, hand-soldered (ADR 0012): the release gate judges it as `hand`.
ASSEMBLY = "hand"

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


# What is on the other side of each connector (P2 electrical analyzer, EL-CONN-PROT). The only connector is the Uno itself
# (A1, a shield socket): its pins are the outside world. 5 V logic (USB-powered Uno: 4.4-5.25 V). GND pins are ground-class.
EXTERNAL = X.merge(
    X.pins("A1", ["D2", "D3"], dir="out", v=(0.0, 5.25),
           why="Uno inputs with INPUT_PULLUP (firmware/uno_toggle.ino); this board pulls them to GND through a button"),
    # no `v` here on purpose: NET_SPEC's 5 V is the ACTIVE level (lint needs it for the LED current), the pin's honest range
    # is 0..5.25 V and declaring it would make the model report a NET_SPEC conflict.
    X.pins("A1", ["D8", "D9"], dir="in",
           why="Uno digital outputs, 5 V logic, drive the LED resistors (max 40 mA per pin, 10 mA used)"),
    # The tactile switches are series elements between an Uno pin and GND, not a cable: the only thing that leaves
    # the board is the Uno itself (A1). Their finger-ESD exposure is judged on the A1 pin nets.
    X.none("SW1", "SW2"),
)


FIRMWARE = {
    # Read by tools/boardgen/check_pinmap.py (schema documented there).
    "files": ["firmware/uno_toggle.ino"],
    "mcu_ref": "A1",
    "analog_base": 14,
    "signals": {"BTN1": "BTN1", "BTN2": "BTN2", "LED1": "LED1", "LED2": "LED2"},
}


# Executable requirements (judged by the `requirements` stage -> out/REQUIREMENTS.md); design intent from DESIGN_BRIEF.md.
REQUIREMENTS = [
    {"id": "R1", "kind": "path", "from": "SW1.1", "to": "A1.D2",
     "text": "Button 1 reaches Uno pin D2"},
    {"id": "R2", "kind": "path", "from": "SW2.1", "to": "A1.D3",
     "text": "Button 2 reaches Uno pin D3"},
    {"id": "R3", "kind": "path", "from": "A1.D8", "to": "D1.A", "through": {"ref": "R1"},
     "text": "LED1 is driven from D8 through its 330R resistor R1"},
    {"id": "R4", "kind": "path", "from": "A1.D9", "to": "D2.A", "through": {"ref": "R2"},
     "text": "LED2 is driven from D9 through its 330R resistor R2"},
    {"id": "R5", "kind": "path", "from": "SW1.2", "to": "A1.GND1",
     "text": "A pressed button pulls its pin to the Uno ground (internal pull-up, pressed = LOW)"},
    {"id": "R6", "kind": "path_absent", "from": "A1.D8", "to": "A1.D9",
     "text": "The two LED outputs are not wired together"},
]

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
