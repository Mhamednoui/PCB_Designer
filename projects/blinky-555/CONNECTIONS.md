# blinky-555 - every connection, in plain words

_Generated 2026-10-28 04:00 by `tools/boardgen/make_connections.py` from the real board copper (`blinky-555.kicad_pcb`), with pin names from the schematic. Regenerate: `python pipeline.py blinky-555 --only connections`._

## How to use this file

You don't need to read the PCB. Each part below lists its pins and where each pin's copper goes.

1. Start with **Check these first** - parts where a wrong pin order would really matter.
2. For each, open the datasheet picture (or look at your real part) and confirm the pin names match: e.g. a MOSFET's pin 1 really is G (gate).
3. When the board arrives, use a multimeter in beep mode: two pins listed as connected must beep.
   Two pins that are NOT listed together must not beep.

## Automatic cross-check

Every pin on the board copper goes to the same net as in the schematic: **24 pins checked, 0 differences.**

## Check these next - transistors, ICs, modules

### U1 - NE555P

IC / module · footprint `Package_DIP:DIP-8_W7.62mm` · Precision Timers, 555 compatible, PDIP-8

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | GND | **GND** → C1 pin 2, C2 pin 2, C3 pin 2, D1 pin 1 (K), J1 pin 2 (Pin 2) |
| 2 | TRIG | **TRIG** → C1 pin 1, R2 pin 2, U1 pin 6 (THRES) |
| 3 | OUT | **OUT** → R3 pin 1 |
| 4 | RST (active-low) | **VCC** → C3 pin 1, J1 pin 1 (Pin 1), R1 pin 1, U1 pin 8 (VCC) |
| 5 | CONT | **CONT** → C2 pin 1 |
| 6 | THRES | **TRIG** → C1 pin 1, R2 pin 2, U1 pin 2 (TRIG) |
| 7 | DISCH | **DISCH** → R1 pin 2, R2 pin 1 |
| 8 | VCC | **VCC** → C3 pin 1, J1 pin 1 (Pin 1), R1 pin 1, U1 pin 4 (RST (active-low)) |

## Everything else

### C1 - 10uF

capacitor · footprint `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` · Polarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **TRIG** → R2 pin 2, U1 pin 2 (TRIG), U1 pin 6 (THRES) |
| 2 |  | **GND** → C2 pin 2, C3 pin 2, D1 pin 1 (K), J1 pin 2 (Pin 2), U1 pin 1 (GND) |

### C2 - 10nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **CONT** → U1 pin 5 (CONT) |
| 2 |  | **GND** → C1 pin 2, C3 pin 2, D1 pin 1 (K), J1 pin 2 (Pin 2), U1 pin 1 (GND) |

### C3 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **VCC** → J1 pin 1 (Pin 1), R1 pin 1, U1 pin 4 (RST (active-low)), U1 pin 8 (VCC) |
| 2 |  | **GND** → C1 pin 2, C2 pin 2, D1 pin 1 (K), J1 pin 2 (Pin 2), U1 pin 1 (GND) |

### D1 - RED

diode / LED · footprint `LED_THT:LED_D5.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **GND** → C1 pin 2, C2 pin 2, C3 pin 2, J1 pin 2 (Pin 2), U1 pin 1 (GND) |
| 2 | A | **LED_A** → R3 pin 2 |

### J1 - 9-12V IN

connector / terminal · footprint `TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm` · Generic connector, single row, 01x02, script generated

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **VCC** → C3 pin 1, R1 pin 1, U1 pin 4 (RST (active-low)), U1 pin 8 (VCC) |
| 2 | Pin 2 | **GND** → C1 pin 2, C2 pin 2, C3 pin 2, D1 pin 1 (K), U1 pin 1 (GND) |

### R1 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **VCC** → C3 pin 1, J1 pin 1 (Pin 1), U1 pin 4 (RST (active-low)), U1 pin 8 (VCC) |
| 2 |  | **DISCH** → R2 pin 1, U1 pin 7 (DISCH) |

### R2 - 47k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **DISCH** → R1 pin 2, U1 pin 7 (DISCH) |
| 2 |  | **TRIG** → C1 pin 1, U1 pin 2 (TRIG), U1 pin 6 (THRES) |

### R3 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **OUT** → U1 pin 3 (OUT) |
| 2 |  | **LED_A** → D1 pin 2 (A) |
