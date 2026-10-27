# Stage 4 - physical bring-up checklist

Only usable once the manufactured board is in hand. Upload `self_test.ino` (Arduino IDE or
`pio run -t upload` from a PlatformIO project pointed at it) **instead of the game firmware** for this
whole checklist - it never runs the real game logic, only isolated per-subsystem checks.

## 0. Before applying any power
- [ ] Visual inspection: no solder bridges, no obviously cold/dry joints, no components in backwards
      (check diode/LED/electrolytic-cap polarity band against the silkscreen).
- [ ] Continuity check with a multimeter (power OFF): +12V to GND should NOT read a dead short.
      +5V to GND should NOT read a dead short.
- [ ] Confirm the 5V module (K7805-2000R3 or equivalent) is in the right orientation before power-up.

## 1. First power-up (no Mega/ESP32 plugged in yet)
- [ ] Apply 12V. The green PWR12 LED (D3) should light.
- [ ] Measure +5V rail at the 5V module output: should read 4.75-5.25V.
- [ ] The green PWR5 LED (D4) should light.
- [ ] Power off. No smoke, no hot components (touch-test the 5V module and the fuse holder briefly).

## 2. Plug in the Mega, upload `self_test.ino`, open Serial Monitor at 115200 baud
- [ ] `[1/5] Status LEDs`: LED1-4 (A3-A6 header) light one at a time, matching the printed order.
- [ ] `[2/5] 7-segment`: counts 0-9 in order, no missing/extra segments, no ghosting.
- [ ] `[3/5] Magnets`: each of the 10 fires (click/buzz) briefly, one at a time, in order M1->M10.
      **Stop immediately (power off) if any magnet or MOSFET gets hot fast** - that means a wiring
      fault, not normal operation for a 150ms pulse.
- [ ] `[4/5] Buttons`: press S1, S2, S3, RST within the 10s window - each should print "pressed - OK".
      Any button printing "NOT SEEN" needs its wiring/connector checked.
- [ ] `[5/5] Coin`: insert one coin/token within the 10s window - should print "detected - OK".

## 3. Magnet current (open question from the design phase)
- [ ] With a magnet actually connected and energized continuously (not the 150ms test pulse), measure
      the current draw at the 12V input or in series with one magnet's terminal.
- [ ] Compare against the board's design target: **<=1.5A per magnet, 10A total fuse**. If any magnet
      draws more, tell the person who did the design work before running all 10 simultaneously - the
      fuse and the `MAG*_OUT` trace width were sized for 1.5A each (see `test/electrical/REPORT.md`).

## 4. ESP32 half
- [ ] Plug in the ESP32, upload its sketch from `CODES/`.
- [ ] Confirm the Mega<->ESP32 serial link works (whatever the game firmware uses to prove it - a
      diagnostic message is the usual approach; see `arduino_main_code.cpp`'s `DIAG|` output over Serial1).

## 5. Only after every box above is checked
- [ ] Re-upload the real game firmware (not `self_test.ino`).
- [ ] Play a full game round for real: pay a coin, wait for magnets to sequence, press buttons, watch
      the score on the 7-segment.

## If something fails
Note which numbered check failed and what you observed (LED didn't light / wrong segment pattern /
button not detected / etc.) - that maps directly back to one net in `gen/netlist.py` and one connector
in `WIRING_GUIDE.md`, which is where to start looking.
