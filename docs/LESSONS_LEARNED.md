# Lessons learned - scripted KiCad 10 PCB design

Written for: my future self (Claude) starting another KiCad board in this workspace.
Source: the Reflex Machine board, `projects/reflex-machine/` - built 2026-09-11 (SMD) and rebuilt
2026-09-16 as an all-through-hole board, entirely from scripts.

---

## 1. The pipeline that worked

```
projects/<id>/gen/netlist.py   # ONE source of truth: parts, pins -> nets, footprints, LCSC numbers
   |-> tools/boardgen/make_sch.py     -> <project>.kicad_sch  (symbols + wire stubs + net labels)
   |-> tools/boardgen/check_sch.py    -> exported netlist compared against netlist.py, then ERC
   |-> projects/<id>/gen/make_pcb.py  place|route|finish|check|render
   |-> tools/boardgen/make_outputs.py -> gerbers, drill, JLCPCB BOM+CPL, STEP, PDF, renders
```
Everything under `tools/boardgen/` is **shared by every board - one copy, never duplicated** (see
section 13). Only `netlist.py` and `make_pcb.py` live in a project, because only they are board-specific.
`python pipeline.py <id>` runs the whole chain and picks the right interpreter per stage.

Rules that made it work:
- **Never hand-edit the .kicad_sch/.kicad_pcb.** Regenerate. Every fix is a code change, so it survives a rebuild.
- **Verify each stage with KiCad's own tools**, not by eye: `kicad-cli sch erc`, `sch export netlist` (compare
  against `netlist.py` - this caught net naming problems immediately), `kicad-cli pcb drc --schematic-parity`.
- **Render after every placement change** (`kicad-cli pcb render`) and actually look at the PNG. That is how I
  caught the magnet terminals facing the wrong way and the LCSC numbers printed on the silkscreen.
- Keep a **`place` stage that is fully deterministic** and re-runnable; never mutate the board by hand.

## 2. Mistakes I made, and the fix

| # | Mistake | Symptom | Fix |
|---|---|---|---|
| 1 | Removing items (zones, vias) through the SWIG API | `TypeError: 'SwigPyObject' object is not iterable` on the *next* `GetTracks()`; stages silently died | **Never call `board.Remove()`**. Keep a separate `-routed.kicad_pcb` without pours; `finish` reads it and writes the final board. Design each stage to add only |
| 2 | Hiding stderr with `2>$null` while iterating | Two stages crashed for several minutes without me noticing; DRC looked "unchanged" | Always run scripts with stderr visible; filter noise lines explicitly |
| 3 | Schematic net names vs board net names | 199 `net_conflict` parity warnings | eeschema prefixes local-label nets with `/` (`/MAG1_OUT`); power-symbol nets stay bare (`GND`, `+5V`). Board nets must match exactly |
| 4 | Unused pins on the board had no net | `net_conflict` per pin | eeschema names them `unconnected-(REF-PINNAME-PadN)`, omits the pin name when it equals the pin number, and escapes `/` in pin names as `{slash}` |
| 5 | Copied symbol fields onto footprints to fix parity | 124 warnings stayed | KiCad **drops `ki_*` fields on save** (`ki_fp_filters`). Unfixable from the *board* side. **CORRECTED 2026-09-17: it is fixable from the SCHEMATIC side** - stop copying `ki_fp_filters`/`ki_locked` onto placed symbols in `make_sch.py` and the warnings go to 0. See section 11. Don't suppress the rule |
| 6 | Autorouting GND | Fragmented pours, poor returns | Give **each GND pad its own one-pad dummy net** during routing: the router keeps full clearance but never routes GND. Restore afterwards. Setting pads to net 0 instead caused 17 clearance violations, because no-net pads get no clearance |
| 7 | GND fan-out vias added *after* routing | 11 SMD GND pads had no room left for a via | Add fan-out vias **before** routing, so the router treats them as obstacles |
| 8 | Netclass track width too wide for a fine-pitch pad | Freerouting could not escape the regulator's SW pad (TSOT-23-6, 0.95 mm pitch) | Keep switching//signal nets on the default width; widen only real power nets |
| 9 | Stitching vias placed without checking hole spacing | `hole_to_hole` warnings | Check spacing against every hole, not just same-net copper |
| 10 | `SetIslandRemovalMode(2)` (below-area) to drop slivers | 9 new `isolated_copper` warnings - bigger isolated islands were now kept | Keep mode `0` (always remove isolated islands) |
| 11 | Trusting Freerouting's "N unrouted" line | It reported 11 unrouted while the board was fully connected | KiCad **adds** SES routes to existing ones across passes. Trust `kicad-cli pcb drc`, not the router's summary |
| 12 | Assuming a KiCad footprint exists | No Mega 2560 shield footprint ships with KiCad | Use `Alarm-Siren/arduino-kicad-library` (accurate shield pads), upgrade it with `kicad-cli fp upgrade` |
| 13 | Shield footprints carry a courtyard and back silkscreen | 30 false `pth_inside_courtyard` errors + silk off the board edge | The Mega sits *under* the board: strip its courtyard, move `B.SilkS` to `B.Fab`, and remove holes that fall outside the cut board outline |
| 14 | Position file used page coordinates | JLCPCB CPL had X=164 mm, Y=-110 mm | Set the aux origin (`SetAuxOrigin`) and export gerbers/drill/pos with `--use-drill-file-origin` / `--drill-origin plot` |
| 15 | Changed footprints in `netlist.py` but regenerated only the PCB | 110 `footprint_symbol_mismatch` + 3 `missing_footprint` parity warnings | The schematic is generated too - **always re-run `make_sch.py` + `check_sch.py` after any netlist edit**, before reading PCB parity results |
| 16 | Left a `PWR_FLAG` on a net that a module drives | ERC error "Power output and Power output are connected" (module OUT pin vs the flag) | Only flag nets with no driving pin. A regulator/module `power_out` pin is already a driver |
| 17 | Guessed part sizes when converting SMD -> through-hole | Dozens of courtyard overlaps; two axial resistor columns need 25.2 mm but only 25 mm was free | Dump real courtyards first (`fp.GetCourtyard(F_CrtYd).BBox()`): axial R 12.35 x 3.08, DO-201AD upright 9.87 x 5.8, 3 mm LED 4.93 x 4.5, disc cap 7.18 x 3.08, DIP-16 9.81 x 20.9. Leaded parts need ~4x the area of 0603 - plan a 14 mm channel pitch and expect the board to grow (118x108 -> 160x122 mm) |
| 18 | Placed a connector far from the circuit that serves it | The coin terminal at the far left could not reach its optocoupler; the router failed that one net every pass | Put each connector next to its own circuit block; then re-label the silkscreen rather than fighting the router |
| 19 | Packing a resistor column tight against an IC | 7 parallel traces fenced in the GND pour on BOTH layers; one IC ground pad ended up isolated and no escape track fitted | Leave a real corridor (>= 6-8 mm) between an IC and a column of parts its pins fan out to. Fixing the placement beat every clever routing workaround |
| 20 | PowerShell piping to a program's stdin | MCP/JSON tools failed with "Invalid JSON: expected value" | PowerShell prepends a BOM. Use the Bash tool for stdin, or a file |

