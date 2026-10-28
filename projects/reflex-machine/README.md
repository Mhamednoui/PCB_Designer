# Reflex Machine PCB - start here


**Ordering it:** everything a fab or price calculator asks (size in cm, layers, holes, parts, order-form answers) is in [`MANUFACTURING.md`](MANUFACTURING.md) - generated from the real board, regenerate with `python pipeline.py reflex-machine --only fabreport`.
**Checking the wiring without reading a PCB:** [`CONNECTIONS.md`](CONNECTIONS.md) lists every pin of every part and where it goes, in words.

10-electromagnet reflex/whack-a-mole game controller. Arduino Mega 2560 (shield-mounted) +
ESP32 DevKit V1, all through-hole parts. This file tells you which other file to open next -
don't read everything.

| I want to... | Read |
|---|---|
| Know what's done, what's pending, and open questions | `HANDOVER.md` |
| See the full build history and how it was made | `PROJECT_LOG.md` |
| See the original spec and design decisions | `DESIGN_BRIEF.md` |
| Wire up the physical machine | `WIRING_GUIDE.md` |
| Regenerate or change the board (schematic/PCB scripts) | `gen/` - see `docs/NEW_BOARD_PLAYBOOK.md` in the workspace root |
| Test the design before/after fabrication | `test/README.md` |

## Status (2026-09-17)
Board is **done and verified**: 160x125mm, 2-layer, ERC clean, DRC 0 errors/0 unconnected/0 parity.
Fab files in `out/fab/`, docs+renders+STEP in `out/docs/`.

A pre-fabrication **testing pipeline** is in progress (see `test/README.md`):
1. Electrical check on the real PCB file (DRC/ERC, power/signal integrity, per-magnet trace current) - **done, pass**.
2. SPICE simulation of the analog subcircuits (debounce filters, coin optocoupler, level-shifter) - **done**,
   via LTspice - 9/9 filters confirmed within 0.3% of calculated values. See `test/spice/REPORT.md`.
3. Functional/logic simulation (Wokwi) - **input wiring confirmed** (S1/S2/S3/RST/coin each pull the
   correct Mega pin, verified with a real scripted scenario against the real firmware). Full game-round
   logic not yet checked (costs simulation minutes). See `test/wokwi/README.md` and `test/wokwi/USAGE_LOG.md`.
4. Physical bring-up self-test - **ready** (`test/bringup/`), usable once the board is manufactured.

Open questions for the user: real magnet current/coil resistance (now step 3 of the bring-up checklist),
ESP32 row pitch (25.4mm assumed).

## Folder layout
```
reflex-machine.kicad_sch / .kicad_pcb   the design (open in KiCad)
HANDOVER.md          current state, pending decisions - read first
PROJECT_LOG.md        full build history, part-by-part
DESIGN_BRIEF.md       spec + decisions made before designing
WIRING_GUIDE.md        user-facing wiring instructions
gen/                  scripts that generate the schematic/PCB from netlist.py (source of truth)
sim/                  PlatformIO projects to build real firmware.hex for the Mega/ESP32
test/                 pre-fabrication testing pipeline (see test/README.md)
analysis/             cached kicad-happy analyzer output
out/fab/              gerbers, BOM, CPL for JLCPCB
out/docs/             STEP, schematic PDF, renders, full BOM
```

## Known deviation from the brief: reverse-polarity protection
DESIGN_BRIEF (section on the 12 V input) promised a P-MOSFET reverse-polarity stage. The board as built has none.
The protection is the P6KE15A TVS (D1) across `+12V` behind the 10 A blade fuse F1: a reversed supply forward-biases D1
and blows the fuse (a crowbar). That is cheaper and survives, but it destroys a fuse on every wrong-way connection and
the 10 A fuse is slow against a 1.5 A-per-channel load. Found by EL-CONN-PROT (P2-T7); not changed.

## Known limit: total magnet current (EL-BUDGET, waived until 2027-04-30)
All 10 coils on at their 1.5 A design figure is 15 A on `+12V`, over the 10 A fuse F1 and the 10 A copper rating.
DESIGN_BRIEF B2 sizes the board for 10 A TOTAL; an overload blows F1 before the copper is stressed (fails safe).
Firmware PWM_ON=100/255 averages ~5.9 A with all on, but it is runtime-settable, so it is not relied on.
Measure the real coil current at bring-up (step 3) and re-judge; the waiver is in `waivers.json`.
