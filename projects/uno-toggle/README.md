# Uno Toggle — start here


**Ordering it:** everything a fab or price calculator asks (size in cm, layers, holes, parts, order-form answers) is in [`MANUFACTURING.md`](MANUFACTURING.md) - generated from the real board, regenerate with `python pipeline.py uno-toggle --only fabreport`.
**Checking the wiring without reading a PCB:** [`CONNECTIONS.md`](CONNECTIONS.md) lists every pin of every part and where it goes, in words.

Two buttons, two LEDs, on an Arduino Uno R3 shield. Press a button → its LED toggles on; press again →
off. Built end-to-end (design → fab → tests → live simulation in the webview) as the second real project
in this workspace, and the first one built entirely with the generalised pipeline.

| I want to... | Read |
|---|---|
| Know what it does and why it's wired this way | `DESIGN_BRIEF.md` |
| Rebuild / change the board | `gen/` — never hand-edit the KiCad files |
| See it in 3D and press its buttons | the webview platform — `python pipeline.py uno-toggle --only webview` |
| Load the firmware | `firmware/uno_toggle.ino` |

## Status — DONE (2026-09-17)
- **Board**: Arduino Uno R3 shield outline (68.58 × 53.34 mm, real chamfered Arduino shape), 2 layers,
  all through-hole, 9 components.
- **Checks**: netlist compare **0 mismatches**, ERC **clean**, DRC **0 errors / 0 unconnected /
  0 schematic-parity issues**. 11 silkscreen warnings remain and are the expected
  value-over-part-outline kind (see `docs/LESSONS_LEARNED.md` lesson 24).
- **Outputs**: `out/fab/` (gerber zip, BOM, CPL), `out/docs/` (STEP, schematic PDF, 3 renders, full BOM).
- **Live simulation**: verified through the platform's API — pressing each button toggles the right LED
  on, and pressing again toggles it off. Real compiled firmware on a real simulated Uno, not a mock.

## Pin map (firmware and board must agree)
| Signal | Uno pin | Part |
|---|---|---|
| BTN1 | D2 | SW1 (+ C1 100nF debounce) |
| BTN2 | D3 | SW2 (+ C2 100nF debounce) |
| LED1 | D8 | R1 330R → D1 (red) |
| LED2 | D9 | R2 330R → D2 (green) |

D0/D1 were avoided (serial) and D13 was avoided (the Uno has its own LED there, which would make
bring-up ambiguous). The 5V rail is deliberately unconnected — nothing on the board draws from it.

## Layout
```
DESIGN_BRIEF.md     spec + the decisions behind it
gen/                netlist.py (single source of truth) + the build scripts
firmware/           uno_toggle.ino - the real sketch
sim/uno/            PlatformIO project; builds the firmware Wokwi actually runs
test/wokwi/         diagram.json + wokwi.toml + USAGE_LOG.md (quota tracking)
lib/                Uno R3 shield symbol + footprint (courtyard stripped, see gen/fix_uno_fp.py)
out/fab, out/docs   manufacturing + documentation outputs
```

## Known cosmetic note
Both LEDs render red in `out/docs/render_*.png` — the 3D model is picked by *footprint*, and both use the
generic `LED_D5.0mm` model. The BOM and schematic correctly say D1 = RED and D2 = GREEN.