| 21 | Patching a helper script with an escaped regex inside a bash heredoc | The written file had a literal newline in the pattern -> `SyntaxError: unterminated string literal`, twice | Rewrite whole helper files with `cat > file <<'EOF'`; only use in-place patching for simple literal replacements |
| 22 | Dropping new connectors into an area covered by a pour | The two spare headers split the GND pour under the ESP32; two GND pins ended up isolated | Pre-route a short GND bus with stubs to each connector's GND pin, in the gap between blocks, before routing |
| 23 | Expecting the pour to reach every GND pad inside a dense block | One IC pin and one pull-down resistor per rebuild ended up orphaned | Pre-wire predictable GND links at place time (IC pin-to-pin, pull-down to MOSFET source). Deterministic beats hoping the router/pour cooperates |
| 24 | Printing part values on the silkscreen | 274 `silk_over_copper` / `silk_overlap` warnings | Expected and harmless - fabs clip silk over pads. Set `min_text_height` to 0.6 in the project, place the value at the pad centroid (`fp.Value().SetVisible(True)` + `SetLayer(F_SilkS)`), and judge the result from the render, not the warning count |
| 25 | Reusing a footprint-patching script on a footprint from a **different KiCad file-format era** | `fix_uno_fp.py` (copied from `fix_mega_fp.py`) reported *"removed: 0 courtyard shapes"* and **exited successfully** - the courtyard was still there, which would have produced lesson 13's false `pth_inside_courtyard` errors all over again | The Mega footprint is modern tab-indented format; the Uno one is `version 20211014`, **2-space indented with CRLF**. The regex `\n\t\(fp_line` silently matched nothing. Match any indentation (`\n[ \t]*\(`), and **treat "removed: 0" from an idempotent fixer as a red flag, not a success** - assert the thing you meant to remove is actually gone |
| 26 | Assuming a shield footprint has no usable board outline | Nearly drew a plain rectangle outline for an Arduino shield | Arduino shield footprints often carry the **real board shape (chamfered corners and all) on `B.Fab`** - extract those segments and use them as `Edge_Cuts` for a genuine board outline. Filter by coordinate range first: the same layer also holds the USB/barrel-jack outlines, which are NOT the board edge |
| 27 | A single-pin net from wiring a rail nothing uses | Connecting the shield's 5V pin "because a shield should have 5V" creates a one-pin net = ERC error | Only wire a rail something actually draws from. On uno-toggle the LEDs are driven from the digital pins and the buttons use internal pull-ups, so **5V is deliberately left unconnected** |
| 28 | Project-local symbol/footprint libraries not registered | 2 ERC warnings: *"current configuration does not include the symbol library 'arduino-library'"* | Write a project-level `sym-lib-table` + `fp-lib-table` using `${KIPRJMOD}/lib/...`. Copy the pattern from any existing project; ERC goes to `{}` |
| 29 | Modelling a **pulse-counting input as a button** in the simulator | The reflex machine's coin acceptor never registered any credit, so the game could never start - every "press" was a separate HTTP + MCP round trip landing 100s of ms apart, and the firmware groups coin pulses by a **300ms window** (1-2 pulses=500, 3-5=1000, 6=2000, **7+ discarded**) | Pulse inputs need the **whole burst injected atomically by the backend** - see `/sim/pulse` and `WokwiSession.pulse_burst()`, which pipelines every set_control before reading any response (measured 3 pulses in 180ms, inside the window). Never emulate a pulse train with repeated UI clicks |
| 30 | Hitting my own lesson 21 | Writing `\n` inside a nested bash heredoc produced a literal newline in the Python source -> `SyntaxError: unterminated string literal` | **Re-read LESSONS_LEARNED before using a heredoc to patch code.** Use the Edit tool for anything containing escapes |

