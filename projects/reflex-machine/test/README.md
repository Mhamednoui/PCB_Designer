# test/ - pre-fabrication testing pipeline

4 stages, each testing the real design files (not a generic recreation), from cheapest/fastest to
most realistic. See `../HANDOVER.md` for the current decision point.

| Stage | Folder | Validates | Status |
|---|---|---|---|
| 1. Electrical check | `electrical/` | Real copper: DRC/ERC, power/signal integrity, per-magnet trace current capacity | **Done - pass, see `electrical/REPORT.md`** |
| 2. Analog subcircuit check | `spice/` | Debounce/noise filters, coin optocoupler filter, 5V->3.3V level shifter, via LTspice on the real schematic | **Done - 9/9 filters confirmed <0.3% error, see `spice/REPORT.md`** |
| 3. Functional/logic sim | `wokwi/` | Firmware <-> wiring: button -> magnet, coin count, 7-seg digit, using real compiled firmware and the same topology as `gen/netlist.py` | **Input wiring confirmed** - a real scenario run pressed S1/S2/S3/RST/coin and asserted each pulls the correct Mega pin LOW (all 5 passed). Full game-round logic (magnet sequencing, score, coin count) not yet checked - see `wokwi/README.md` |
| 4. Physical bring-up | `bringup/` | The actual manufactured board | **Ready** - `self_test.ino` + `CHECKLIST.md` written, usable once the PCB arrives |

## Already working (stage-independent tools)
| Command | What it does | Status |
|---|---|---|
| `python pinmap.py` | Reads pin numbers out of `CODES/*.cpp` and compares them with the PCB netlist (`gen/netlist.py`). Catches any wiring/firmware mismatch. | **Working - 26 signals, 0 mismatches** |
| `pio run` in `../sim/mega` | Builds the Mega sketch -> `.pio/build/megaatmega2560/firmware.hex` (load this into stage 2/3/4 tools). | **Working - 11 KB flash, 1.5 KB RAM** |
| `pio run` in `../sim/esp32` | Compile check for the ESP32 sketch. | project created, not run yet |

PlatformIO CLI: `C:\Users\nouir\.platformio\penv\Scripts\pio.exe` (AVR + ESP32 toolchains already installed).

Proteus was considered instead of Wokwi for stage 3 but dropped: the user's Proteus 8 has no ESP32
model, and this game needs both boards.

**All 4 stages now have something built.** Remaining open work: Stage 3 game-behavior verification
(costs Wokwi simulation minutes, see `wokwi/USAGE_LOG.md`) and Stage 4 can only actually run once the
board is manufactured.
