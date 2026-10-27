# uno-toggle - manufacturing details

_Generated 2026-10-27 23:34 by `tools/boardgen/make_fab_report.py` from `uno-toggle.kicad_pcb` - measured from the real board and drill file, not copied from other docs. Regenerate after any board change: `python pipeline.py uno-toggle --only fabreport`._

## Quick answers (what a PCB price calculator asks)

| Question | Answer |
|---|---|
| Width | **6.86 cm** (68.58 mm) |
| Height | **5.33 cm** (53.34 mm) |
| Layers | **2** (copper on: F.Cu, B.Cu) |
| Can it be made single-sided (one layer)? | **No** - it has copper on 2 layers, 166 vias. A one-layer fab can't make it without a redesign. |
| Solder mask | **Yes, both sides** (colour not set in design - green is the cheap default) |
| Silkscreen | Yes, top only (white) |
| Board thickness | 1.6 mm |
| Copper weight | 1 oz (35 um outer) |
| Surface finish | not set in design - **HASL lead-free** is the cheap default and fine for hand soldering |
| Material | FR-4 (KiCad default) |
| Board area | 36.15 cm² (outline custom shape) |
| Total holes to drill | 228 (62 component/mounting + 166 vias) |
| Components | 9 (9 through-hole, 0 SMD) + 0 mechanical (mounting holes etc.) |
| Assembly needed from the fab? | No - all through-hole, hand solderable |

## Board outline

| | |
|---|---|
| Size | 68.58 x 53.34 mm |
| Area | 3614.96 mm² |
| Shape | custom outline, drawn with 9 lines |
| Perimeter (routing length) | 239.97 mm |
| Separate boards / internal cut-outs | 1 / 0 |
| Outline closed | yes |

## Layers (size and thickness of each)

Every layer covers the full board outline (68.58 x 53.34 mm).

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
| F.Cu | 6 | 42.79 mm | 0.3 mm | 1 | 3187.33 mm² (88.17% of board) | 62 |
| B.Cu | 22 | 132.94 mm | 0.3 mm | 1 | 3121.72 mm² (86.36% of board) | 62 |

Silkscreen: 27 text items (smallest 0.8 mm high), 34 lines/shapes (thinnest 0.12 mm).

## Holes

From the design (228 holes in total):

| Diameter (mm) | Plated? | Shape | Count |
|---|---|---|---|
| 0.8 | yes (PTH) | round | 8 |
| 0.9 | yes (PTH) | round | 4 |
| 1.02 | yes (PTH) | round | 38 |
| 1.1 | yes (PTH) | round | 8 |
| 3.2 | no (NPTH) | round | 4 |
| 0.4 | yes (via, 0.8 mm pad) | round | 166 |

- Plated pads: 58 through-hole, 0 SMD; non-plated holes: 4; slots: 0
- Smallest hole 0.4 mm, largest 3.2 mm

Cross-check against the drill file the fab receives, `out/fab/gerbers/uno-toggle.drl`: **228 holes**, matches the design.

| Tool | Diameter (mm) | Plating | Holes | Slots |
|---|---|---|---|---|
| T1 | 0.4 | Plated | 166 | 0 |
| T2 | 0.8 | Plated | 8 | 0 |
| T3 | 0.9 | Plated | 4 | 0 |
| T4 | 1.02 | Plated | 38 | 0 |
| T5 | 1.1 | Plated | 8 | 0 |
| T6 | 3.2 | NonPlated | 4 | 0 |

## Tightest geometry vs. typical fab limits

Limits are typical JLCPCB standard 2-layer values - confirm on the fab's capabilities page before ordering.

| Item | This board | Typical limit | |
|---|---|---|---|
| Thinnest track | 0.3 mm | >= 0.127 mm | OK |
| Copper clearance (DRC rule, enforced) | 0.2 mm | >= 0.127 mm | OK |
| Smallest plated hole | 0.4 mm | >= 0.3 mm | OK |
| Smallest non-plated hole | 3.2 mm | >= 0.5 mm | OK |
| Largest hole | 3.2 mm | <= 6.3 mm | OK |
| Smallest via drill | 0.4 mm | >= 0.3 mm | OK |
| Smallest annular ring | 0.2 mm | >= 0.13 mm | OK |
| Closest two holes (edge to edge, measured) | 0.51 mm | >= 0.45 mm | OK |
| Copper to board edge (DRC rule) | 0.5 mm | >= 0.3 mm | OK |
| Smallest silkscreen text | 0.8 mm | >= 1 mm | advisory |
| Thinnest silkscreen line | 0.12 mm | >= 0.153 mm | advisory |

Closest two holes: A1 pad GND2 (140.64, 100.80) and via on GND (141.83, 101.05).

## Current-carrying nets (copper 1 oz, temp rise 10 C, IPC-2221 external layer)

No net needs more than the default 0.15 mm track (NET_SPEC i_max).

How to read a **CHECK**: a copper or hole row is a real risk - fix it or ask the fab (the fabreport stage exits 1 while any is left). A *silkscreen* row is marked *advisory* instead: it is cosmetic, the fab still prints it, just fainter or blurrier (KiCad's own footprint outlines are 0.12 mm, so nearly every KiCad board shows that one). A *DRC rule* row only means the rule would allow something tighter than the fab; the measured rows show what the board really uses.

## Components

| | Count |
|---|---|
| Parts to place | 9 |
| Through-hole / SMD | 9 / 0 |
| On top / on bottom | 9 / 0 |
| Mechanical (mounting holes, logos) | 0 |
| Solder joints | 58 |
| Unique part types (BOM lines) | 7 |
| Do-not-populate | 0 |
| Nets | 37 |

| Qty | Value | Footprint | Type | Side | References |
|---|---|---|---|---|---|
| 1 | Arduino Uno R3 | Arduino_Uno_R3_Shield | THT | top | A1 |
| 2 | 100nF | C_Disc_D5.0mm_W2.5mm_P5.00mm | THT | top | C1, C2 |
| 1 | RED | LED_D5.0mm | THT | top | D1 |
| 1 | GREEN | LED_D5.0mm | THT | top | D2 |
| 2 | 330R | R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal | THT | top | R1, R2 |
| 1 | BTN1 | SW_PUSH_6mm | THT | top | SW1 |
| 1 | BTN2 | SW_PUSH_6mm | THT | top | SW2 |

## Design check status

| Check | Result |
|---|---|
| DRC errors | **0** |
| DRC warnings | 14 |
| Unconnected items | 0 |
| Schematic vs board differences | 0 |

## Order form (JLCPCB-style) - suggested answers

| Field | Answer |
|---|---|
| Base material | FR-4 |
| Layers | 2 |
| Dimensions | 68.58 x 53.34 mm |
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
| `out/fab/positions_raw.csv` | 0.04 KB | raw placement data (not needed for bare boards) |
| `out/fab/uno-toggle_gerbers_JLCPCB.zip` | 74.82 KB | **upload this** - gerbers + drill |