## 3. KiCad 10 API notes (scripting)
- Symbols: `extends` must be flattened manually (e.g. `Transistor_FET:IRLZ44N` extends `BUZ11`).
- Pin geometry: lib Y is up, schematic Y is down. A pin at angle `a` **points into the body**, so the outward
  direction is `(-cos a, +sin a)` in schematic coordinates. Power-symbol pins sit at the origin, so their
  rotation is cosmetic only.
- Embedded `lib_symbols` in the schematic use the `Lib:Name` key, while the inner sub-symbols keep plain names.
- Writing a schematic with `(version 20250114)` + `(generator_version "10.0")` parses fine in 10.0.6.
- `pcbnew`: `NewBoard()`, `FootprintLoad()`, `ExportSpecctraDSN()`, `ImportSpecctraSES()`, `ZONE_FILLER`,
  `RemoveUnusedNets(None)`, `zone.HitTestFilledArea(layer, pos)`, `polys.Contains(pos, k)` all work.
  `conn.GetConnectedItems(item)` takes **one** argument.
- `kicad-cli pcb render` is the fastest visual check; `--rotate -50,0,25 --perspective` gives a 3D view.
- Project settings (net classes, DRC severities) live in `.kicad_pro`; patch it as JSON. A board loaded without
  its `.kicad_pro` silently loses its net classes - copy the project file next to any board copy.

## 4. Freerouting (v2.4.1)
- Extract the Windows MSI without installing: `msiexec /a file.msi /qn TARGETDIR=<dir>` (bundles its own Java).
- `freerouting.exe -de board.dsn -do board.ses -mp 40` runs headless and routed ~190 nets in 45 s.
- It has no "ignore this net" option, hence the dummy-net trick for GND.
- A second pass can help, but re-check with DRC: its own counters are not authoritative after import.

## 5. Design conventions worth repeating
- Connector-heavy boards: label every screw terminal on the silkscreen with the signal name **and** polarity,
  and hide part references that would collide with those labels.
- Put a plug-in dev board's antenna over the board edge and keep copper away from it.
- Give every hand-soldered THT part a thermal-relief pour connection; SMD GND pads get a fan-out via each.
- Always produce a wiring guide for the user in plain language, separate from the fab files.

## 6. Through-hole (hand-solderable) boards
- The user may not be able to solder 0603. Ask early; converting later costs a full re-layout.
- Swap list that worked: axial resistors `R_Axial_DIN0207_*_P10.16mm_Horizontal`, disc caps
  `C_Disc_D5.0mm_W2.5mm_P5.00mm`, radial electrolytics `CP_Radial_D6.3mm_P2.50mm`, `LED_D3.0mm` / `LED_D5.0mm`,
  `D_DO-41_*`, `D_DO-201AD_P5.08mm_Vertical_CathodeUp` (3 A flyback, stood upright), `D_DO-15_*` (TVS),
  `Package_DIP:DIP-16_W7.62mm` / `DIP-4_W7.62mm`.
- There is no hand-solderable switching regulator IC: use a **3-pin 5V DC-DC module** (`Converter_DCDC:R-785.0-1.0`
  symbol, `Converter_DCDC_RECOM_R-78B-2.0_THT` footprint, 2.54 mm pins) - fits K7805-2000R3, R-78B5.0-2.0 etc.
  It also deletes the inductor and the boot/feedback parts from the BOM.
- Budget the area: the same circuit went from 118x108 mm (SMD) to 160x122 mm (THT).
- Print the value of every part on the silkscreen, the Arduino pin next to each connector, and section
  headings. It costs nothing and makes hand assembly possible without the BOM.

## 7. Testing a board + its firmware
- **Cross-check the sketch against the netlist first.** `test/pinmap.py` parses the pin `#define`s and arrays out
  of the firmware and compares them with `gen/netlist.py`. It is ~80 lines, runs in a second, and is the only
  check that catches "the code says D44 but the board wired D46". Do this before any simulation.
- **Build the firmware locally** with the PlatformIO CLI (`~/.platformio/penv/Scripts/pio.exe`, AVR + ESP32
  toolchains already installed). A compile error or a RAM figure is free information, and Proteus needs the .hex.
