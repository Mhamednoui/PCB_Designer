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
PROJECT_LIBS = ("arduino-library", "reflex")

_NS = uuid.UUID("6f1b5f5e-3c1a-4a55-9a53-8a1f2c7d0b11")


def uid(*parts):
    return str(uuid.uuid5(_NS, "/".join(parts)))


# ── Footprints ──────────────────────────────────────────────
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CE = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_LED3 = "LED_THT:LED_D3.0mm"
FP_LED5 = "LED_THT:LED_D5.0mm"
FP_DO41 = "Diode_THT:D_DO-41_SOD81_P7.62mm_Horizontal"
FP_DO201V = "Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp"
FP_DO15 = "Diode_THT:D_DO-15_P10.16mm_Horizontal"
FP_TO220 = "Package_TO_SOT_THT:TO-220-3_Vertical"
FP_DIP4 = "Package_DIP:DIP-4_W7.62mm"
FP_DIP16 = "Package_DIP:DIP-16_W7.62mm"
FP_MODULE = "Converter_DCDC:Converter_DCDC_RECOM_R-78B-2.0_THT"
FP_CP10 = "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm"
FP_FUSE = "Fuse:Fuseholder_Blade_Mini_Keystone_3568"
FP_J_PWR = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal"
FP_J_MAG = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
FP_J3 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-3-3.5-H_1x03_P3.50mm_Horizontal"
FP_J8 = "TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal"
FP_HDR2x10 = "Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical"
FP_HDR2x4 = "Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical"
FP_MEGA = "arduino-library:Arduino_Mega2560_R3_Shield"
FP_ESP32 = "reflex:ESP32_DevKit_V1_30pin_Socket"

