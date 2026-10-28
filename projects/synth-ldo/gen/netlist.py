"""synth-ldo - NETLIST-ONLY synthetic fixture (no board, no schematic, never fabricated). P2-T6.

The power path and the 3V3 budget of projects/ref-esp32/ARCHITECTURE.md sections 2.1-2.4: USB VBUS (4.40-5.25 V at the
device end, 500 mA default power) -> PTC F1 (Ihold 1.1 A, R1max 0.25 ohm) -> VBUS_F -> LDO U2 (LDL1117S33R) -> 3V3 ->
ESP32-S3-WROOM-1-N8 + SHT30 + I2C pull-ups + EN/BOOT pull-ups + two LEDs + a 100 mA allowance header. A 35 mA allowance sits on
the 5 V side (J3). It exists to prove EL-BUDGET / EL-DROPOUT / EL-THERMAL against the hand calculation of that document:
the mutation M-ldo swaps U2 for the AMS1117-3.3 record (same pin order), which must fail EL-DROPOUT.
"""
import os
import sys

PRJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_NAME = "synth-ldo"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PRJ_DIR)), "tools"))
from boardgen import parts as _parts  # noqa: E402

PROJECT_LIBS = ()
SCH_TITLE = "synth-ldo (netlist-only power-path fixture)"
SCH_SUBTITLE = "USB -> PTC -> LDO -> ESP32-S3 of ref-esp32"
SCH_DATE = "2026-10-28"
SCH_REV = "0.1"
PARTS_STRICT = True

R_ID, C_ID, SW_ID, HDR_ID, MCU_ID = ("res-axial-0207-p10.16", "cap-disc-5mm-p5.00", "sw-push-6mm-tht", "hdr-2x04-p2.54-v",
                                      "esp32-s3-wroom-1-n8")
LED_ID, SNS_ID, PTC_ID, LDO_ID = "led-5mm", "sht30-dis-b2.5ks-dfn8ep2.5x2.5", "ptc-smd1206p110tf", "ldl1117s33r-sot2234"
PARTS = []

# ESP32-S3 module pads: 1,40,41 GND; 2 3V3; 3 EN; 12 IO8 (SDA); 17 IO9 (SCL); 23 IO21 (LED); 27 IO0 (BOOT).
_USED = {"1": "GND", "2": "3V3", "3": "EN", "12": "I2C_SDA", "17": "I2C_SCL", "23": "LED_STATUS", "27": "BOOT",
         "40": "GND", "41": "GND"}
_NC = [str(i) for i in range(4, 41) if str(i) not in _USED]
PARTS.append(_parts.registry_part("U1", MCU_ID, "ESP32-S3-WROOM-1-N8", _USED, "mcu", nc=_NC))
PARTS.append(_parts.registry_part("U2", LDO_ID, "3V3 LDO", {1: "GND", 2: "3V3", 3: "VBUS_F"}, "power"))
PARTS.append(_parts.registry_part("U3", SNS_ID, "SHT30", {1: "I2C_SDA", 2: "GND", 4: "I2C_SCL", 5: "3V3", 8: "GND", 9: "GND"}, "sensor",
                                  nc=[3, 6, 7]))
PARTS.append(_parts.registry_part("F1", PTC_ID, "1.1A PTC", {1: "VBUS", 2: "VBUS_F"}, "power"))
PARTS.append(_parts.registry_part("J1", HDR_ID, "USB 5V IN", {1: "VBUS", 2: "GND"}, "power", nc=[3, 4, 5, 6, 7, 8]))
PARTS.append(_parts.registry_part("J2", HDR_ID, "3V3 OUT", {1: "3V3", 2: "GND"}, "power", nc=[3, 4, 5, 6, 7, 8]))
PARTS.append(_parts.registry_part("J3", HDR_ID, "5V OUT", {1: "VBUS_F", 2: "GND"}, "power", nc=[3, 4, 5, 6, 7, 8]))
PARTS.append(_parts.registry_part("R3", R_ID, "10k", {1: "3V3", 2: "EN"}, "boot"))
PARTS.append(_parts.registry_part("C5", C_ID, "1uF", {1: "EN", 2: "GND"}, "boot"))
PARTS.append(_parts.registry_part("SW2", SW_ID, "RESET", {1: "EN", 2: "GND"}, "boot"))
PARTS.append(_parts.registry_part("R4", R_ID, "10k", {1: "3V3", 2: "BOOT"}, "boot"))
PARTS.append(_parts.registry_part("SW1", SW_ID, "BOOT", {1: "BOOT", 2: "GND"}, "boot"))
PARTS.append(_parts.registry_part("R5", R_ID, "2.2k", {1: "3V3", 2: "I2C_SDA"}, "sensor"))
PARTS.append(_parts.registry_part("R6", R_ID, "2.2k", {1: "3V3", 2: "I2C_SCL"}, "sensor"))
PARTS.append(_parts.registry_part("R7", R_ID, "1k", {1: "3V3", 2: "LED1_A"}, "leds"))
PARTS.append(_parts.registry_part("LED1", LED_ID, "RED", {"A": "LED1_A", "K": "GND"}, "leds"))
PARTS.append(_parts.registry_part("R8", R_ID, "470R", {1: "LED_STATUS", 2: "LED2_A"}, "leds"))
PARTS.append(_parts.registry_part("LED2", LED_ID, "RED", {"A": "LED2_A", "K": "GND"}, "leds"))
GROUPS = [("mcu", "ESP32-S3 module"), ("power", "USB power path"), ("boot", "Boot and reset"), ("sensor", "Sensor and I2C"),
          ("leds", "Indicators")]

POWER_FLAG_NETS = ["VBUS", "VBUS_F", "3V3", "GND"]
NET_SPEC = {"VBUS": {"v": (4.4, 5.25), "i_max": 0.6}, "VBUS_F": {"v": (4.1, 5.25), "i_max": 0.6},
            "3V3": {"v": (3.0, 3.6), "i_max": 1.0}, "GND": {"v": 0.0, "i_max": 0.6}}
EXTERNAL = {"J1.1": {"v": (4.4, 5.25), "i": 0.5, "dir": "supply", "why": "USB host VBUS at the device end, 500 mA default power"},
            "J1.2": {"v": (0.0, 0.0), "dir": "supply", "why": "USB ground"},
            "J2.1": {"i": 0.1, "dir": "out", "why": "3V3 header: 100 mA external allowance (ARCHITECTURE 2.2)"},
            "J2.2": {"dir": "out", "why": "ground of the 3V3 header"},
            "J3.1": {"i": 0.030, "dir": "out", "why": "5V header: 30 mA allowance (ARCHITECTURE 2.4 says 35; 5 mA less so the conservative pull-up count still fits the 500 mA cap)"},
            "J3.2": {"dir": "out", "why": "ground of the 5V header"},
            "SW1": "none", "SW2": "none"}
