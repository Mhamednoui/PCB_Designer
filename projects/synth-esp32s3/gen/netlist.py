"""synth-esp32s3 - NETLIST-ONLY synthetic fixture (no board, no schematic, never fabricated).

Purpose: give the electrical rules (EL-STRAP) and the mutation harness a real ESP32-S3-WROOM-1-N8 design to chew on,
because no signed-off project carries one yet. The wiring is the strapping/boot part of projects/ref-esp32/ARCHITECTURE.md
section 4: GPIO0 = 10k pull-up + BOOT button to GND (no capacitor); GPIO3/45/46 unconnected; EN = 10k pull-up + 1uF to GND
+ RESET button. Everything else on the module is NC; the 3V3 rail is declared as an external supply (no regulator here).
"""
import os
import sys

PRJ_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_NAME = "synth-esp32s3"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(PRJ_DIR)), "tools"))
from boardgen import parts as _parts  # noqa: E402

PROJECT_LIBS = ()
SCH_TITLE = "synth-esp32s3 (netlist-only strap fixture)"
SCH_SUBTITLE = "ESP32-S3 boot/strap wiring of ref-esp32"
SCH_DATE = "2026-10-28"
SCH_REV = "0.1"
PARTS_STRICT = True

R_ID, C_ID, SW_ID, HDR_ID, MCU_ID = "res-axial-0207-p10.16", "cap-disc-5mm-p5.00", "sw-push-6mm-tht", "hdr-2x04-p2.54-v", "esp32-s3-wroom-1-n8"
PARTS = []

# Module pads by number (see parts/records/esp32-s3-wroom-1-n8.json): 1,40,41 GND; 2 3V3; 3 EN; 27 IO0.
# IO3 (15), IO45 (26), IO46 (16) stay NC (strapping pins, defaults give the boot state).
_USED = {"1": "GND", "2": "3V3", "3": "EN", "27": "BOOT", "40": "GND", "41": "GND"}
_NC = [str(i) for i in range(4, 41) if str(i) not in _USED]
PARTS.append(_parts.registry_part("U1", MCU_ID, "ESP32-S3-WROOM-1-N8", _USED, "mcu", nc=_NC))
PARTS.append(_parts.registry_part("J1", HDR_ID, "3V3 IN", {1: "3V3", 2: "GND"}, "power", nc=[3, 4, 5, 6, 7, 8]))
PARTS.append(_parts.registry_part("R3", R_ID, "10k", {1: "3V3", 2: "EN"}, "boot"))
PARTS.append(_parts.registry_part("C5", C_ID, "1uF", {1: "EN", 2: "GND"}, "boot"))
PARTS.append(_parts.registry_part("SW2", SW_ID, "RESET", {1: "EN", 2: "GND"}, "boot"))
PARTS.append(_parts.registry_part("R4", R_ID, "10k", {1: "3V3", 2: "BOOT"}, "boot"))
PARTS.append(_parts.registry_part("SW1", SW_ID, "BOOT", {1: "BOOT", 2: "GND"}, "boot"))
GROUPS = [("mcu", "ESP32-S3 module"), ("power", "Supply"), ("boot", "Boot and reset")]

POWER_FLAG_NETS = ["3V3", "GND"]
NET_SPEC = {"3V3": {"v": (3.0, 3.6), "i_max": 0.5}, "GND": {"v": 0.0, "i_max": 0.5}}
EXTERNAL = {"J1.1": {"v": (3.0, 3.6), "i": 0.5, "dir": "supply", "why": "fixture supply"},
            "J1.2": {"v": (0.0, 0.0), "dir": "supply", "why": "fixture ground"},
            "SW1": "none", "SW2": "none"}

# Executable requirements R1-R5 from projects/ref-esp32/ARCHITECTURE.md (section 4 boot/EN, 3V3 rail); judged by the `requirements`
# stage. ref-esp32 has no netlist yet, so this synthetic fixture carries them; ref-esp32 can copy them verbatim.
REQUIREMENTS = [
    {"id": "R1", "kind": "path", "from": "3V3", "to": "U1.EN", "through": {"ref": "R3"},
     "text": "EN is pulled up to 3V3 through R3 (10k) so the module boots without the reset button"},
    {"id": "R2", "kind": "path", "from": "U1.EN", "to": "GND", "with": {"SW2": "on"}, "through": {"ref": "SW2"},
     "text": "Pressing RESET (SW2) pulls EN to GND"},
    {"id": "R3", "kind": "path", "from": "3V3", "to": "U1.27", "through": {"ref": "R4"},
     "text": "GPIO0 (BOOT, pin 27) is pulled up to 3V3 through R4 so the default boot is from flash"},
    {"id": "R4", "kind": "path_absent", "from": "U1.27", "to": "GND",
     "text": "GPIO0 has no hard path to GND while BOOT (SW1) is released (no strap cap or resistor to ground)"},
    {"id": "R5", "kind": "net_v", "net": "3V3", "min": 3.0, "max": 3.6,
     "text": "The 3V3 rail stays inside the module's 3.0-3.6 V operating range"},
]