- Simulator options, verified 2026-09-17:
  - **Proteus 8** (user has it): runs the real compiled .hex for the Mega, clickable buttons/LEDs/7-segment,
    virtual terminal can play the part of the ESP32. **No ESP32 model** - the WiFi half cannot be simulated.
  - **Wokwi** (free, browser): supports Arduino Mega, `wokwi-74hc595`, `wokwi-7segment`, pushbuttons, and
    **two boards linked over serial** (Mega + ESP32). Nothing to draw - generate `diagram.json`.
  - **avr8js** (the engine behind Wokwi): the npm package targets the ATmega328p; Mega2560 needs custom port and
    timer definitions. Do not promise a local avr8js panel without budgeting that work.
  - **Native unit tests are not possible here**: this machine has no host C/C++ compiler (no gcc, no MSVC).
- A simulator built from the project's own sources (netlist + firmware constants) is worth more than a generic
  one: driving the 7-segment through the netlist's 595 wiring and the firmware's bit table proves the two agree.
- **Electrical checks on the real `.kicad_pcb` file (via the `kicad` MCP server) are the closest thing to
  "testing the actual PCB" before fab** - DRC/ERC, power/signal integrity, and `find_tracks_by_net` for the
  current-carrying nets specifically (not just the supply rail - the per-load net, e.g. `MAG1_OUT`, is what
  actually carries the load current). No simulator runs firmware "through" copper; traces are only checked
  electrically (resistance/current capacity), never for logic behavior.

## 8. The `spice` skill's LTspice backend had three real bugs (fixed 2026-09-17)
Never exercised with LTspice on Windows before this project. All three fixed in
`.claude/skills/spice/scripts/` (workspace-wide, not project-specific - applies to any future board):
1. **Log filename collision**: the orchestrator (`simulate_subcircuits.py`) wrote its own stdout/stderr
   capture to `<label>.log` - the exact filename LTspice batch mode (`-b`) uses for its `.meas` results -
   clobbering them before `parse_results()` ever read them. Fixed by renaming the orchestrator's own file to
   `<label>.run.log`.
2. **ngspice/LTspice function-name mismatch**: testbenches are generated once, in ngspice syntax
   (`vdb()`, `vp()`, `vm()`). LTspice has no such functions - only `db(v(...))`, `ph(v(...))`, `mag(v(...))`.
   Fixed with a regex translation step in `spice_simulator.py`'s `LtspiceBackend.format_measurement_block`.
3. **`.meas` result parsing was written for an older LTspice log format**: LTspice 26 prints
   `name: expr=target AT value` on one line; the parser expected a multi-line `AT=value` continuation and
   grabbed the restated `target` instead of the real measured `value`. Fixed by rewriting the parser to
   prefer the `AT` value for threshold-crossing (`when`) measurements and the `=` value for `MIN`/`MAX`
   measurements.
- **Lesson: always check the `.cir`/`.log` files in the simulator's workdir before trusting a "skip" or
  "fail" verdict from an automated SPICE report** - a "could not measure" message can mean the circuit is
  wrong, or it can mean the tooling's log parsing doesn't match this simulator's version. Don't take the
  summary at face value; read the raw log.
- Some detector templates (voltage-divider, decoupling/PDN impedance) still have generator-level bugs
  (missing `.meas` output for the divider; an undefined vector name `z_mag` for decoupling) unrelated to
  LTspice - not yet fixed. Verify those subcircuits by hand calculation instead until someone invests in
  `spice_templates.py`.
- **A testbench's own assumptions can be wrong even when the simulation "passes."** The R62/R63 divider
  testbench assumed a 3.3V source and reported a trivial pass; the real signal is the Mega's 5V TX line
  (see `DESIGN_BRIEF.md`/`PROJECT_LOG.md` part 2), giving 3.33V out - safe, but only ~270mV under the
  ESP32 RX pin's ~3.6V absolute max. Always check what the analyzer assumed against what the schematic
  actually connects to.

## 9. Wokwi CLI on Windows (fixed 2026-09-17)
- The official install script (`curl https://wokwi.com/ci/install.sh | sh`) only recognizes Linux/macOS
  `uname -s` output and exits "Unsupported OS" on Windows/Git Bash - even though a Windows binary exists.
  Fetch it directly instead: `https://github.com/wokwi/wokwi-cli/releases/latest/download/wokwi-cli-win-x64.exe`
  (or pin a version: `.../releases/download/vX.Y.Z/wokwi-cli-win-x64.exe`).
