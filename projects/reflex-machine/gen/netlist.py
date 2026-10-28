"""Reflex Machine controller shield - single source of truth for schematic AND PCB.

Pin keys are symbol pin numbers (== footprint pad numbers).
Firmware pin map: CODES/arduino_main_code.cpp, CODES/ESP32_main_code.cpp (unchanged).
"""
import os
import sys
import uuid

PRJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_NAME = "reflex-machine"
# Resolved once for the workspace (honours $KICAD_HOME, else the newest install) - never hardcode
# the KiCad path here again; upgrading KiCad used to mean editing 18 separate files.
# PRJ_DIR is projects/<id>, so up two more levels is the workspace root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PRJ_DIR)), "tools"))
from boardgen.kicad_paths import SHARE as KICAD_SHARE, SYMBOLS as KICAD_SYMBOLS, \
    FOOTPRINTS as KICAD_FOOTPRINTS  # noqa: E402
from boardgen import netlist_ext as X  # noqa: E402
from boardgen import parts as _parts  # noqa: E402
PROJECT_LIBS = ("arduino-library", "reflex")

_NS = uuid.UUID("6f1b5f5e-3c1a-4a55-9a53-8a1f2c7d0b11")


def uid(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


PARTS_STRICT = True        # every part must be declared through the registry (lint rule PR-REF)

# ── Registry ids ────────────────────────────────────────────
# Symbol, footprint and LCSC id of each part come from its record, parts/records/<id>.json. ICs, the
# transistors, the module, the polarised parts and the ESP32 socket connect their pins BY FUNCTION (the
# record's pin name): the pad numbers are derived from the record. Generic 2-pin passives, screw terminals
# and pin headers have unnamed pins ("~", "Pin_1"): pad numbers. The Mega shield footprint keeps its own
# pad names ("D2", "5V1", "GND1" ...), which already are its function.
R_ID, C_ID, CE_ID, CP10_ID = "res-axial-0207-p10.16", "cap-disc-5mm-p5.00", "cap-elec-d6.3-p2.50", "cap-elec-d10-p5.00"
LED3_ID, LED5_ID = "led-3mm", "led-5mm"
DO41_ID, DO201V_ID, DO15_ID = "diode-do41-p7.62-h", "diode-do201ad-p5.08-v", "tvs-do15-p10.16-h"
Q_ID, MODULE_ID, OPTO_ID, SR_ID = "irlz44npbf-to220ab", "k7805-2000r3-module", "pc817c-dip4", "74hc595n-dip16"
FUSE_ID, J_PWR_ID, J_MAG_ID = "fuseholder-blade-mini-keystone-3568", "tb-phoenix-mkds-3-2-5.08", "tb-phoenix-mkds-1.5-2-5.08"
J3_ID, J8_ID = "tb-phoenix-pt-1.5-3-3.5-h", "tb-phoenix-pt-1.5-8-3.5-h"
HDR2x10_ID, HDR2x4_ID = "hdr-2x10-p2.54-v", "hdr-2x04-p2.54-v"
MEGA_ID, ESP32_ID = "arduino-mega2560-r3-shield", "esp32-devkit-v1-30pin-socket"

PARTS = []


# Per-instance LCSC ids of the generic parts, keyed by value (the ids the BOM carried before the registry).
# A generic record has no id of its own: a 10k and a 1M resistor are the same record.
LCSC_BY_VALUE = {"10k": "C2649453", "1nF": "C49002957", "220uF 25V": "C47344177", "1000uF 25V": "C48935382",
                 "RED": "C2895470", "1N5822": "C2476", "1N4007": "C2985028", "P6KE15A": "C294003"}


def rp(ref, part_id, value, pins, group, nc=()):
    PARTS.append(_parts.registry_part(ref, part_id, value, pins, group, nc, lcsc=LCSC_BY_VALUE.get(value)))


def R(ref, value, a, b, group):
    rp(ref, R_ID, value, {1: a, 2: b}, group)


def C(ref, value, a, b, group, part_id=C_ID):
    rp(ref, part_id, value, {1: a, 2: b}, group)


def LED(ref, color, cathode, anode, group, part_id=LED3_ID):
    rp(ref, part_id, color, {"K": cathode, "A": anode}, group)


# ── 1. Power: 12V in -> fuse -> TVS/bulk -> magnets ; diode -> buck -> 5V ──
G = "power"
rp("J1", J_PWR_ID, "12V_IN", {1: "+12V_IN", 2: "GND"}, G)
rp("F1", FUSE_ID, "10A mini blade", {1: "+12V_IN", 2: "+12V"}, G)
rp("D1", DO15_ID, "P6KE15A", {"K": "+12V", "A": "GND"}, G)
rp("C1", CP10_ID, "1000uF 25V", {1: "+12V", 2: "GND"}, G)           # Device:C_Polarized, pad 1 = +
rp("D2", DO41_ID, "1N4007", {"K": "+12V_REG", "A": "+12V"}, G)
rp("U1", MODULE_ID, "5V 2A module (K7805-2000R3)", {"IN": "+12V_REG", "GND": "GND", "OUT": "+5V"}, G)
C("C2", "220uF 25V", "+12V_REG", "GND", G, CE_ID)                  # Device:C_Polarized, pad 1 = +
C("C3", "100nF", "+12V_REG", "GND", G)
C("C6", "220uF 25V", "+5V", "GND", G, CE_ID)                       # Device:C_Polarized, pad 1 = +
C("C7", "100nF", "+5V", "GND", G)
R("R1", "4.7k", "+12V", "PWR12_LED", G)
LED("D3", "GREEN", "GND", "PWR12_LED", G, LED5_ID)
R("R2", "1k", "+5V", "PWR5_LED", G)
LED("D4", "GREEN", "GND", "PWR5_LED", G, LED5_ID)

# ── 2. Controllers ──────────────────────────────────────────
G = "mcu"
MAG_PINS = ["D3", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D44"]
mega = {
    "D2": "COIN_IN", "D18": "MEGA_TX1", "D19": "ESP_TX2",
    "D22": "BTN_S1", "D24": "BTN_S2", "D26": "BTN_S3", "D28": "BTN_RST",
    "A0": "SEG_DATA", "A1": "SEG_LATCH", "A2": "SEG_CLOCK",
    "A3": "LED1", "A4": "LED2", "A5": "LED3", "A6": "LED4",
    "D20": "I2C_SDA", "D21": "I2C_SCL", "D4": "SPARE_D4", "D13": "SPARE_D13",
    "A7": "SPARE_A7", "A8": "SPARE_A8",
    "D14": "SPARE_TX3", "D15": "SPARE_RX3", "D30": "SPARE_D30", "D31": "SPARE_D31",
    "D32": "SPARE_D32", "D33": "SPARE_D33",
    "D50": "SPARE_MISO", "D51": "SPARE_MOSI", "D52": "SPARE_SCK", "D53": "SPARE_CS",
    "5V1": "+5V", "5V3": "+5V", "5V4": "+5V", "3V3": "+3V3",
    "GND1": "GND", "GND2": "GND", "GND3": "GND", "GND5": "GND", "GND6": "GND",
}
for i, p in enumerate(MAG_PINS):
    mega[p] = "MAG%d_PWM" % (i + 1)
# The Mega shield footprint has ~90 pads and most are spare: every pad not listed here is unconnected
# by design (nc="rest" is only allowed for connector records). Same for the ESP32 socket's unused pins.
rp("A1", MEGA_ID, "Arduino Mega 2560 R3", mega, G, nc="rest")
rp("A2", ESP32_ID, "ESP32 DevKit V1 (30 pin)",
   {"VIN(5V)": "+5V", "GND#1": "GND", "GND#2": "GND", "RX2/IO16": "ESP_RX2", "TX2/IO17": "ESP_TX2",
    "3V3": "+3V3_ESP", "IO25": "ESP_IO25", "IO26": "ESP_IO26", "IO27": "ESP_IO27",
    "IO32": "ESP_IO32", "IO33": "ESP_IO33", "IO14": "ESP_IO14"}, G, nc="rest")

# ── 3. Serial link Mega TX1 (5V) -> divider -> ESP32 RX2 (3.3V) ──
G = "serial"
R("R62", "1k", "MEGA_TX1", "ESP_RX2", G)
R("R63", "2k", "ESP_RX2", "GND", G)

# ── 4. 10 electromagnet drivers ─────────────────────────────
G = "magnets"
for i in range(1, 11):
    rp("J%d" % (1 + i), J_MAG_ID, "MAG%d" % i, {1: "+12V", 2: "MAG%d_OUT" % i}, G)
    rp("Q%d" % i, Q_ID, "IRLZ44N", {"G": "MAG%d_G" % i, "D": "MAG%d_OUT" % i, "S": "GND"}, G)
    R("R%d" % (10 + i), "100R", "MAG%d_PWM" % i, "MAG%d_G" % i, G)
    R("R%d" % (20 + i), "10k", "MAG%d_G" % i, "GND", G)
    rp("D%d" % (10 + i), DO201V_ID, "1N5822", {"K": "+12V", "A": "MAG%d_OUT" % i}, G)
    LED("D%d" % (20 + i), "RED", "MAG%d_LED" % i, "+12V", G)
    R("R%d" % (30 + i), "2.2k", "MAG%d_LED" % i, "MAG%d_OUT" % i, G)

# ── 5. Coin acceptor (optocoupler input) ────────────────────
G = "coin"
rp("J12", J3_ID, "COIN", {1: "+12V", 2: "GND", 3: "COIN_SIG"}, G)
R("R41", "2.2k", "+12V", "COIN_OPTO_A", G)
rp("U2", OPTO_ID, "PC817", {"A": "COIN_OPTO_A", "K": "COIN_SIG", "E": "GND", "C": "COIN_IN"}, G)
R("R42", "10k", "+5V", "COIN_IN", G)
C("C8", "1nF", "COIN_IN", "GND", G)

# ── 6. Buttons (RC filter + strong pull-up) ─────────────────
G = "buttons"
BTN = ["S1", "S2", "S3", "RST"]
jb = {}
for k, b in enumerate(BTN):
    jb[2 * k + 1] = "BTN_%s_EXT" % b
    jb[2 * k + 2] = "GND"
    R("R%d" % (43 + k), "1k", "BTN_%s_EXT" % b, "BTN_%s" % b, G)
    R("R%d" % (47 + k), "10k", "+5V", "BTN_%s" % b, G)
    C("C%d" % (9 + k), "100nF", "BTN_%s" % b, "GND", G)
rp("J13", J8_ID, "BUTTONS", jb, G)

# ── 7. Status LEDs ──────────────────────────────────────────
G = "leds"
jl = {}
for k in range(4):
    jl[2 * k + 1] = "LED%d_OUT" % (k + 1)
    jl[2 * k + 2] = "GND"
    R("R%d" % (51 + k), "330R", "LED%d" % (k + 1), "LED%d_OUT" % (k + 1), G)
rp("J14", J8_ID, "STATUS_LEDS", jl, G)

# ── 8. 7-segment via 74HC595 (bit map from firmware) ────────
G = "sevenseg"
# Two outputs are unconnected BY DESIGN, not forgotten:
#   QA  (pin 15) - the firmware's segment byte leaves bit 7 unused (CODES/arduino_main_code.cpp:
#                  "QA (bit 7) -> NOT CONNECTED"); the 7 segments A..G are on QB..QH (bits 6..0).
#   QH' (pin 9)  - the serial-out for daisy-chaining a second register; there is no second register.
rp("U3", SR_ID, "74HC595N", {
    "SER": "SEG_DATA", "RCLK": "SEG_LATCH", "SRCLK": "SEG_CLOCK", "SRCLR": "+5V", "OE": "GND",
    "VCC": "+5V", "GND": "GND",
    "QB": "SEG_QB", "QC": "SEG_QC", "QD": "SEG_QD", "QE": "SEG_QE", "QF": "SEG_QF", "QG": "SEG_QG", "QH": "SEG_QH",
}, G, nc=["QA", "QH'"])
C("C13", "100nF", "+5V", "GND", G)
SEG_FROM = [("A", "QD"), ("B", "QG"), ("C", "QF"), ("D", "QH"), ("E", "QE"), ("F", "QC"), ("G", "QB")]
js = {8: "GND"}
for k, (seg, q) in enumerate(SEG_FROM):
    R("R%d" % (55 + k), "470R", "SEG_" + q, "SEG_" + seg, G)
    js[k + 1] = "SEG_" + seg
rp("J15", J8_ID, "7SEG", js, G)

# ── 9. Expansion header ─────────────────────────────────────
G = "expansion"
rp("J16", HDR2x10_ID, "MEGA SPARE", {
    1: "+5V", 2: "GND", 3: "+3V3", 4: "GND",
    5: "I2C_SDA", 6: "I2C_SCL", 7: "SPARE_TX3", 8: "SPARE_RX3",
    9: "SPARE_D4", 10: "SPARE_D13", 11: "SPARE_D30", 12: "SPARE_D31",
    13: "SPARE_D32", 14: "SPARE_D33", 15: "SPARE_A7", 16: "SPARE_A8",
    17: "SPARE_SCK", 18: "SPARE_MISO", 19: "SPARE_MOSI", 20: "SPARE_CS"}, G)
rp("J17", HDR2x4_ID, "ESP32 SPARE", {
    1: "+3V3_ESP", 2: "GND", 3: "ESP_IO25", 4: "ESP_IO26",
    5: "ESP_IO27", 6: "ESP_IO32", 7: "ESP_IO33", 8: "ESP_IO14"}, G)

GROUPS = [
    ("power", "POWER: 12V INPUT, FUSE, SURGE PROTECTION, 12V -> 5V REGULATOR"),
    ("mcu", "CONTROLLERS: ARDUINO MEGA 2560 (shield) + ESP32 DEVKIT V1"),
    ("serial", "SERIAL: MEGA TX1 (5V) -> DIVIDER -> ESP32 RX2 (3.3V)"),
    ("magnets", "10x ELECTROMAGNET DRIVERS (IRLZ44N + FLYBACK DIODE + ON LED)"),
    ("coin", "COIN ACCEPTOR INPUT (OPTOCOUPLER)"),
    ("buttons", "BUTTONS: SPEED1 / SPEED2 / SPEED3 / RESET"),
    ("leds", "STATUS LEDS"),
    ("sevenseg", "7-SEGMENT DISPLAY DRIVER (74HC595)"),
    ("expansion", "EXPANSION HEADER"),
]
POWER_FLAG_NETS = ["+12V", "+12V_REG", "GND"]   # +5V is driven by the U1 module output


# Electrical intent, read by tools/boardgen/lint_netlist.py (v in volts: number or (min, max); i_max in A).
# MAGn_OUT is the MOSFET drain: its level when the magnet is ON (~0 V). Magnets are sized for <=1.5 A
# each, with a 10 A blade fuse on the 12 V input (see DESIGN_BRIEF / HANDOVER).
NET_SPEC = {
    "GND": {"v": 0.0, "i_max": 10.0},
    "+12V_IN": {"v": (10.8, 13.2), "i_max": 10.0},   # 12 V +-10 % (the user's supply)
    "+12V": {"v": (10.8, 13.2), "i_max": 10.0},
    "+12V_REG": {"v": (9.8, 13.2), "i_max": 1.0},        # only feeds the 5 V module (via D2)
    "+5V": {"v": (4.75, 5.25), "i_max": 2.0},                # K7805-2000R3 module (derived 4.85-5.15 V) or Mega USB 5 V; was a point 5.0 = EL-NETSPEC conflict
    "+3V3": {"v": 3.3, "i_max": 0.5},
    "+3V3_ESP": {"v": 3.3, "i_max": 0.5},
}
for _i in range(1, 11):
    NET_SPEC["MAG%d_OUT" % _i] = {"v": 0.0, "i_max": 1.5}


# What the outside world does to every connector pin (P2 electrical analyzer; EL-CONN-PROT reads this). Sources: DESIGN_BRIEF,
# WIRING_GUIDE (one 12 V 16 A supply, off-board magnets/coin acceptor/buttons/LEDs/7-segment, Mega shield + ESP32 socket).
# GND pins are ground-class nets and need no entry. A pin gets no `v` where NET_SPEC already holds a POINT claim for the
# net (+3V3, +3V3_ESP, MAGn_OUT): declaring the honest range would only create a NET_SPEC conflict in the model.
_MEGA_OUT = [n for n in ("MAG%d_PWM" % i for i in range(1, 11))] + ["SEG_DATA", "SEG_LATCH", "SEG_CLOCK", "LED1", "LED2",
                                                                    "LED3", "LED4", "MEGA_TX1"]
_MEGA_IN = ["BTN_S1", "BTN_S2", "BTN_S3", "BTN_RST", "COIN_IN", "ESP_TX2"]
_MEGA_IO = ["I2C_SDA", "I2C_SCL"] + sorted(n for n in mega.values() if n.startswith("SPARE_"))
_MEGA_PADS = {n: p for p, n in mega.items()}
EXTERNAL = X.merge(
    X.pins("J1", [1], dir="supply", v=(10.8, 13.2), i=16.0,
           why="the single 12 V 16 A supply (DESIGN_BRIEF), +-10 % assumed; the 10 A blade fuse F1 is the protection"),
    *[X.pins("J%d" % j, [1, 2], dir="out", i=1.5,
             why="MAG%d electromagnet coil wired by the user (WIRING_GUIDE), sized <= 1.5 A (i = that design figure, continuous), flyback diode D%d on board" % (j - 1, j + 9))
      for j in range(2, 12)],
    X.pins("J12", [1], dir="out", why="12 V supply for the coin acceptor (WIRING_GUIDE J12)"),
    X.pins("J12", [3], dir="in", v=(0.0, 13.2),
           why="coin acceptor open-collector SIG (pulls low per pulse), 12 V pull-up level, feeds the PC817 opto input"),
    X.pins("J13", [1, 3, 5, 7], dir="in", v=(0.0, 5.25),
           why="off-board push button to GND (dry contact), 5 V pull-up on the board side, long cable assumed"),
    X.pins("J14", [1, 3, 5, 7], dir="out", why="off-board status LED anode (WIRING_GUIDE J14), 330R series resistor on board"),
    X.pins("J15", [1, 2, 3, 4, 5, 6, 7], dir="out", why="7-segment common-cathode segment anode (470R series on board)"),
    X.pins("J16", [1], dir="out", why="expansion header: 5 V rail offered to a user add-on"),
    X.pins("J16", [3], dir="out", why="expansion header: Mega 3V3 rail offered to a user add-on"),
    X.pins("J16", range(5, 21), dir="bidir", v=(0.0, 5.25),
           why="expansion header: spare Mega I/O, 5 V logic, free for a user add-on (nothing is specified)"),
    X.pins("J17", [1], dir="out", why="ESP32 spare header: DevKit 3V3 rail offered to a user add-on"),
    X.pins("J17", range(3, 9), dir="bidir", v=(0.0, 3.465),
           why="ESP32 spare header: spare ESP32 GPIO, 3.3 V logic, free for a user add-on (nothing is specified)"),
    {"J16": {"class": "expansion", "why": "spare Mega I/O for user add-ons; nothing on the board uses it"},
     "J17": {"class": "expansion", "why": "spare ESP32 GPIO for user add-ons; nothing on the board uses it"}},
    X.none("F1"),                  # blade fuse holder: a series element on +12V_IN, nothing is wired to it from outside
    # The Mega shield socket A1: the Mega is the outside world (5 V logic, USB may also be plugged for programming).
    X.pins("A1", [_MEGA_PADS[n] for n in _MEGA_OUT], dir="in", v=(0.0, 5.25), why="Mega 5 V push-pull output drives this board"),
    X.pins("A1", [_MEGA_PADS[n] for n in _MEGA_IN if n != "ESP_TX2"], dir="out", v=(0.0, 5.25),
           why="Mega input: this board drives it (5 V pull-up / opto collector)"),
    X.pins("A1", [_MEGA_PADS["ESP_TX2"]], dir="out", v=(0.0, 3.465), why="Mega RX1 input, driven by the ESP32 TX2 (3.3 V logic)"),
    X.pins("A1", [_MEGA_PADS[n] for n in _MEGA_IO], dir="bidir", v=(0.0, 5.25), why="Mega spare I/O, 5 V logic (also on J16)"),
    X.pins("A1", ["5V1", "5V3", "5V4"], dir="bidir",
           why="Mega 5V rail: fed by U1 on this board, also by the Mega USB when plugged in (DESIGN_BRIEF G2/G4)"),
    X.pins("A1", ["3V3"], dir="supply", i=0.05, why="Mega 3V3 pin (onboard regulator, 50 mA max per Arduino spec)"),
    # ESP32 DevKit socket A2 (pad numbers of the 30-pin socket; names in the record)
    X.pins("A2", ["15"], dir="out", why="ESP32 VIN: this board feeds the DevKit with 5 V (WIRING_GUIDE)"),
    X.pins("A2", ["30"], dir="supply", i=0.5, why="ESP32 DevKit 3V3 pin (onboard LDO); 0.5 A is the NET_SPEC +3V3_ESP budget"),
    X.pins("A2", ["24"], dir="in", v=(0.0, 3.465), why="ESP32 TX2 push-pull output, 3.3 V logic"),
    X.pins("A2", ["25"], dir="out", why="ESP32 RX2 input behind the 1k/2k divider from Mega TX1 (3.33 V)"),
    X.pins("A2", ["6", "7", "8", "9", "10", "11"], dir="bidir", v=(0.0, 3.465), why="ESP32 spare GPIO, 3.3 V logic (also on J17)"),
)


FIRMWARE = {
    # Read by tools/boardgen/check_pinmap.py (schema documented there).
    "files": ["../../CODES/arduino_main_code.cpp"],
    "mcu_ref": "A1",
    "analog_base": 54,
    "fixed": {"D18": "MEGA_TX1", "D19": "ESP_TX2"},           # Serial1 pins are fixed in hardware
    "signals": {
        "PWM_PINS": ["MAG%d_PWM" % i for i in range(1, 11)],
        "BTN_SPEED1": "BTN_S1", "BTN_SPEED2": "BTN_S2", "BTN_SPEED3": "BTN_S3", "BTN_RESET": "BTN_RST",
        "COIN_PIN": "COIN_IN", "SEG_DATA": "SEG_DATA", "SEG_LATCH": "SEG_LATCH", "SEG_CLOCK": "SEG_CLOCK",
        "LED1": "LED1", "LED2": "LED2", "LED3": "LED3", "LED4": "LED4",
    },
    "wokwi_part": "mega",
    "also": [{
        "files": ["../../CODES/ESP32_main_code.cpp"],
        "mcu_ref": "A2",
        "wokwi": False,
        "pad_to_pin": {"25": "16", "24": "17", "6": "32", "7": "33", "8": "25", "9": "26", "10": "27", "11": "14"},
        "pin_regex": r"(^|_)PIN\d*$",
        "signals": {"RX2_PIN": "ESP_RX2", "TX2_PIN": "ESP_TX2"},
    }],
}


# Executable requirements (judged by the `requirements` stage -> out/REQUIREMENTS.md); design intent from DESIGN_BRIEF.md.
REQUIREMENTS = [
    {"id": "R1", "kind": "path", "from": "J1.1", "to": "+12V", "through": {"class": "fuse"},
     "text": "The 12 V input reaches the board rail only through the 10 A fuse F1"},
    {"id": "R2", "kind": "path", "from": "+12V", "to": "U1.IN", "through": {"ref": "D2"},
     "text": "The 5 V module is fed through the reverse-polarity diode D2"},
    {"id": "R3", "kind": "path_absent", "from": "+12V_REG", "to": "+12V",
     "text": "The module supply never back-feeds the magnet rail (D2 blocks it)"},
    {"id": "R4", "kind": "path_absent", "from": "J12.3", "to": "COIN_IN",
     "text": "The coin acceptor signal reaches the Mega only through the PC817 optocoupler (no galvanic path)"},
    {"id": "R5", "kind": "path_absent", "from": "+12V", "to": "+5V",
     "text": "No passive DC path from the 12 V rail to the 5 V rail except through the module"},
    {"id": "R6", "kind": "path_absent", "from": "+12V", "to": "MAG1_PWM",
     "text": "The 12 V rail has no passive path to a Mega PWM pin"},
] + [
    {"id": "M%d" % i, "kind": "path", "from": "J%d.2" % (1 + i), "to": "Q%d.S" % i, "with": {"Q%d" % i: "on"},
     "text": "Magnet %d: with its MOSFET Q%d on, the magnet terminal MAG%d_OUT conducts to GND" % (i, i, i)}
    for i in range(1, 11)
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
    for n, members in sorted(ns.items()):
        if len(members) < 2:
            print("WARNING single-pin net", n, members)
