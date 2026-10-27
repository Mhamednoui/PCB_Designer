# reflex-machine - manufacturing details

_Generated 2026-09-18 15:36 by `tools/boardgen/make_fab_report.py` from `reflex-machine.kicad_pcb` - measured from the real board and drill file, not copied from other docs. Regenerate after any board change: `python pipeline.py reflex-machine --only fabreport`._

## Quick answers (what a PCB price calculator asks)

| Question | Answer |
|---|---|
| Width | **16 cm** (160 mm) |
| Height | **12.5 cm** (125 mm) |
| Layers | **2** (copper on: F.Cu, B.Cu) |
| Can it be made single-sided (one layer)? | **No** - it has copper on 2 layers, 229 vias. A one-layer fab can't make it without a redesign. |
| Solder mask | **Yes, both sides** (colour not set in design - green is the cheap default) |
| Silkscreen | Yes, top only (white) |
| Board thickness | 1.6 mm |
| Copper weight | 1 oz (35 um outer) |
| Surface finish | not set in design - **HASL lead-free** is the cheap default and fine for hand soldering |
| Material | FR-4 (KiCad default) |
| Board area | 200 cm² (outline rectangle) |
| Total holes to drill | 671 (442 component/mounting + 229 vias) |
| Components | 123 (123 through-hole, 0 SMD) + 2 mechanical (mounting holes etc.) |
| Assembly needed from the fab? | No - all through-hole, hand solderable |

## Board outline

| | |
|---|---|
| Size | 160 x 125 mm |
| Area | 20000 mm² |
| Shape | rectangle, drawn with 4 lines |
| Perimeter (routing length) | 570 mm |
| Separate boards / internal cut-outs | 1 / 0 |
| Outline closed | yes |

## Layers (size and thickness of each)

Every layer covers the full board outline (160 x 125 mm).

No stackup is defined in the design, so KiCad's standard 2-layer build applies:

| Layer | Type | Thickness |
|---|---|---|
| F.Silkscreen | top legend | - |
| F.Mask | top solder mask | ~0.01 mm |
| F.Cu | copper | 0.035 mm (1 oz) |
| core | FR-4 dielectric | 1.51 mm |
| B.Cu | copper | 0.035 mm (1 oz) |
| B.Mask | bottom solder mask | ~0.01 mm |
| B.Silkscreen | bottom legend | - |
| **Total** | | **1.6 mm** |

What is on each copper layer:

| Copper layer | Tracks | Track length | Track widths used | Pour zones | Poured area | Pads |
|---|---|---|---|---|---|---|
| F.Cu | 458 | 2528.74 mm | 0.3 mm, 0.8 mm, 1.5 mm, 2.5 mm | 2 | 14242.71 mm² (71.21% of board) | 442 |
| B.Cu | 583 | 3108.41 mm | 0.3 mm, 0.4 mm, 0.5 mm, 0.8 mm, 1.5 mm | 1 | 14157.42 mm² (70.79% of board) | 442 |

Silkscreen: 292 text items (smallest 0.7 mm high), 1030 lines/shapes (thinnest 0.12 mm).

## Holes

From the design (671 holes in total):

| Diameter (mm) | Plated? | Shape | Count |
|---|---|---|---|
| 0.8 | yes (PTH) | round | 150 |
| 0.9 | yes (PTH) | round | 24 |
| 1 | yes (PTH) | round | 60 |
| 1.02 | yes (PTH) | round | 92 |
| 1.1 | yes (PTH) | round | 32 |
| 1.2 | yes (PTH) | round | 32 |
| 1.3 | yes (PTH) | round | 22 |
| 1.6 | yes (PTH) | round | 20 |
| 1.78 | yes (PTH) | round | 4 |
| 3.2 | no (NPTH) | round | 6 |
| 0.3 | yes (via, 0.6 mm pad) | round | 25 |
| 0.4 | yes (via, 0.8 mm pad) | round | 204 |

- Plated pads: 436 through-hole, 0 SMD; non-plated holes: 6; slots: 0
- Smallest hole 0.3 mm, largest 3.2 mm

Cross-check against the drill file the fab receives, `out/fab/gerbers/reflex-machine.drl`: **671 holes**, matches the design.