- **Always run `wokwi-cli lint --diagram-file diagram.json .` before anything else** - it's free (doesn't
  touch simulation-minute quota) and catches wrong pin names immediately. A hand/LLM-written `diagram.json`
  will almost certainly have some: real pin names differ from what you'd guess by analogy with other
  simulators or the real chip's datasheet names -
  - `wokwi-arduino-mega` digital pins have **no `D` prefix**: `"22"` not `"D22"` (analog pins do keep `A0`.. `A15`).
  - `wokwi-74hc595` pins are `DS, SHCP, STCP, MR, OE, Q0..Q7, Q7S, VCC, GND` - not the ngspice-adjacent
    `SER/SRCLK/RCLK/SRCLR/QA..QH` you might expect from the datasheet's own pin names.
  - `wokwi-esp32-devkit-v1` has `VIN`, not `5V`, and its UART2 pins are (correctly, unlike the above)
    `RX2`/`TX2`.
  - The error list itself tells you the valid pin set per part - read it, don't guess twice.
- **A real `--elf`/`--timeout` run consumes the account's simulation-minute quota** (50 min/month on the
  free tier) - `lint` does not. Always ask the user before running a timed simulation, keep runs short
  (a few seconds is enough to catch a wiring/crash problem), and don't loop retries against the paid quota.
- **Empty `--serial-log-file` output is not necessarily a failure.** It only captures the primary
  `Serial` (USB) UART. Firmware that talks over `Serial1`/`Serial2` (as this board's Mega does, to the
  ESP32) will produce nothing there even when running correctly - check what UART the firmware actually
  uses before reading a blank log as a bug.
- **Keep a running usage log next to the diagram** (`test/wokwi/USAGE_LOG.md` here) - date, run, duration,
  cumulative total, remaining budget. On a metered free tier, the person paying for/rationing the quota
  needs to see the running total without asking every time.
- **`expect-pin`'s public docs page (docs.wokwi.com) shows the field as `expected:`, but the actual CLI
  (v0.27.1) reads `value:` instead** (`pin`/`name` for the pin identifier both still work). Confirmed by
  reading `packages/cli/src/scenario/ExpectPinCommand.ts` in the `wokwi/wokwi-cli` GitHub repo after a
  scenario run failed with "expected to be undefined but was 0" - the "0" was the correct real reading,
  the assertion itself was silently miswired. **When a Wokwi CLI scenario command's documented field
  doesn't work, check the TypeScript source in their repo before assuming the circuit is wrong** - the
  docs and the shipped CLI can drift.
- Digital `expect-pin` assertions are reliable for battery/pull-up-style signals (button presses,
  switches) but not for `analogWrite`/PWM output pins - a single sample lands at a timing-dependent point
  in the PWM waveform. Verifying a PWM pin's behavior needs `--vcd-file` (capture the waveform, check duty
  cycle offline) instead of `expect-pin`.
- **`--vcd-file` / `wokwi_export_vcd` only dumps signals wired to a `wokwi-logic-analyzer` part.** With no
  such part in `diagram.json` the export *reports success and writes no file* - which reads exactly like a
  broken tool, and cost a debugging round here before the cause was found. Add the part and wire its
  `D0..D7` to the pins you care about:
  ```json
  {"type": "wokwi-logic-analyzer", "id": "la1", "top": -320, "left": -260, "attrs": {}}
  ```
  ```json
  ["la1:D0", "mega:3", "gray", []]
  ```
  Channels are `D0..D7` (8 max), so choose the eight signals worth watching. Verified working on
  `projects/reflex-machine`: 7.6s captured, all 8 channels parsed by `webview/server/vcd.py`.
  **General rule: when an export "succeeds" but produces no artifact, suspect a missing input/probe
  declaration before suspecting the tool.**

## 10. KiCad's `pcb export glb` uses real-world meters, not mm - check before picking Three.js camera numbers
- A 160-260mm board exports to a GLB with a bounding box on the order of 0.2-0.3 *units*, not 200-300.
  Check with a quick script reading the GLB's JSON chunk (`accessors[].min`/`max`) rather than assuming -
  see `webview/app/main.js`'s `frameModel()` for the working pattern (derive a `radius` from the real
  bounding box, then compute everything else off that).
- **Never trust `deltaY` magnitude from a mouse wheel event.** three.js r160+ `OrbitControls` zooms by
  `0.95 ^ (zoomSpeed * |deltaY| * 0.01)`, i.e. proportional to whatever the mouse driver reports.
  Free-spin / "smooth scrolling" wheels report deltaY in the thousands per notch instead of ~100, so one
  notch becomes a 10x+ jump straight to `minDistance`/`maxDistance` with nothing in between - and no
  `zoomSpeed` value fixes it, because the magnitude is hardware-dependent. Set `controls.enableZoom =
  false` and implement zoom from the wheel's **sign only** with a fixed step per notch (see
  `webview/app/main.js`'s `zoomByNotches()`). Applies to any Three.js work, not just this platform.
- **When a frontend change appears to do nothing, check what the browser is actually being served before
  theorising about the code** (`curl -D - http://.../main.js`). A dev server that sends no
  `Cache-Control`/`ETag`/`Last-Modified` lets browsers heuristically cache JS/CSS across normal refreshes;
  this hid three consecutive frontend fixes and sent debugging down the wrong path entirely.
