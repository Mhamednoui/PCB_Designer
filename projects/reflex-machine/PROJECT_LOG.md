# Project log - what we did, step by step

Written for: you (the board owner), as a record of this whole session.
Date: 2026-09-11. Everything lives in `C:\Users\nouir\PCB`.

---

## Part 1 - Setting up the tools

You installed KiCad 10.0.6. I searched for the best free tools around it and set them up in this folder:

| What | Why | Where |
|---|---|---|
| KiCad MCP server (Seeed) | lets me read your schematics/boards and run KiCad's checks | `.mcp.json` |
| 11 kicad-happy skills | design review, EMC, simulation, BOM, datasheets, JLCPCB/PCBWay/LCSC ordering | `.claude/skills/` |
| Konnect (downloaded) | AI plugin for KiCad - **you still need to install it** | `downloads/` |
| Freerouting 2.4.1 | automatic routing; I extracted it without installing | `tools/freerouting/` |
| Python tools | `easyeda2kicad` (import JLCPCB parts), `KiKit`, `SKiDL`, `kicad-skip` | `.venv/`, KiCad's Python |
| Source code of 10 projects | reference material | `tools/` |

Notes in `CLAUDE.md` (project memory) and `README.md` (your cheat sheet).

## Part 2 - Understanding your machine

I read both your programs in `CODES/` and pulled out the complete pin map:
10 magnets on pins 3,5,6,7,8,9,10,11,12,44 · coin acceptor on pin 2 · buttons on 22/24/26/28 ·
7-segment through a 74HC595 on A0/A1/A2 · 4 status LEDs on A3-A6 · Mega↔ESP32 serial on 18/19 ↔ GPIO16/17.

I wrote everything I needed into `projects/reflex-machine/DESIGN_BRIEF.md` and asked you questions before
designing. Your answers: one 12V 16A supply for everything, 10 electromagnets with IRLZ MOSFETs and diodes,
your own resistor divider on the serial line, standard Mega + ESP32 DevKit V1, small DIY LEDs, 5V 7-segment,
compact board with comfortable spacing.

**Three hardware problems I found in your existing setup:**
1. The Mega's 5V TX line reaches the ESP32, which only takes 3.3V - your divider handles it, and the board now
   has that divider built in.
2. The "false coin when a button is pressed" noise in your code comments is a wiring problem. The board fixes it
   with an optocoupler, input filters and separate ground paths.
3. PWM-held magnets need MOSFETs with flyback diodes - relays cannot do this.

## Part 3 - The board

**What it is:** a 118 × 108 mm, 2-layer board that plugs on top of the Arduino Mega like a shield.
The ESP32 plugs into sockets on top, with its antenna hanging over the board edge.

**On the board:** 12V input with fuse, surge protection and reverse protection · 12V→5V regulator for both
controllers · 10 MOSFET magnet drivers, each with flyback diode and an ON indicator LED · optocoupler coin input ·
filtered button inputs · LED resistors · the 74HC595 with segment resistors · the serial divider · a spare header.

**Every wire connects to a labelled screw terminal:** 12V IN, M1-M10, COIN, BUTTONS, STATUS LEDS, 7-SEGMENT.
Wiring instructions are in `projects/reflex-machine/WIRING_GUIDE.md`.

**Your firmware does not change.** Every pin and the 7-segment bit order match your code exactly.

## Part 4 - How I built it (all by script, no mouse)

1. `gen/netlist.py` - one file listing every part and every connection.
2. `gen/make_sch.py` - generates the schematic; `check_sch.py` exports the netlist back out and compares it to
   step 1, then runs KiCad's electrical check (ERC).
3. `gen/make_pcb.py place` - positions all 127 parts, draws the board outline and silkscreen.
4. `gen/make_pcb.py route` - Freerouting draws the traces (two passes).
5. `gen/make_pcb.py finish` - ground vias, copper pours on both sides, final fill.
6. `gen/make_pcb.py check` - KiCad's design rule check, including schematic↔board comparison.
7. `gen/make_outputs.py` - manufacturing files, 3D model, PDF, renders.

Because it is all scripts, any change can be re-run from scratch in a few minutes.

## Part 5 - Final results

| Check | Result |
|---|---|
| Schematic vs parts list | 95 nets, **0 differences** |
| Electrical check (ERC) | **0 errors, 0 warnings** |
| Design rule check (DRC) | **0 errors** |
| Unconnected items | **0** |
| Schematic ↔ board match | **0 differences** |
| Remaining warning | 1 cosmetic, from the Arduino library footprint (text on a non-printed layer) |

## Part 6 - What you have now

```
projects/reflex-machine/
  reflex-machine.kicad_sch / .kicad_pcb   the design (open in KiCad)
  DESIGN_BRIEF.md                         the spec and all decisions
  WIRING_GUIDE.md                         how to wire the machine  <-- read this
  out/fab/     reflex-machine_gerbers_JLCPCB.zip, BOM_JLCPCB.csv, CPL_JLCPCB.csv
  out/docs/    3D model (.step), schematic PDF, 3D renders, full parts list
  gen/         the scripts that generate everything
```

## Part 7 - Before you order

1. **Measure your ESP32.** The two pin rows must be 25.4 mm apart.
2. **Check the 3D pictures** in `out/docs/` against your machine's space.
3. **Tell me your magnet current** (or its resistance). The board is built for up to 1.5A per magnet with a 10A
   fuse; if yours pull more, I will widen the copper and change the fuse.
4. **Upload to JLCPCB:** the gerber zip, then the BOM and CPL files if you want them to solder the small parts.
   JLCPCB's preview shows part rotations - check a few before paying.
5. The parts you solder yourself are listed at the end of the wiring guide.

---

## Part 8 - Rebuild on 2026-09-16 (version 2)

You asked for parts you can actually solder, so the board was rebuilt:

1. **Every part is now through-hole (leaded).** No surface-mount components at all: axial resistors, disc and
   electrolytic capacitors, 3 mm/5 mm LEDs, DO-41/DO-201 diodes, DIP-16 for the 74HC595, DIP-4 for the
   optocoupler.
2. **The tiny regulator chip was replaced by a 3-pin 5V module** (K7805-2000R3 or equivalent, 2 A). It drops in
   like an old 7805 and removed the inductor and several small parts from the list.
3. **Values are printed on the silkscreen next to every part,** plus section headings, the Arduino pin beside
   each magnet terminal, and the pin name under each bottom terminal screw.
4. **Two spare-pin headers added** in the free space under the ESP32: a 2x10 "MEGA SPARE" (I2C, Serial3, SPI,
   6 digital, 2 analog, 5V/3.3V/GND) and a 2x4 "ESP32 SPARE" (4 free GPIOs + 3.3V + GND).
5. **The Mega still plugs in underneath** as a shield, as you chose.
6. The board grew from 118 x 108 mm to **160 x 125 mm** - leaded parts need about four times the area.

Checks after the rebuild: netlist compare 0 differences, ERC clean, DRC 0 errors, 0 unconnected,
0 schematic-vs-board differences. Only silkscreen-over-pad warnings remain, which the fab trims automatically.