| Tool | Diameter (mm) | Plating | Holes | Slots |
|---|---|---|---|---|
| T1 | 0.3 | Plated | 25 | 0 |
| T2 | 0.4 | Plated | 204 | 0 |
| T3 | 0.8 | Plated | 150 | 0 |
| T4 | 0.9 | Plated | 24 | 0 |
| T5 | 1 | Plated | 60 | 0 |
| T6 | 1.02 | Plated | 92 | 0 |
| T7 | 1.1 | Plated | 32 | 0 |
| T8 | 1.2 | Plated | 32 | 0 |
| T9 | 1.3 | Plated | 22 | 0 |
| T10 | 1.6 | Plated | 20 | 0 |
| T11 | 1.78 | Plated | 4 | 0 |
| T12 | 3.2 | NonPlated | 6 | 0 |

## Tightest geometry vs. typical fab limits

Limits are typical JLCPCB standard 2-layer values - confirm on the fab's capabilities page before ordering.

| Item | This board | Typical limit | |
|---|---|---|---|
| Thinnest track | 0.3 mm | >= 0.127 mm | OK |
| Copper clearance (DRC rule, enforced) | 0.2 mm | >= 0.127 mm | OK |
| Smallest plated hole | 0.3 mm | >= 0.3 mm | OK |
| Smallest non-plated hole | 3.2 mm | >= 0.5 mm | OK |
| Largest hole | 3.2 mm | <= 6.3 mm | OK |
| Smallest via drill | 0.3 mm | >= 0.3 mm | OK |
| Smallest annular ring | 0.15 mm | >= 0.13 mm | OK |
| Closest two holes (edge to edge, measured) | 0.489 mm | >= 0.5 mm | **CHECK** |
| Copper to board edge (DRC rule) | 0.5 mm | >= 0.3 mm | OK |
| Smallest silkscreen text | 0.7 mm | >= 1 mm | **CHECK** |
| Thinnest silkscreen line | 0.12 mm | >= 0.153 mm | **CHECK** |

Closest two holes: via on GND (126.00, 152.00) and A1 pad GND3 (127.18, 151.80).