- **Never give a Three.js camera's `near` plane an absolute floor "for safety"** (e.g.
  `Math.max(radius/1000, 0.1)`) - a floor that looks like a sane minimum for a "normal" 1-100-unit scene
  can be *larger* than a small-scale model's entire `OrbitControls.minDistance`, silently reintroducing
  the exact "model disappears when you zoom in" bug the floor was meant to prevent, just bounded instead
  of unbounded. Derive `near`/`far`/`minDistance`/`maxDistance` purely as multiples of the model's own
  measured `radius`, with no absolute numbers anywhere in the calculation. This bit the `webview/` platform
  twice on the same day before the root cause (an absolute floor) was found - see `webview/ROADMAP.md`
  Phase 2b/2c "Zoom bug, round 1/2" for the full story.

## 11. Placement, silkscreen and layers (found by building `blinky-555`, 2026-09-17)
- **A footprint's origin is usually NOT the centre of the part.** Every through-hole footprint checked
  so far puts its origin on **pad 1**: `R_Axial_..._P10.16mm_Horizontal` has pad 2 at `+10.16`, so a
  resistor placed at `x=48` occupies `x=46.95..59.21`. Placing by assumed-centred coordinates put a
  mounting hole through a resistor pad (`courtyards_overlap` + `pth_inside_courtyard`).
  **Measure first: `python tools/fp_bbox.py <lib>:<Footprint>`** prints the real courtyard extent
  relative to the origin, and write the resulting span in a comment next to each `placements()` entry.
- **A symbol can declare no pins of its own.** `Timer:NE555P` is `(extends "NE555D")`; grepping it for
  pins finds nothing, which looks like a broken library rather than a redirect.
  Use `python tools/sym_pins.py <lib>:<Symbol>` - it follows `extends`.
- **The courtyard layer is spelled `F.CrtYd`, not `Courtyard`.** A filter looking for "Courtyard"
  matched nothing, fell back to pad extents, and reported every part as 0 mm tall - i.e. it looked
  like a legitimate answer. When a filter finds nothing, say so loudly; never let it degrade silently.
- **KiCad's default DRC minimum text height is 0.8 mm.** Anything smaller is a `text_height` violation -
  including the value/reference text the generator places itself, which was 0.7 mm and therefore
  produced one violation per part.
- **Silk text offsets must scale with the part.** A fixed 2.2 mm offset from the pad centroid clears a
  flat axial resistor but lands inside a 6.8 mm electrolytic: one part produced 56 of 60 silk warnings.
  Derive it from `fp.GetCourtyard(pcbnew.F_CrtYd).BBox()` instead - 60 warnings became 3.
  **When warnings cluster on one reference, it is one geometric cause, not N problems.**
- **Don't copy `ki_fp_filters` / `ki_locked` onto placed schematic symbols.** They are library-only
  hints with no footprint counterpart, so KiCad's schematic-parity check reports
  "Missing symbol field ... in footprint" for *every part on the board*, burying real parity errors.
  Skipping them in `make_sch.py`'s property loop took parity from 9 warnings to 0.
- **4 copper layers work fine** (`board.SetCopperLayerCount(4)` auto-enables `In1_Cu`/`In2_Cu`; pours,
  DRC and gerbers all behave, exporting `.g1`/`.g2`). But **`make_outputs.py` hardcoded its gerber
  `--layers` list**, which would have shipped a 4-layer board's fab package with NO INNER COPPER -
  silently, with a zip that looks and uploads fine. It now derives the list from the board.
  **General rule: anything enumerating layers/nets/parts must read them from the design, not restate them.**
- `board.GetNetsByName()` returns local nets with a leading `/` (`"/VCC"`) and global power nets
  without (`"GND"`) - the same split as `pcb_net_name()`. Look up both spellings.

## 12. What each check can and cannot catch
Four deliberate breakages of the same board, each caught by a different mechanism - which is why
skipping a pipeline stage is how a bad board gets made:

| Mistake | Caught by | Other checks |
|---|---|---|
| Footprint name typo | `place` raises `RuntimeError` | stops the run |
| Symbol name typo | `sch` raises `KeyError` | stops the run |
| **Pin number the symbol doesn't have** | **`sch-check` netlist compare ONLY** | **ERC clean, DRC clean** |
| Net name split in two | `netlist.py` pre-check; ERC *warning* | DRC clean - both halves are legal nets |

The last two reach fabrication. A pin number that doesn't exist simply **vanishes** - the schematic is
internally consistent, so ERC passes and the real pin ends up unconnected. ERC and DRC only verify
internal consistency; a board can be perfectly consistent and still not be the board you meant. Only
diffing the exported netlist against declared intent catches it. **Never skip `sch-check`, and never
read "ERC clean" as "wired correctly."**

## 13. Shared code vs copied code (the refactor of 2026-09-17)
- **Copied "generic" scripts diverge, silently and fast.** `make_sch.py`, `check_sch.py`,
  `make_outputs.py` and `sexp.py` were copied into every project and labelled "generic, copy as-is".
  Within three boards there were **three different versions of `make_sch.py` and two of
  `make_outputs.py`** - and two projects were still carrying bugs that had been fixed in the third
  (a schematic-parity warning on every part, and a gerber export that would ship a 4-layer board with
  no inner copper). Nothing reported this; the copies just quietly drifted.
  **Fix:** the generic stages now live once in `tools/boardgen/` and every project uses them.
  `projects/<id>/gen/` holds only `netlist.py` and `make_pcb.py` - the two genuinely board-specific
  files. **If a shared stage needs to differ for your board, make it configurable - never fork it.**
