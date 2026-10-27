# Blinky 555 — 1 Hz LED flasher


**Ordering it:** everything a fab or price calculator asks (size in cm, layers, holes, parts, order-form answers) is in [`MANUFACTURING.md`](MANUFACTURING.md) - generated from the real board, regenerate with `python pipeline.py blinky-555 --only fabreport`.
**Checking the wiring without reading a PCB:** [`CONNECTIONS.md`](CONNECTIONS.md) lists every pin of every part and where it goes, in words.

A standalone NE555 astable that blinks one LED at about 1.4 Hz from a 9–12 V supply.
70 × 45 mm, 2-layer, entirely through-hole, 9 parts.

**Status: done.** `0 DRC errors / 0 unconnected / 0 schematic-parity / 3 silk warnings`, ERC clean,
netlist compare 0 mismatches. Fab files in `out/fab`, documentation and renders in `out/docs`.

## Why this board exists

It is the pipeline's **test case for a board with no microcontroller**. The other two boards are
Arduino shields, which hide several things this one is forced to do for itself:

- pick its **own board outline** (a rectangle) instead of inheriting one from a shield footprint
- place its **own mounting holes**
- carry a **real VCC rail**, so two power-flag nets rather than just GND
- use a **multi-pin DIP** part, so pin numbers must come from the symbol, not from 1/2 convention
- use only **stock KiCad libraries** — `PROJECT_LIBS` is empty, nothing is vendored into `lib/`

Building it found six real bugs, all written up in `docs/PCB_CREATION_GUIDE.md`. Three of the fixes
were to the shared generator scripts and benefit every future board:

| Fix | Effect |
|---|---|
| silk text offset derived from the footprint courtyard instead of a fixed 2.2 mm | 60 → 3 silk warnings |
| `make_sch.py` no longer copies `ki_fp_filters` / `ki_locked` onto placed symbols | 9 → 0 parity warnings |
| `make_outputs.py` derives the gerber layer list from the board | a 4-layer board no longer ships with no inner copper |

## Circuit

Standard 555 astable. `f ≈ 1.44 / ((R1 + 2·R2)·C1) = 1.44 / ((10k + 94k)·10 µF) ≈ 1.4 Hz`.

| Part | Value | Role |
|---|---|---|
| U1 | NE555P (DIP-8) | the timer |
| R1 | 10 k | VCC → DISCH (charge path) |
| R2 | 47 k | DISCH → TRIG (charge and discharge path) |
| C1 | 10 µF electrolytic | timing capacitor — **polarity matters**, pad 1 (left) is + |
| C2 | 10 nF | noise filter on CONT |
| C3 | 100 nF | decoupling at U1 pin 8 |
| R3 | 470 R | LED current limit (~15 mA at 9 V) |
| D1 | red LED, 5 mm | the output |
| J1 | 2-pin terminal block | 9–12 V in — **polarity marked on the silkscreen**, + is pad 1 |

`U1` pin 4 (`~RST`) is tied to VCC. A floating reset pin holds the timer in reset at random and is
the most common reason a hand-wired 555 does nothing.

## Simulate it
No microcontroller means nothing for Wokwi to run, so this board is simulated with **LTspice** on its
own netlist (`SPICE` block in `gen/netlist.py`, run by `tools/boardgen/make_spice.py`):

| | Hand calculation | LTspice |
|---|---|---|
| frequency | 1.39 Hz | **1.385 Hz** |
| LED on / off | 395 / 326 ms | **395.4 / 326.5 ms** (54.8 % duty) |
| LED current | ~15 mA at 9 V | **14.8 mA** at 9 V, 21.1 mA at 12 V |

```bash
python pipeline.py blinky-555 --only spice          # or: python tools/boardgen/make_spice.py blinky-555 --set VCC=12
```
**In the webview**: start `webview/server/server.py` and `webview/services/spice/service.py`, pick
blinky-555, press **Run SPICE**. D1 blinks on the 3D board in real time, C1's voltage ticks live, and the
Analyzer tab shows the waveforms. The supply slider (9-12 V) sets the next run. Offline, no quota.

## Build it

```bash
python pipeline.py blinky-555 --list     # confirm the stages
python pipeline.py blinky-555 --force    # --force because out/fab already exists
```

Everything comes from `gen/netlist.py`. **Never hand-edit the generated KiCad files** — change the
generator and re-run. See the workspace `README.md` § "Running the scripts".

## Assembly notes

Two parts can be fitted the wrong way round and both are marked on the silkscreen — check them:
- **C1** — the electrolytic. `C1+` is printed beside it; the positive lead goes in pad 1.
- **J1** — `+` and `-` are printed above the two pads. Reversing the supply destroys the 555.

The LED and the 555 itself are also polarised (cathode flat / pin-1 notch), marked by the footprints'
own silkscreen.
