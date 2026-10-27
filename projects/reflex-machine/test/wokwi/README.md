# Stage 3 - Wokwi functional/logic sim

`diagram.json` is generated from the real pin map in `gen/netlist.py` and `CODES/arduino_main_code.cpp`
(same source of truth as the PCB) - not a generic recreation. It wires:
- Arduino Mega: 4 buttons (S1/S2/S3/RST) + coin input on their real pins, 10 magnet-indicator LEDs on
  the real PWM pins, 4 status LEDs, the 74HC595 -> 7-segment chain with the exact segment bit mapping
  from the firmware (`SEG_A..SEG_G` in the .cpp, common-cathode).
- ESP32 DevKit: linked to the Mega over UART (Serial1/TX2-RX2), including the real 1k/2k level-shifter
  divider on the Mega->ESP32 leg.

**Not modeled**: the MOSFET/flyback-diode magnet driver stage and the RC debounce filters (Stage 1 and
Stage 2 already validated those on the real files - this stage is for firmware *logic*, not analog
behavior). The onboard magnet-ON indicator LED is wired directly to the PWM pin as a stand-in for "this
magnet is firing," which is functionally equivalent for testing game logic.

## How to run it (no install needed)
1. Go to wokwi.com -> New Project -> Arduino Mega.
2. Replace the project's `diagram.json` with this file.
3. Paste `CODES/arduino_main_code.cpp` in as the sketch (rename the tab to `.ino` if it complains).
4. For the ESP32 half: add a second Wokwi project (ESP32) with `CODES`'s ESP32 sketch, or for now just
   watch the Mega board - the ESP32 in this diagram exists so the UART link isn't floating, but Wokwi
   doesn't yet run two linked boards in one project as easily as two separate tabs. If you want the full
   two-board loop, tell me and I'll split this into two diagrams with instructions for wiring them
   together via Wokwi's "external chip" serial bridge.
5. Press play. Press buttons, watch the magnet-indicator LEDs and 7-segment respond.

## Status: validated with the Wokwi CLI (2026-09-17)
The user provided a `WOKWI_CLI_TOKEN` (free tier, 50 simulation-minutes/month - **be sparing with runs**).
Every timed run is logged in `USAGE_LOG.md` - check it before running another one, and update it
immediately after (lint is free and not logged).
Downloaded `wokwi-cli` directly from GitHub releases (the official install script only targets
Linux/macOS `uname`; the Windows binary exists but isn't offered by that script).

- `wokwi-cli lint --diagram-file diagram.json .` - caught 29 real pin-name errors on the first pass
  (Mega digital pins have no `D` prefix - just `"22"`, not `"D22"`; the 74HC595's pins are
  `DS/STCP/SHCP/MR/Q1..Q7`, not the ngspice-style `SER/RCLK/SRCLK/SRCLR/QB..QH`; the ESP32 devkit has
  `VIN`, not a `5V` pin). Fixed in `diagram.json` - **lint is now clean** (0 errors, 1 harmless info
  about the ESP32 part being "undocumented/may change").
- Ran the **real compiled firmware** (`sim/mega/.pio/build/megaatmega2560/firmware.elf`) against this
  diagram for a 5-second headless simulation (`wokwi-cli --diagram-file diagram.json --elf <path>
  --timeout 5000 --serial-log-file serial.log .`) - completed cleanly (exit 42 = timeout reached, no
  crash). `serial.log` came back empty, which is correct: this firmware only prints diagnostics over
  `Serial1` (to the ESP32), never the USB `Serial` that Wokwi's default log captures - empty log here is
  expected, not a failure.
- **Input wiring confirmed with a real scenario run** (`scenario_inputs.yaml`, 8s, logged in
  `USAGE_LOG.md`): pressed each of S1, S2, S3, RST and the coin input via Wokwi's `set-control`, and
  asserted with `expect-pin` that each press pulls exactly the right Mega pin (22, 24, 26, 28, 2) LOW -
  all 5 passed against the real firmware in the real simulator. This is the schema: `expect-pin` takes
  `name` (or the deprecated-but-working `pin`) and `value` (**not** `expected` - see
  `docs/LESSONS_LEARNED.md` section 9 for how that was found, since it isn't in the public docs).
- **Not yet checked**: full game-round logic (correct magnet lights up, 7-seg score updates, coin count
  accumulates, RST arms all 10 magnets). The magnet outputs are PWM (`analogWrite`, duty ~39%), so a
  single `expect-pin` sample would be timing-flaky against the PWM waveform - would need either a
  `--vcd-file` capture (record the waveform, check duty cycle offline) or a `wait-serial` scenario if the
  firmware printed status over the primary `Serial` (it doesn't - see above). Ask the user before running
  more scenarios; each one costs simulation minutes.

## How to run it yourself (uses simulation minutes on the free tier)
```
export WOKWI_CLI_TOKEN=<your token>
wokwi-cli lint --diagram-file diagram.json .                      # free, static check only
wokwi-cli --diagram-file diagram.json --elf <firmware.elf> \
  --timeout <ms> --serial-log-file serial.log .                   # costs simulation time
```
Or paste `diagram.json` into a wokwi.com Arduino Mega project and press play interactively (also uses
your account's simulation minutes on the free tier, same quota).
