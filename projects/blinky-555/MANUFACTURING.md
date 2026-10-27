# blinky-555 - manufacturing details

_Generated 2026-09-18 15:36 by `tools/boardgen/make_fab_report.py` from `blinky-555.kicad_pcb` - measured from the real board and drill file, not copied from other docs. Regenerate after any board change: `python pipeline.py blinky-555 --only fabreport`._

## Quick answers (what a PCB price calculator asks)

| Question | Answer |
|---|---|
| Width | **7 cm** (70 mm) |
| Height | **4.5 cm** (45 mm) |
| Layers | **2** (copper on: F.Cu, B.Cu) |
| Can it be made single-sided (one layer)? | **No** - it has copper on 2 layers, 159 vias. A one-layer fab can't make it without a redesign. |
| Solder mask | **Yes, both sides** (colour not set in design - green is the cheap default) |
| Silkscreen | Yes, top only (white) |
| Board thickness | 1.6 mm |
| Copper weight | 1 oz (35 um outer) |
| Surface finish | not set in design - **HASL lead-free** is the cheap default and fine for hand soldering |
| Material | FR-4 (KiCad default) |
| Board area | 31.5 cm² (outline rectangle) |
| Total holes to drill | 187 (28 component/mounting + 159 vias) |
| Components | 9 (9 through-hole, 0 SMD) + 4 mechanical (mounting holes etc.) |
| Assembly needed from the fab? | No - all through-hole, hand solderable |

## Board outline

| | |
|---|---|
| Size | 70 x 45 mm |
| Area | 3150 mm² |
| Shape | rectangle, drawn with 4 lines |
| Perimeter (routing length) | 230 mm |
| Separate boards / internal cut-outs | 1 / 0 |
| Outline closed | yes |

## Layers (size and thickness of each)

Every layer covers the full board outline (70 x 45 mm).

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
| F.Cu | 7 | 57.36 mm | 0.2 mm | 1 | 2862.13 mm² (90.86% of board) | 28 |
| B.Cu | 15 | 118.25 mm | 0.2 mm | 1 | 2825.14 mm² (89.69% of board) | 28 |

Silkscreen: 26 text items (smallest 0.9 mm high), 183 lines/shapes (thinnest 0.12 mm).

## Holes

From the design (187 holes in total):

| Diameter (mm) | Plated? | Shape | Count |
|---|---|---|---|
| 0.8 | yes (PTH) | round | 20 |
| 0.9 | yes (PTH) | round | 2 |
| 1.3 | yes (PTH) | round | 2 |
| 3.2 | no (NPTH) | round | 4 |
| 0.4 | yes (via, 0.8 mm pad) | round | 159 |

- Plated pads: 24 through-hole, 0 SMD; non-plated holes: 4; slots: 0
- Smallest hole 0.4 mm, largest 3.2 mm

Cross-check against the drill file the fab receives, `out/fab/gerbers/blinky-555.drl`: **187 holes**, matches the design.

| Tool | Diameter (mm) | Plating | Holes | Slots |
|---|---|---|---|---|
| T1 | 0.4 | Plated | 159 | 0 |
| T2 | 0.8 | Plated | 20 | 0 |
| T3 | 0.9 | Plated | 2 | 0 |
| T4 | 1.3 | Plated | 2 | 0 |
| T5 | 3.2 | NonPlated | 4 | 0 |

## Tightest geometry vs. typical fab limits

Limits are typical JLCPCB standard 2-layer values - confirm on the fab's capabilities page before ordering.

| Item | This board | Typical limit | |
|---|---|---|---|
| Thinnest track | 0.2 mm | >= 0.127 mm | OK |
| Copper clearance (DRC rule, enforced) | 0.2 mm | >= 0.127 mm | OK |
| Smallest plated hole | 0.4 mm | >= 0.3 mm | OK |
| Smallest non-plated hole | 3.2 mm | >= 0.5 mm | OK |
| Largest hole | 3.2 mm | <= 6.3 mm | OK |
| Smallest via drill | 0.4 mm | >= 0.3 mm | OK |
| Smallest annular ring | 0.2 mm | >= 0.13 mm | OK |
| Closest two holes (edge to edge, measured) | 0.893 mm | >= 0.5 mm | OK |
| Copper to board edge (DRC rule) | 0.5 mm | >= 0.3 mm | OK |
| Smallest silkscreen text | 0.9 mm | >= 1 mm | **CHECK** |
| Thinnest silkscreen line | 0.12 mm | >= 0.153 mm | **CHECK** |

Closest two holes: H3 hole (103.50, 91.00) and via on GND (106.00, 92.00).

How to read a **CHECK**: a copper or hole row is a real risk - fix it or ask the fab. A *silkscreen* row is cosmetic: the fab still prints it, just fainter or blurrier (KiCad's own footprint outlines are 0.12 mm, so nearly every KiCad board shows that one). A *DRC rule* row only means the rule would allow something tighter than the fab; the measured rows show what the board really uses.

## Components

| | Count |
|---|---|
| Parts to place | 9 |
| Through-hole / SMD | 9 / 0 |
| On top / on bottom | 9 / 0 |
| Mechanical (mounting holes, logos) | 4 |
| Solder joints | 24 |
| Unique part types (BOM lines) | 9 |
| Do-not-populate | 0 |
| Nets | 7 |

| Qty | Value | Footprint | Type | Side | References |
|---|---|---|---|---|---|
| 1 | 10uF | CP_Radial_D6.3mm_P2.50mm | THT | top | C1 |
| 1 | 10nF | C_Disc_D5.0mm_W2.5mm_P5.00mm | THT | top | C2 |
| 1 | 100nF | C_Disc_D5.0mm_W2.5mm_P5.00mm | THT | top | C3 |
| 1 | RED | LED_D5.0mm | THT | top | D1 |
| 1 | 9-12V IN | TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm | THT | top | J1 |
| 1 | 10k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R1 |
| 1 | 47k | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R2 |
| 1 | 470R | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R3 |
| 1 | NE555P | DIP-8_W7.62mm | THT | top | U1 |

Mechanical: H1 (MountingHole_3.2mm_M3), H2 (MountingHole_3.2mm_M3), H3 (MountingHole_3.2mm_M3), H4 (MountingHole_3.2mm_M3).

## Design check status

| Check | Result |
|---|---|
| DRC errors | **0** |
| DRC warnings | 3 |
| Unconnected items | 0 |
| Schematic vs board differences | 0 |

## Order form (JLCPCB-style) - suggested answers

| Field | Answer |
|---|---|
| Base material | FR-4 |
| Layers | 2 |
| Dimensions | 70 x 45 mm |
| PCB quantity | your choice (5 is the usual minimum) |
| Different designs | 1 |
| Delivery format | single PCB |
| PCB thickness | 1.6 mm |
| PCB colour | Green (cheapest, fastest) |
| Silkscreen | White |
| Surface finish | HASL (with lead) or LeadFree HASL |
| Outer copper weight | 1 oz |
| Via covering | Tented |
| Min via hole size / diameter | 0.4 / 0.8 mm |
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
| `out/fab/blinky-555_gerbers_JLCPCB.zip` | 48.12 KB | **upload this** - gerbers + drill |
| `out/fab/positions_raw.csv` | 0.04 KB | raw placement data (not needed for bare boards) |