# ── LCSC part numbers (JLCPCB assembly) ─────────────────────
LCSC = {
    "10k": "C2649453", "1k": "", "100R": "", "330R": "", "470R": "",
    "2.2k": "", "2k": "", "4.7k": "", "100nF": "", "1nF": "C49002957",
    "220uF 25V": "C47344177", "1000uF 25V": "C48935382", "LED_RED": "C2895470", "LED_GREEN": "",
    "1N5822": "C2476", "1N4007": "C2985028", "P6KE15A": "C294003",
    "74HC595N": "C507175", "PC817": "C20612594", "IRLZ44N": "C38774",
    "K7805": "C18212380",
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


def LED(ref, color, cathode, anode, group, fp=FP_LED3):
    part(ref, "Device:LED", color, fp, {1: cathode, 2: anode}, group, LCSC["LED_" + color])


# ── 1. Power: 12V in -> fuse -> TVS/bulk -> magnets ; diode -> buck -> 5V ──
G = "power"
part("J1", "Connector:Screw_Terminal_01x02", "12V_IN", FP_J_PWR, {1: "+12V_IN", 2: "GND"}, G)
part("F1", "Device:Fuse", "10A mini blade", FP_FUSE, {1: "+12V_IN", 2: "+12V"}, G)
part("D1", "Device:D_Zener", "P6KE15A", FP_DO15, {1: "+12V", 2: "GND"}, G, LCSC["P6KE15A"])
part("C1", "Device:C_Polarized", "1000uF 25V", FP_CP10, {1: "+12V", 2: "GND"}, G, LCSC["1000uF 25V"])
part("D2", "Device:D", "1N4007", FP_DO41, {1: "+12V_REG", 2: "+12V"}, G, LCSC["1N4007"])
part("U1", "Converter_DCDC:R-785.0-1.0", "5V 2A module (K7805-2000R3)", FP_MODULE,
     {1: "+12V_REG", 2: "GND", 3: "+5V"}, G, LCSC["K7805"])
C("C2", "220uF 25V", "+12V_REG", "GND", G, FP_CE)
C("C3", "100nF", "+12V_REG", "GND", G)
C("C6", "220uF 25V", "+5V", "GND", G, FP_CE)
C("C7", "100nF", "+5V", "GND", G)
R("R1", "4.7k", "+12V", "PWR12_LED", G)
LED("D3", "GREEN", "GND", "PWR12_LED", G, FP_LED5)
R("R2", "1k", "+5V", "PWR5_LED", G)
LED("D4", "GREEN", "GND", "PWR5_LED", G, FP_LED5)

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
part("A1", "arduino-library:Arduino_Mega2560_R3_Shield", "Arduino Mega 2560 R3", FP_MEGA, mega, G)
part("A2", "reflex:ESP32_DevKit_V1_30pin", "ESP32 DevKit V1 (30 pin)", FP_ESP32,
     {15: "+5V", 14: "GND", 29: "GND", 25: "ESP_RX2", 24: "ESP_TX2",
      30: "+3V3_ESP", 8: "ESP_IO25", 9: "ESP_IO26", 10: "ESP_IO27",
      6: "ESP_IO32", 7: "ESP_IO33", 11: "ESP_IO14"}, G)

# ── 3. Serial link Mega TX1 (5V) -> divider -> ESP32 RX2 (3.3V) ──
G = "serial"
R("R62", "1k", "MEGA_TX1", "ESP_RX2", G)
R("R63", "2k", "ESP_RX2", "GND", G)

# ── 4. 10 electromagnet drivers ─────────────────────────────
G = "magnets"
for i in range(1, 11):
    part("J%d" % (1 + i), "Connector:Screw_Terminal_01x02", "MAG%d" % i, FP_J_MAG,
         {1: "+12V", 2: "MAG%d_OUT" % i}, G)
    part("Q%d" % i, "Transistor_FET:IRLZ44N", "IRLZ44N", FP_TO220,
         {1: "MAG%d_G" % i, 2: "MAG%d_OUT" % i, 3: "GND"}, G, LCSC["IRLZ44N"])
    R("R%d" % (10 + i), "100R", "MAG%d_PWM" % i, "MAG%d_G" % i, G)
    R("R%d" % (20 + i), "10k", "MAG%d_G" % i, "GND", G)
    part("D%d" % (10 + i), "Device:D_Schottky", "1N5822", FP_DO201V, {1: "+12V", 2: "MAG%d_OUT" % i}, G, LCSC["1N5822"])
    LED("D%d" % (20 + i), "RED", "MAG%d_LED" % i, "+12V", G)
    R("R%d" % (30 + i), "2.2k", "MAG%d_LED" % i, "MAG%d_OUT" % i, G)

# ── 5. Coin acceptor (optocoupler input) ────────────────────
G = "coin"
part("J12", "Connector:Screw_Terminal_01x03", "COIN", FP_J3, {1: "+12V", 2: "GND", 3: "COIN_SIG"}, G)
R("R41", "2.2k", "+12V", "COIN_OPTO_A", G)
part("U2", "Isolator:PC817", "PC817", FP_DIP4,
     {1: "COIN_OPTO_A", 2: "COIN_SIG", 3: "GND", 4: "COIN_IN"}, G, LCSC["PC817"])
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
part("J13", "Connector:Screw_Terminal_01x08", "BUTTONS", FP_J8, jb, G)

# ── 7. Status LEDs ──────────────────────────────────────────
G = "leds"
jl = {}
for k in range(4):
    jl[2 * k + 1] = "LED%d_OUT" % (k + 1)
    jl[2 * k + 2] = "GND"
    R("R%d" % (51 + k), "330R", "LED%d" % (k + 1), "LED%d_OUT" % (k + 1), G)
part("J14", "Connector:Screw_Terminal_01x08", "STATUS_LEDS", FP_J8, jl, G)

# ── 8. 7-segment via 74HC595 (bit map from firmware) ────────
G = "sevenseg"
part("U3", "74xx:74HC595", "74HC595N", FP_DIP16, {
    14: "SEG_DATA", 12: "SEG_LATCH", 11: "SEG_CLOCK", 10: "+5V", 13: "GND", 16: "+5V", 8: "GND",
    1: "SEG_QB", 2: "SEG_QC", 3: "SEG_QD", 4: "SEG_QE", 5: "SEG_QF", 6: "SEG_QG", 7: "SEG_QH",
}, G, LCSC["74HC595N"])
C("C13", "100nF", "+5V", "GND", G)
SEG_FROM = [("A", "QD"), ("B", "QG"), ("C", "QF"), ("D", "QH"), ("E", "QE"), ("F", "QC"), ("G", "QB")]
js = {8: "GND"}
for k, (seg, q) in enumerate(SEG_FROM):
    R("R%d" % (55 + k), "470R", "SEG_" + q, "SEG_" + seg, G)
    js[k + 1] = "SEG_" + seg
part("J15", "Connector:Screw_Terminal_01x08", "7SEG", FP_J8, js, G)

# ── 9. Expansion header ─────────────────────────────────────
G = "expansion"
part("J16", "Connector_Generic:Conn_02x10_Odd_Even", "MEGA SPARE", FP_HDR2x10, {
    1: "+5V", 2: "GND", 3: "+3V3", 4: "GND",
    5: "I2C_SDA", 6: "I2C_SCL", 7: "SPARE_TX3", 8: "SPARE_RX3",
    9: "SPARE_D4", 10: "SPARE_D13", 11: "SPARE_D30", 12: "SPARE_D31",
    13: "SPARE_D32", 14: "SPARE_D33", 15: "SPARE_A7", 16: "SPARE_A8",
    17: "SPARE_SCK", 18: "SPARE_MISO", 19: "SPARE_MOSI", 20: "SPARE_CS"}, G)
part("J17", "Connector_Generic:Conn_02x04_Odd_Even", "ESP32 SPARE", FP_HDR2x4, {
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
    "+12V_IN": {"v": 12.0, "i_max": 10.0},
    "+12V": {"v": 12.0, "i_max": 10.0},
    "+12V_REG": {"v": 12.0, "i_max": 1.0},          # only feeds the 5 V module (via D2)
    "+5V": {"v": 5.0, "i_max": 2.0},                # K7805-2000R3 module, 2 A
    "+3V3": {"v": 3.3, "i_max": 0.5},
    "+3V3_ESP": {"v": 3.3, "i_max": 0.5},
}
for _i in range(1, 11):
    NET_SPEC["MAG%d_OUT" % _i] = {"v": 0.0, "i_max": 1.5}


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