- **How to detect this class of problem:** `md5sum` the files that are supposed to be identical across
  projects and count the distinct hashes. Anything above 1 for a "generic" file is a bug.
- **Don't parse a project id out of `sys.argv` without validating it.** The shared stages take an
  optional project id, and a project's own `make_pcb.py` is invoked as `make_pcb.py place`. Since
  `make_pcb.py` imports the shared modules, a naive "first non-flag argument" read the project id as
  `"place"` and the build died with `no netlist.py for project 'place'`. Check that the candidate
  actually names a project before accepting it, then fall back to the working directory.
- **One place for the KiCad install path.** 18 files each hardcoded
  `C:\Program Files\KiCad\10.0`, so a KiCad upgrade meant editing all of them and any miss would fail
  differently (a missing `kicad-cli`, or worse, symbols silently read from the old version). Now
  resolved once in `tools/boardgen/kicad_paths.py`: `$KICAD_HOME` if set, else the newest installed
  version, else the known-good fallback.
- **"0 violations" can mean "rule switched off".** `uno-toggle` and `reflex-machine` both set
  `footprint_symbol_field_mismatch` to `ignore` in their `.kicad_pro`, so their parity check reports 0
  because the rule is suppressed, not because the board is clean. `blinky-555` does not suppress it,
  which is exactly why the underlying bug surfaced there and got fixed at the root.
  **When a check reports zero, confirm the rule is actually enabled** - and prefer fixing the cause to
  silencing the rule. Both of those projects can drop the suppression next time they are rebuilt.

## 14. Writing Windows paths through a bash heredoc corrupts them INVISIBLY
Patching a file with `python - <<'PY'` and a replacement string containing a Windows path wrote real
ASCII control characters into the file: the path became
`C:\Program Files\KiCad` + 0x08 + `.0` + 0x08 + `in\python.exe`, because the backslash escapes were
interpreted somewhere in the chain. **The corruption is invisible on screen** - 0x08 is backspace, so
the terminal eats the preceding character and prints something that still looks like a plausible path
(`C:\Program Files\KiCad.0in\python.exe`). Worse, `grep` for the displayed text finds nothing, because
that text does not exist in the file.
- Symptom: a search for the string you can plainly see on screen returns no match.
- Diagnose with `repr()` of the line, never with a visual read or a `grep`.
- **Never build a string containing backslashes inside a heredoc.** Use the Write tool to create a
  small script file and run that, or use the Edit tool. This is the same family as lesson 21 but
  strictly worse, because lesson 21's version fails loudly with a `SyntaxError`.
- Worth a sweep after any heredoc-based patching session: scan text files for 0x01/0x08/0x0b/0x0c and
  print `repr()` of any line that has them. A clean workspace scan is 0 lines.

## 15. Simulating a board with no microcontroller (LTspice, 2026-09-18)
- **Wokwi cannot simulate a board without firmware** - it has no 555, and its parts are digital. For an
  analog/timer/power board the simulator is SPICE: `tools/boardgen/make_spice.py` builds the deck from
  `netlist.py`, so it simulates the *same* circuit the PCB was made from, not a redrawn one.
- **LTspice ships its own `NE555` subcircuit** (`%LOCALAPPDATA%\LTspice\lib\sub\NE555.sub`, `.lib NE555.sub`)
  and its pins 1..8 are in DIP order - identical to KiCad's `Timer:NE555P` pin numbers, so no remapping.
- **LTspice's `.raw` is binary**: a UTF-16LE header up to `Binary:\n`, then per point one float64 time
  followed by float32 per variable (all float64 if `Flags:` contains `double`). Time can carry a sign
  bit as a marker - take `abs()`. Use `.options plotwinsize=0` so the waveform isn't compressed.
- **LTspice writes a second file, `<name>.op.raw`**, besides `<name>.raw`. Delete both after parsing or
  they pile up in the project.
- **Measure levels on the settled part of a transient, not the whole run.** Every node starts at 0 V at
  power-on, so a 555's 3-6 V timing ramp measured over the full run reads 0-6 V and the mid-level
  threshold lands in the wrong place (TRIG reported 100 % duty). Use the second half for min/max.
- **The 555 frequency does not depend on the supply**, but the LED current does - a useful sanity check
  that a slider actually reached the simulator (9 V -> 14.8 mA, 12 V -> 21.1 mA, 1.385 Hz both times).
- **Never drop a part the simulator has no model for.** Leaving it out simulates a different circuit and
  still reports success. `make_spice.py` stops with the part's ref and lib_id instead; connectors are the
  only deliberate skip (the declared supplies replace whatever plugs into them).