How to read a **CHECK**: a copper or hole row is a real risk - fix it or ask the fab. A *silkscreen* row is cosmetic: the fab still prints it, just fainter or blurrier (KiCad's own footprint outlines are 0.12 mm, so nearly every KiCad board shows that one). A *DRC rule* row only means the rule would allow something tighter than the fab; the measured rows show what the board really uses.

## Components

| | Count |
|---|---|
| Parts to place | 123 |
| Through-hole / SMD | 123 / 0 |
| On top / on bottom | 123 / 0 |
| Mechanical (mounting holes, logos) | 2 |
| Solder joints | 436 |
| Unique part types (BOM lines) | 41 |
| Do-not-populate | 0 |
| Nets | 172 |

| Qty | Value | Footprint | Type | Side | References |
|---|---|---|---|---|---|
| 1 | Arduino Mega 2560 R3 | Arduino_Mega2560_R3_Shield | THT | top | A1 |
| 1 | ESP32 DevKit V1 (30 pin) | ESP32_DevKit_V1_30pin_Socket | THT | top | A2 |
| 1 | 1000uF 25V | CP_Radial_D10.0mm_P5.00mm | THT | top | C1 |
| 2 | 220uF 25V | CP_Radial_D6.3mm_P2.50mm | THT | top | C2, C6 |
| 7 | 100nF | C_Disc_D5.0mm_W2.5mm_P5.00mm | THT | top | C3, C7, C9, C10, C11, C12, C13 |
| 1 | 1nF | C_Disc_D5.0mm_W2.5mm_P5.00mm | THT | top | C8 |
| 1 | P6KE15A | D_DO-15_P10.16mm_Horizontal | THT | top | D1 |
| 1 | 1N4007 | D_DO-41_SOD81_P7.62mm_Horizontal | THT | top | D2 |
| 2 | GREEN | LED_D5.0mm | THT | top | D3, D4 |
| 10 | 1N5822 | D_DO-201AD_P5.08mm_Vertical_CathodeUp | THT | top | D11, D12, D13, D14, D15, D16, D17, D18, D19, D20 |
| 10 | RED | LED_D3.0mm | THT | top | D21, D22, D23, D24, D25, D26, D27, D28, D29, D30 |
| 1 | 10A mini blade | Fuseholder_Blade_Mini_Keystone_3568 | THT | top | F1 |
| 1 | 12V_IN | TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J1 |
| 1 | MAG1 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J2 |
| 1 | MAG2 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J3 |
| 1 | MAG3 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J4 |
| 1 | MAG4 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J5 |
| 1 | MAG5 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J6 |
| 1 | MAG6 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J7 |
| 1 | MAG7 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J8 |
| 1 | MAG8 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J9 |
| 1 | MAG9 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J10 |
| 1 | MAG10 | TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal | THT | top | J11 |
| 1 | COIN | TerminalBlock_Phoenix_PT-1,5-3-3.5-H_1x03_P3.50mm_Horizontal | THT | top | J12 |
| 1 | BUTTONS | TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal | THT | top | J13 |
| 1 | STATUS_LEDS | TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal | THT | top | J14 |
| 1 | 7SEG | TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal | THT | top | J15 |
| 1 | MEGA SPARE | PinHeader_2x10_P2.54mm_Vertical | THT | top | J16 |
| 1 | ESP32 SPARE | PinHeader_2x04_P2.54mm_Vertical | THT | top | J17 |
| 10 | IRLZ44N | TO-220-3_Vertical | THT | top | Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10 |
| 1 | 4.7k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R1 |
| 6 | 1k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R2, R43, R44, R45, R46, R62 |
| 10 | 100R | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R11, R12, R13, R14, R15, R16, R17, R18, R19, R20 |
| 15 | 10k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R21, R22, R23, R24, R25, R26, R27, R28, R29, R30, R42, R47, R48, R49, R50 |
| 11 | 2.2k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R31, R32, R33, R34, R35, R36, R37, R38, R39, R40, R41 |
| 4 | 330R | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R51, R52, R53, R54 |
| 7 | 470R | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R55, R56, R57, R58, R59, R60, R61 |
| 1 | 2k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R63 |
| 1 | 5V 2A module (K7805-2000R3) | Converter_DCDC_RECOM_R-78B-2.0_THT | THT | top | U1 |
| 1 | PC817 | DIP-4_W7.62mm | THT | top | U2 |
| 1 | 74HC595N | DIP-16_W7.62mm | THT | top | U3 |

Mechanical: H1 (MountingHole_3.2mm_M3), H2 (MountingHole_3.2mm_M3).

## Design check status

| Check | Result |
|---|---|
| DRC errors | **0** |
| DRC warnings | 213 |
| Unconnected items | 0 |
| Schematic vs board differences | 0 |

## Order form (JLCPCB-style) - suggested answers

| Field | Answer |
|---|---|
| Base material | FR-4 |
| Layers | 2 |
| Dimensions | 160 x 125 mm |
| PCB quantity | your choice (5 is the usual minimum) |
| Different designs | 1 |
| Delivery format | single PCB |
| PCB thickness | 1.6 mm |
| PCB colour | Green (cheapest, fastest) |
| Silkscreen | White |
| Surface finish | HASL (with lead) or LeadFree HASL |
| Outer copper weight | 1 oz |
| Via covering | Tented |
| Min via hole size / diameter | 0.3 / 0.6 mm |
| Board outline tolerance | ±0.2 mm (regular) |
| Castellated holes | No |
| Edge plating | No |
| Gold fingers | No |
| Impedance control | No |
| Remove order number | No = fab prints a small order code somewhere; 'Specify a location' = add the text JLCJLCJLCJLC to the silkscreen where you want it; Yes = extra cost |
| PCB assembly | No - all through-hole, solder yourself |

## Files to send

| File | Size | Use |
|---|---|---|
| `out/fab/BOM_JLCPCB.csv` | 0.04 KB | assembly only |
| `out/fab/CPL_JLCPCB.csv` | 0.04 KB | assembly only |
| `out/fab/positions_raw.csv` | 0.04 KB | raw placement data (not needed for bare boards) |
| `out/fab/reflex-machine_gerbers_JLCPCB.zip` | 441.88 KB | **upload this** - gerbers + drill |