- **`requestAnimationFrame`'s timestamp is the frame's start time and can be EARLIER than a
  `performance.now()` taken just before scheduling it.** Using `performance.now()` as the playback
  origin made the first frame's time negative -> array index -1 -> `undefined.toFixed` crash. Take the
  origin from the first frame's own timestamp.
- **A headless browser can be driven with no extra installs**: Node 22+ has a global `WebSocket`, so a
  ~60-line script can launch `msedge --headless=new --remote-debugging-port=N`, click buttons and read
  `Runtime.exceptionThrown` over CDP. That is what caught the rAF bug - `node --check` and curl could not.
  Headless Edge ignores `--window-size` with `--headless=new`; set the size with
  `Emulation.setDeviceMetricsOverride`.
- **A missing `WOKWI_CLI_TOKEN` looked like "the simulation just doesn't run".** `wokwi-cli mcp` never
  answers the handshake without a token, so `/sim/start` hung until the MCP timeout, the browser gave up
  first (`ConnectionAbortedError` in the server log) and the UI showed no error at all. `/sim/start` now
  checks the token first and returns a clear message instantly. The token lives only in the shell that
  starts `server.py` - it is not saved anywhere on this machine, so every restart needs it again.
  **Now fixed for good**: the token is saved once as a Windows USER environment variable
  (`[Environment]::SetEnvironmentVariable('WOKWI_CLI_TOKEN','<token>','User')`), and
  `wokwi_mcp._load_saved_token()` reads it from `HKCU\Environment` on every `/sim/start` - so it works
  from a terminal opened before it was saved and needs no server restart. Never put it in a project file.

## 16. Manufacturing report (`make_fab_report.py`, 2026-09-18)
- **Measure, don't restate.** The report reads the real `.kicad_pcb` and the `.drl` actually sent to the
  fab, and cross-checks the two hole counts - a mismatch means stale fab files.
- **The stackup is NOT reachable through KiCad 10's SWIG API** (`GetStackupDescriptor()` returns an opaque
  `SwigPyObject`); parse the `(stackup ...)` block from the file. Most generated boards have none, which
  means KiCad's default build: 1.6 mm, 35 um (1 oz) copper - say so rather than leaving it blank.
- `BOARD.GetBoardPolygonOutlines(poly, False)` needs the second argument in KiCad 10; pass False so a broken
  Edge.Cuts is reported instead of silently replaced by an inferred outline.
- `GetBoardEdgesBoundingBox()` includes the Edge.Cuts line width (70.1 x 45.1 for a 70 x 45 board). Use the
  outline polygon's BBox for the real size.
- **DRC rules are not fab limits.** KiCad's default hole-to-hole rule is 0.25 mm; JLCPCB quotes ~0.5 mm.
  Measuring the real closest pair found 0.489 mm on reflex-machine that DRC passed. Report measured values.
- Print limits with 3 decimals: 0.127 mm rounded to "0.13" makes a pass look marginal.
- A one-layer-only price calculator can't make any board with copper on both sides, vias or SMD pads on
  the back - the report answers "can it be single-sided?" explicitly.

## 17. Plain-language connection list (`make_connections.py`, 2026-09-18)
- **Board files don't carry pin names.** `pad.GetPinFunction()` is empty on generated boards - take the
  names from `kicad-cli sch export netlist --format kicadxml` (`<node pinfunction=...>`).
- KiCad 10's XML `pinfunction` is `<name>_<number>` (`G_1`, `D2_INT0_D2`) and uses overbar markup
  (`~{RST}`). Strip both before showing it to a person.
- Take WHERE a pin goes from the board copper and WHAT it's called from the schematic, then compare the two
  per pin - that's an extra, independent schematic-vs-board check (reflex-machine: 433 pins, 0 differences).
- "Project-local library" does not mean "drawn by us": the Arduino shield footprints are third-party
  downloads. Flag them as "not from KiCad's standard library", which is the honest claim.
- **Hit lesson 14 again while writing this tool**: a regex backreference `\1` patched in through a bash
  heredoc became a raw 0x01 byte. Symptom: the output silently lost text ("RST" vanished), and the Edit
  tool could not match the line it displayed. `repr()` showed `\x01` at once. Rule, now twice-learned:
  **anything with a backslash goes through the Edit tool, never a heredoc.**

**Found again by CI (PA-9):** `tools/boardgen/check_sch.py` carried a raw 0x08 in a regex (a `BS-b` from a heredoc) for weeks; `python tools/ci_checks.py ctrlchars` now catches this class on every commit.
### Freerouting results swing with the DSN item order, and KiCad's order is random (MD-T12)
KiCad writes (and exports to Freerouting) footprints in random-UUID order, so the *same* placement reached the
router in a different order each build and routed fully or left one net open ("flaky" reflex builds that failed
identically on all retries). `place` now assigns UUIDs derived from the reference (`_stable_uuids`), the DSN net
blocks start sorted (retries shuffle them with the attempt number), and the route check also treats a router-made
short (`shorting_items`) as a failure. Check determinism with: run `place` twice, diff the files after stripping uuids.
