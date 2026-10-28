# Session log (historical)
Moved verbatim from CLAUDE.md on 2026-10-28.

## Session log
- **2026-09-11** - Researched AI/KiCad tooling online. Cloned 9 repos into `tools/`, created `.venv` with
  easyeda2kicad/skidl/kicad-skip, installed Seeed kicad-mcp-server + KiKit into KiCad Python, copied kicad-happy
  skills to `.claude/skills`, downloaded Konnect + Freerouting, wrote `.mcp.json`, `README.md`, this file.
  Other options found but not installed: circuit-synth (Python circuits + Claude), atopile, tscircuit,
  mixelpixx/KiCAD-MCP-Server (Konnect's predecessor), lamaalrajih/kicad-mcp, KiBot.
- **2026-09-11** - Started Reflex Machine project. Read both firmware files, extracted full pin map (Mega + ESP32),
  wrote `projects/reflex-machine/DESIGN_BRIEF.md` with proposed architecture + questions A1-H7. User wants all
  questions answered BEFORE any design work starts.
- **2026-09-11** - User answered + said GO (one 12V 16A supply for everything, small DIY LEDs, 5V CC 7-seg,
  "old" Mega + ESP32 DevKit V1 30-pin). Built the design with a scripted pipeline in `projects/reflex-machine/gen/`:
  `netlist.py` (single source of truth) -> `make_sch.py` (+`check_sch.py`: netlist compare + ERC) ->
  `make_pcb.py place|route|finish|check|render` (Freerouting extracted to tools/freerouting, GND pads detached
  during autoroute then fan-out vias + GND pours) -> `make_outputs.py` (JLCPCB gerbers/BOM/CPL, STEP, PDF, renders).
  Mega footprint from Alarm-Siren arduino-kicad-library (courtyard removed, 2 edge holes removed by `fix_mega_fp.py`).
  Custom ESP32 symbol/footprint in `lib/reflex.*` (rows 25.4 mm - user should verify with calipers).
  Wiring instructions for the user: `projects/reflex-machine/WIRING_GUIDE.md`.
  **Result: 118x108 mm 2-layer shield, 127 parts, ERC clean, DRC 0 errors / 0 unconnected / 0 parity issues.**
  Fab files in `projects/reflex-machine/out/fab`, docs+renders+STEP in `out/docs`. Session write-up: `PROJECT_LOG.md`.
  Open question for the user: real magnet current (board sized for <=1.5 A each, 10 A fuse) and ESP32 row pitch (25.4 mm assumed).
- **2026-09-16** - Rebuilt the Reflex Machine board as **all through-hole** (user cannot solder SMD):
  axial R / disc + radial C / 3 mm + 5 mm LEDs / DO-41 + DO-201AD diodes / DIP-16 + DIP-4 ICs, and the SMD buck
  replaced by a 3-pin 5V module (`Converter_DCDC:R-785.0-1.0` symbol + `Converter_DCDC_RECOM_R-78B-2.0_THT`
  footprint; K7805-2000R3). Board 118x108 -> 160x125 mm, channel pitch 14 mm.
  Added on user request: part **values printed on the silkscreen** above each part, section headings, Arduino pin
  beside each magnet terminal and under each bottom-terminal screw, plus **J16 2x10 MEGA SPARE**
  (I2C/Serial3/SPI/D4/D13/D30-D33/A7/A8/5V/3V3/GND) and **J17 2x4 ESP32 SPARE** (IO25/26/27/32/33/14).
  Mega mounting: user chose shield style (pins down into the Mega).
  Deterministic pre-routes now in `place`: U3 pin13->pin8, each gate pull-down -> MOSFET source, a GND bus under
  the ESP32 for both headers, and J16 pin9 -> Mega D4. Result: 0 errors / 0 unconnected / 0 parity; ~213 silk
  warnings are expected because values are printed over pads.
  New docs: `HOWTO_NEW_BOARD.md` (playbook for a fresh session), `LESSONS_LEARNED.md` now 24 traps + a
  through-hole section, `PROJECT_LOG.md` part 8.
- **2026-09-17** - Started a testing pipeline, then paused at the user's request (handover to another agent).
  Working: `test/pinmap.py` parses the pin numbers out of `CODES/*.cpp` and compares them with `gen/netlist.py`
  -> **26 signals, 0 mismatches**; `sim/mega` (PlatformIO) builds `firmware.hex` (11 KB flash, 1.5 KB RAM) for
  Proteus; `sim/esp32` project created. Verified facts: the user has **Proteus 8** installed (no ESP32 model in
  Proteus); **Wokwi** supports Mega + 74HC595 + 7-segment + buttons and two boards over serial; **avr8js** only
  targets the Uno's chip out of the box, so a local live panel would need custom Mega2560 work; PlatformIO CLI is
  at `~/.platformio/penv/Scripts/pio.exe` with AVR + ESP32 toolchains; there is **no host C/C++ compiler**.
  Pending: which test route to build first (Proteus guide / Wokwi diagram / custom offline simulator / bring-up
  self-test). New docs: `HANDOVER.md`, `projects/reflex-machine/test/README.md`.
- **2026-09-17** - Resumed the testing pipeline as a 4-stage framework (electrical check -> SPICE ->
  Wokwi functional sim -> physical bring-up), all validating the real design files rather than a generic
  recreation. **Stage 1 done**: ran DRC/ERC + power/signal integrity via the `kicad` MCP server directly on
  `reflex-machine.kicad_pcb` - 0 DRC errors, GND solid (202 vias), and the per-magnet current path
  (`MAG*_OUT`, 1.5mm single-layer trace) comfortably covers the 1.5A/magnet target. Report:
  `projects/reflex-machine/test/electrical/REPORT.md`. Stage 2 (SPICE) blocked: no simulator installed,
  ngspice has no winget package, LTspice (`AnalogDevices.LTspice`) is available - awaiting user OK to install.
  **Reorganized the whole workspace's docs** (too many root-level .md files, no clear entry point):
  moved `HOWTO_NEW_BOARD.md` -> `docs/NEW_BOARD_PLAYBOOK.md`, `LESSONS_LEARNED.md` -> `docs/LESSONS_LEARNED.md`,
  old `README.md` -> `docs/TOOLING.md`; moved project-specific `HANDOVER.md`/`PROJECT_LOG.md` from repo root
  into `projects/reflex-machine/`; added a new root `README.md` (workspace front door) and
  `projects/reflex-machine/README.md` (project index) that each say which file to read for which task.
  New `test/electrical/`, `test/spice/`, `test/bringup/` subfolders (one per pipeline stage); removed the
  unused empty `test/proteus/` (Proteus has no ESP32 model, so Wokwi covers stage 3 instead).
- **2026-09-17** - **Stage 2 done.** Installed LTspice (`winget install AnalogDevices.LTspice`) since ngspice
  has no winget package. Found and fixed 3 real bugs in the vendored `spice` skill's LTspice backend
  (log-filename collision with LTspice's own `.meas` log, ngspice-vs-LTspice function-name mismatch
  `vdb()`/`vp()` -> `db(v())`/`ph(v())`, and `.meas` result parsing written for an older LTspice log format) -
  see `docs/LESSONS_LEARNED.md` section 8, full writeup in `projects/reflex-machine/test/spice/REPORT.md`.
  Result: all 9 debounce/noise-filter RC networks (coin optocoupler + 4 button filters) confirmed within
  0.24% of calculated cutoff - real SPICE, not just the analyzer's math. Also surfaced a real finding: the
  Mega-TX/ESP32-RX level-shifter divider runs at 3.33V from the actual 5V source (the automated testbench
  had wrongly assumed 3.3V in) - safe, ~270mV under the ESP32's ~3.6V absolute max. Voltage-divider and
  decoupling/PDN automated checks hit separate `spice_templates.py` generator bugs (unrelated to LTspice),
  not fixed - verified those two by hand instead. `projects/reflex-machine/HANDOVER.md` and `test/README.md`
  updated with current pipeline status.
- **2026-09-17** - **Stage 3 built** (not yet run): generated `projects/reflex-machine/test/wokwi/diagram.json`
  from the real `gen/netlist.py` pin map and the firmware's actual 74HC595/7-segment bit order (common-cathode,
  confirmed from `CODES/arduino_main_code.cpp`) - Mega + ESP32 + 4 buttons + coin input + 10 magnet-indicator
  LEDs + 4 status LEDs + 7-seg, including the real 1k/2k serial level-shifter divider. Not validated: no Wokwi
  API token here to drive their CLI (not on the plain npm registry either), and their install script wasn't
  run without asking first - handed to the user to paste into wokwi.com and report back any pin-name errors.
  **Generalized the pipeline for future boards**: added a "Testing pipeline" section (5) to
  `docs/NEW_BOARD_PLAYBOOK.md` describing all 4 stages procedurally (not reflex-machine-specific) so the next
  board copies the same 4-stage structure. The Stage 2 skill fixes already apply workspace-wide since they're
  in the shared `.claude/skills/spice/` scripts, not project files.
- **2026-09-17** - User provided a `WOKWI_CLI_TOKEN` (free tier, 50 min/month). Downloaded `wokwi-cli`
  directly from GitHub releases (`wokwi-cli-win-x64.exe`) since the official install script only recognizes
  Linux/macOS. `wokwi-cli lint` (free, no quota used) caught 29 real pin-name errors in `diagram.json` -
  fixed (Mega digital pins have no `D` prefix, 74HC595 pins are `DS/STCP/SHCP/MR/Q1..Q7` not the
  ngspice-adjacent names I'd guessed, ESP32 devkit has `VIN` not `5V`) - lint now clean. Ran a **5-second
  timed simulation with the real compiled firmware** (costs quota, done with the user's explicit OK) -
  completed cleanly, no crash; empty serial log is correct (firmware only talks over Serial1, to the ESP32,
  not the USB Serial Wokwi's default log captures). Added `test/wokwi/USAGE_LOG.md` (running total of
  simulation-seconds spent this month, currently 5s/3000s) per the user's request to track quota spend.
  New durable lessons in `docs/LESSONS_LEARNED.md` section 9 (Wokwi Windows CLI install, exact pin names
  per part type, quota discipline, why an empty serial log isn't automatically a failure).
  **Built Stage 4** (`test/bringup/self_test.ino` + `CHECKLIST.md`): isolated per-subsystem bring-up
  firmware (status LEDs, 7-seg count, each magnet pulsed 150ms one at a time, all 4 buttons, coin input)
  and a step-by-step physical checklist (pre-power continuity checks, power-up sequence, per-subsystem
  pass criteria, the still-open real-magnet-current measurement, then the ESP32 half) - ready for when the
  board is manufactured. **All 4 pipeline stages now have something built**; remaining open work is Stage 3
  game-behavior verification (needs more Wokwi minutes) and Stage 4 physically running once the board
  arrives.
- **2026-09-17** - Ran a scripted Wokwi scenario (`test/wokwi/scenario_inputs.yaml`) against the real
  firmware: pressed each of S1/S2/S3/RST/coin via `set-control` and asserted with `expect-pin` that each
  pulls the correct Mega pin (22/24/26/28/2) LOW - **all 5 passed**, confirming the input wiring end to
  end in the actual simulator, not just static lint. Hit one snag first: `expect-pin`'s field is
  documented as `expected:` on docs.wokwi.com but the shipped CLI (v0.27.1) actually reads `value:` -
  found by reading `ExpectPinCommand.ts` in their GitHub repo after the first run silently misfired (the
  pin reading was already correct - the assertion syntax was wrong). Recorded in `docs/LESSONS_LEARNED.md`
  section 9, including the general lesson that PWM output pins (the 10 magnet drivers here) aren't
  reliably testable with a single `expect-pin` sample - would need a VCD capture instead. Usage log now at
  13s/3000s (`test/wokwi/USAGE_LOG.md`).
- **2026-09-17** - Built a new top-level **`webview/` platform**: a generic, local 3D viewer + dashboard
  for any project (not reflex-machine-specific), explicitly separate from the testing/creation tools
  (kicad/spice skills, `gen/*.py`, Wokwi) which it calls but never reimplements. Architecture (full detail
  in `webview/ROADMAP.md`): a `manifest.json` per project (components/pins/nets/io/actions) generated by
  `webview/tools/build_manifest.py` (imports `gen/netlist.py` as a real module - no regexing) from a
  small hand-written `io_map.json` (which nets are inputs vs outputs - the one thing that can't be
  auto-derived); a shared icon cache (`webview/tools/build_icon_cache.py`, `kicad-cli sym export svg`
  per symbol actually used, cached across ALL projects); a stdlib-only Python backend
  (`webview/server/`, binds `127.0.0.1` only) serving the manifest/model/icons and running each
  project's declared `actions[]` (`kind: "script"` or `"file"`, never arbitrary/user-supplied commands),
  logging every run to `run_log.jsonl` so the frontend's **Output Console** drawer shows history even
  after closing and reopening it; a Three.js frontend (`webview/app/`, ES modules via jsdelivr CDN,
  `GLTFLoader` + `OrbitControls`) with a project picker, camera presets, and a dashboard listing every
  input/output with its real KiCad-derived icon. Exported reflex-machine's real board as GLB
  (`kicad-cli pcb export glb`, 32MB with tracks/pads/zones/silkscreen). **Fully wired and verified with
  curl** (all routes 200; `pinmap-check` runs the real script live; the 3 stage reports load from disk;
  history persists) but **not yet opened in an actual browser** - do that next, this is Phase 0's one
  unchecked box. Root `README.md`, `docs/NEW_BOARD_PLAYBOOK.md` updated to point at it; this file's
  folder-layout table updated too.
- **2026-09-17** - First real browser test of the webview found and fixed two bugs (server was left
  stopped between sessions - remember to restart it: `python webview/server/server.py 8787`):
  1. The initial GLB export used `--include-tracks/pads/zones/silkscreen` -> 30,594 separate primitives /
     1.38M vertices (one tiny mesh per pad/silkscreen line). Zooming in crashed the WebGL context - not
     really a "GPU power" problem, more a draw-call-count / Windows GPU-driver-timeout (TDR) problem.
     Re-exported without those flags (board body + component 3D models only, same as KiCad's own default
     3D viewer) -> 6,768 primitives / 143K vertices / 3.8MB. If full copper/pad/silkscreen detail is
     wanted back later, merge primitives (Three.js `BufferGeometryUtils` or a glTF optimizer) instead of
     just re-adding the flags - see `webview/ROADMAP.md`.
  2. Separately, real bug regardless of model weight: the camera had no near-plane margin and
     `OrbitControls` had no zoom limits, so zooming in past `near` blanked the model on any hardware.
     Fixed in `webview/app/main.js` `frameModel()`.
  Also implemented **click-to-highlight**: confirmed (by inspecting the GLB's own node list) that KiCad's
  glTF exporter names each component node after its real reference designator - so clicking a dashboard
  io entry now finds `scene.getObjectByName(ref)` directly, adds a `BoxHelper` outline, and re-targets
  the camera. No per-project lookup table needed - resolves a Phase 1 open question ahead of schedule.
  `webview/ROADMAP.md` and `webview/README.md` updated with the full story. Not yet re-verified in an
  actual browser after these fixes.
- **2026-09-17** - User reported every dashboard input/output showed the same icon. Root cause: the
  frontend's fallback ref-inference (used whenever `io_map.json` doesn't set `ref`) picked the
  alphabetically-first `ref.pin` on a net - and since the Arduino Mega's own ref is `A1` (sorts before
  almost everything) and nearly every net touches the MCU, that fallback resolved nearly every entry to
  the Mega's own icon. **Fixed**: added explicit `ref` to every `reflex-machine/io_map.json` entry
  (button connector `J13`, optocoupler `U2`, each magnet's driver MOSFET `Q1..Q10`, status-LED connector
  `J14`, shift register `U3`) and made `main.js` prefer that explicit ref. Regenerated the manifest -
  confirmed all 20 io entries now resolve to distinct, meaningful components. Documented in
  `webview/ROADMAP.md`'s new "Bugs found and fixed after the fact" section, with the explicit warning
  that any future project's `io_map.json` must always set `ref` per entry or this recurs.
- **2026-09-17** - User redirected the interactivity approach: instead of a client-side JS reimplementation
  of the firmware logic (built, then removed), the platform should call a **real** background tool via
  API - reusing the Wokwi pipeline already built in Stage 3, not reinventing it. Discovered `wokwi-cli`
  has an `mcp` subcommand (JSON-RPC over stdio) exposing `wokwi_start_simulation`, `wokwi_set_control`,
  `wokwi_read_pin`, `wokwi_get_status`, `wokwi_stop_simulation` etc. against a REAL running simulation
  (real compiled firmware, real wiring) - exactly the "separate tool working in the background, called
  via API" architecture agreed earlier. Built `webview/server/wokwi_mcp.py` (spawns and talks to that
  subprocess) plus new backend routes (`POST .../sim/start|stop|press`, `GET .../sim/outputs`) and a new
  per-project `wokwi_map.json` (which net maps to which Wokwi part id/control or part id/pin - the only
  new per-project file, everything else generic). Added a `wokwi.toml` to
  `projects/reflex-machine/test/wokwi/` so the MCP server can find the compiled firmware without a CLI
  flag. Frontend: global Start/Stop Simulation button, a Press button per input, a live status dot per
  output polled every 400ms while running. **Every start/stop cycle spends real Wokwi quota** - the
  backend computes elapsed seconds on stop and appends/rewrites a row in that project's own
  `test/wokwi/USAGE_LOG.md` automatically, keeping that file the single source of truth (now at
  23s/3000s used this month). Verified fully through the real HTTP API: start -> press BTN_S1 (no coin
  credit given, so magnets/LEDs correctly stayed off - real firmware behavior) -> poll outputs -> stop,
  log updated correctly. Full writeup, known limitations (no live 7-seg decode, PWM-read flakiness,
  single global session lock, simplified coin-press vs real pulse-count logic), and the removed-mock
  history are in `webview/ROADMAP.md`.
- **2026-09-17** - User feedback after clicking through the live-sim UI: wanted a run-time limit control,
  a live elapsed/quota readout, the Output Console to stop covering the rest of the page, and smoother 3D
  zoom. All fixed:
  1. **Time limit is server-enforced**, not just client-side: `POST /sim/start` now takes `limit_s`
     (clamped 1-300s) and the backend schedules a `threading.Timer` that stops+logs the session even if
     the browser tab closes; the frontend also polls `GET /sim/status` every 300ms to catch up if the
     timer fires first. Added `GET /sim/quota` (read-only) for the topbar's live "quota: Xs left" label.
     Verified end to end: started with a 3s limit, confirmed it auto-stopped and logged correctly
     (`USAGE_LOG.md` now at 35s/3000s).
  2. **Layout bug**: the console was `position: fixed`, overlaying content instead of resizing around it
     - restructured to a real flex column (`#body-flex`) so opening it shrinks the 3D view/dashboard
       instead of hiding them; the existing `ResizeObserver` on `#viewport` picks this up automatically.
  3. **Zoom bug**: `controls.minDistance`/`maxDistance` had been derived from the camera's near/far
     clipping planes (~12,500x range), making OrbitControls' zoom feel binary (only fully-in or
     fully-out). Decoupled zoom range from clipping planes (`radius*0.15` .. `radius*4`).
  User then confirmed the live sim genuinely runs the real Arduino firmware (asked directly - answer:
  yes, `wokwi.toml` points the MCP session at the real PlatformIO-compiled `firmware.hex`/`.elf`, executed
  by Wokwi's real AVR instruction-level CPU emulator, not a mock) and asked for a plain-language activity
  feed ("I pressed this, now this is happening") next to the dashboard. Built one requiring **zero new
  per-project config**: it reads the manifest's own `io[].label` values (already required for every
  project) and diffs each `/sim/outputs` poll against its previous value - so it works for any future
  project the moment `wokwi_map.json` is wired up, with no engine changes. Small always-visible panel
  above Inputs/Outputs, not another drawer.
- **2026-09-17** - User reported the magnet indicators flickering randomly with no clear pattern after
  RST. Root-caused two real bugs and found one genuine tooling limitation:
  1. `/sim/outputs` read all 14 nets via 14 sequential MCP round-trips - seconds per poll instead of the
     intended 400ms, so different magnets got sampled seconds apart. Fixed with `read_pins_batch()` -
     pipelines every read over the one stdio connection instead of waiting for each response first.
  2. Magnets are held via `analogWrite(..., PWM_ON=100/255)` - a real ~39% duty PWM wave, not a steady
     HIGH - so a single instantaneous read is a coin flip per magnet per poll. Fixed with
     `read_outputs_debounced()`: 6 rapid pipelined samples OR'd together. **Verified**: 4 consecutive
     real polls after RST now show all 10 magnets + LED1 solid ON, zero flicker (previously flickered
     every time). Also clarified for the user: their earlier test's "chaotic release" was actually just
     noisy sampling of the still-RESET-held state - the S3 press needed 2000 coin credit and only got
     1000, so the real firmware correctly never left RESET; nothing was actually releasing.
  3. Attempted live 7-segment digit decode (user: "we have countdown and 7-seg, remember?") - built
     `decode_seven_segment()` + a `"display"` spec in `wokwi_map.json`, then empirically found a real MCP
     limitation: sampling the 74HC595's segment pins across a known-stable 700ms blink cycle showed a
     slow "walking ones" pattern over ~2 real seconds instead of two stable states - synchronous
     `wokwi_read_pin` calls don't sample a consistent simulated instant for a fast-changing signal like a
     shift register. **Reverted** the live wiring (removed `"display"` from `wokwi_map.json`) rather than
     ship a UI showing `"?"` - the decode code and `.io-digit` UI element stay in place, unused, for later.
  Full writeup with the exact walking-pattern data in `webview/ROADMAP.md`'s "Phase 2c".
- **2026-09-17** - User reported the wheel zoom fix from earlier still wasn't right. Actually checked the
  GLB's real bounding box this time instead of assuming: KiCad's `pcb export glb` uses real-world
  **meters** - this board is ~0.26m, so `radius ≈ 0.2` (a sub-1-unit-scale scene). The earlier "fix" had
  set `camera.near = Math.max(radius/1000, 0.1)` - that `0.1` floor is *larger* than
  `minDistance` (`radius*0.15 ≈ 0.03`), so OrbitControls would dolly the camera closer than the
  near-clipping plane and the model would vanish in that dead zone - the exact same bug as the original
  report, just reintroduced by an absolute "safe-looking" floor that wasn't safe for this model's actual
  scale. Fixed by removing the floor entirely (`camera.near = radius/1000`, no `Math.max`) and tightening
  `far` from `radius*100` to `radius*10` for better depth precision. New durable lesson in
  `docs/LESSONS_LEARNED.md` section 10: never give a Three.js near-plane an absolute floor "for safety" -
  always derive every camera/controls number purely as a multiple of the model's own measured radius,
  checked against the GLB's real bounding box, not assumed.
- **2026-09-17** - User: "fix the zoom already, only two possible zooms" (3rd report). **Actual root cause
  found: the webview server sent NO cache headers at all** (no `Cache-Control`/`ETag`/`Last-Modified`), so
  the browser had been serving a heuristically-cached old `main.js` across normal refreshes - none of the
  previous zoom fixes were ever loaded. Fixed `_send_file()` to always send
  `Cache-Control: no-store, no-cache, must-revalidate` (verified with `curl -D -`). Also, while there:
  widened the zoom range to `radius*0.05 .. radius*20` (~400x) and inverted the derivation so clipping
  planes come FROM the zoom bounds (`near = minDistance/20`, `far = maxDistance*3`), making it structurally
  impossible for the near plane to sit inside the reachable zoom range; removed the `overflow: auto` on
  `html, body` (a scrollable page competes with the canvas for wheel events) and set
  `touch-action: none; overscroll-behavior: contain` on the viewport. Added a live `zoom d (min - max)`
  readout in the topbar so "the zoom is broken" is falsifiable at a glance next time.
  **Standing lesson: when a frontend change appears to do nothing, check what the browser is actually
  being served before theorising about the code.**
- **2026-09-17** - Zoom finally fixed and **confirmed working by the user**. After the cache-header fix
  let real code reach the browser, the live zoom readout made the true symptom visible: one wheel notch
  jumped straight to min or max. Root cause: three.js r160+ `OrbitControls` zooms by
  `0.95 ^ (zoomSpeed * |deltaY| * 0.01)` - **proportional to the deltaY the mouse driver reports**, and
  free-spin/"smooth scrolling" wheels report thousands per notch instead of ~100, making one notch a 10x+
  jump. No `zoomSpeed` value can fix that (it's hardware-dependent). **Fix**: `controls.enableZoom = false`
  plus our own handler using the wheel's **sign only** with a fixed 8% step (`zoomByNotches()`), giving
  ~78 intermediate levels identically on any machine; also wired to +/- buttons in the topbar. Durable
  lesson added to `docs/LESSONS_LEARNED.md` section 10 (applies to any future Three.js work).
- **2026-09-17** - **Made the platform genuinely work for ANY project (webview Phase 3+4), plus a
  top-level pipeline runner.** Audited the APIs/background work first and found a real genericity bug:
  both generators hard-failed without `projects/<id>/gen/netlist.py` - this workspace's *bespoke*
  convention - so no normal KiCad project could be onboarded at all. The runtime was generic; the
  onboarding tooling was not.
  1. `webview/tools/kicad_pcb.py` - stdlib s-expression reader for `.kicad_pcb` (a file every KiCad
     project has). `build_manifest.py` uses `gen/netlist.py` when present, else falls back to the PCB.
     Verified equivalent: **both paths give 110 nets and all 20 io_map nets resolve** on the same board.
     The PCB path strips KiCad's `/` hierarchical prefixes and drops auto-generated `unconnected-(...)`
     nets so names match either way; icons fall back to generic per-reference-prefix symbols.
  2. `webview/tools/onboard.py` - **one-command onboarding** (export GLB -> cache icons -> scaffold
     `io_map.json`/`actions.json` -> build manifest), replacing the 7-step manual recipe.
  3. **Scale-proof done for real**: onboarded KiCad's own bundled `pic_programmer` demo - a genuinely
     third-party project - with **zero `server/`/`app/` changes**. 63 components/34 nets from its PCB,
     served live, `live_sim: false` correctly. Icon dedup confirmed (3 new exported, 3 reused).
  4. `pipeline.py` (workspace root) - **one command from design to viewable board**: sch -> sch-check ->
     place -> route -> finish -> check -> outputs -> pinmap -> webview, auto-skipping stages a project
     doesn't have. An imported `.kicad_pcb` runs only `webview`; a scripted project runs everything.
  5. **Phase 4 architecture set** (user: "separate tools running on their own, talking with APIs"):
     `server/services.py` is a service registry + proxy - drop a `service.json` in
     `webview/services/<name>/` and the core proxies `/api/services/<name>/*` to it. Proven end to end
     (down-service reports honestly without hanging; GET+POST proxy correctly with body preserved).
     `webview/services/echo/` is a ~40-line reference to copy. **New features should be services, not
     edits to `server/server.py`.**
  6. `webview/API.md` - full reference: every endpoint, all background work (MCP subprocess, auto-stop
     timer, action subprocesses, polling), why output reads are pipelined+debounced, and exactly which
     files a project needs and who writes them.
  8. **Diagrams** (`docs/diagrams/`, linked from the root README): `workflow.svg` (prompt -> one command
     -> what you get), `architecture.svg` (frontend / core / background work / services, with the API
     seams), `status.svg` (phases done vs. the goal, and the single next thing). Hand-written SVG, dark
     theme matching the webview. **Verified by actually rasterising them with headless Edge and looking
     at the result** - which caught an arrow crossing a label in architecture.svg. To re-check after
     editing: `msedge --headless --disable-gpu --screenshot=out.png --window-size=W,H file:///<path>.svg`
     (it writes asynchronously - sleep a couple of seconds before checking for the file, and ignore the
     exit code). ImageMagick is NOT installed here; `convert` on PATH is Windows' own convert.exe.
  7. **Closed the one dangerous gap** before stopping: `pipeline.py` now refuses to re-run design stages
     (sch/place/route/finish) on a board that already has `out/fab` outputs - it would otherwise silently
     re-route a signed-off board. It prints the safe alternatives (`--only webview`, `--only check`) and
     requires `--force` to really redo a finished design. Verified: `reflex-machine` is now protected,
     `--only webview` and the imported project still run freely.
- **2026-09-17** - **Built `projects/uno-toggle` from scratch, A-to-Z, as the first real test of the
  generalised pipeline** (user's spec: "two leds two buttons, arduino uno r3, each button toggles its LED,
  through-hole, on board"). Followed the playbook: DESIGN_BRIEF first, then `gen/netlist.py` as the single
  source of truth. **Result: ERC clean, netlist compare 0 mismatches, DRC 0 errors / 0 unconnected /
  0 parity**, fab + docs written, and **live simulation verified through the platform API: each button
  toggles its LED on, pressing again toggles it off** - real compiled firmware (2578 bytes) on a real
  simulated Uno. Board is a proper Arduino Uno R3 shield outline (68.58x53.34, real chamfered shape).
  What this proved about reuse: `check_sch.py`, `make_outputs.py`, `sexp.py` reused **unchanged**;
  `make_sch.py` needed only the hardcoded title block parameterising (now reads `SCH_TITLE`/`SCH_DATE`/
  etc. from netlist.py); `make_pcb.py` needed a new `placements()` + board constants, which is inherent
  (placement is board-specific) - but it also had **three hidden reflex-machine-isms that broke on another
  board** and are now generic or documented: a hardcoded `"J1"` GND seed in `connect_orphans()` (raised
  `StopIteration`; now seeds from whichever footprint has the most GND pads), an L-shaped `+12V` pour
  region, and a `NL.MAG_PINS` silkscreen loop.
  Platform upgrades in the same session (all generic, no per-project code):
  - **Real components light up in 3D** when their output goes high (emissive glow, colour from the
    part's own value). Gotcha: KiCad's GLB **shares materials between components**, so each mesh's
    material is cloned once on first touch or one LED would light every part sharing it.
  - **Click a part in the 3D view** -> highlights it, logs ref/value/footprint, scrolls + flashes the
    matching dashboard row. Dashboard rows use the same `selectRef()`, so both directions stay in sync.
    Drags are ignored so orbiting doesn't select.
  - **Better rendering**: ACES tone mapping, sRGB output, key/fill/rim lights, transparent canvas over a
    CSS vignette.
  - **Extensible input types** (user: *"not just press, maybe analog... sound sensor, speaker out"*):
    new `POST /sim/input {net, value}` sets a control to ANY number; `/sim/press` remains the momentary
    case. `INPUT_WIDGETS`/`INPUT_TYPE_ALIASES` in `app/main.js` map an input's `type` to a widget
    (momentary / toggle / analog slider with min/max/step/unit). **Adding a new input kind is one
    registry entry - no backend change**, because the simulator control already took a number.
    Verified live: value 1 held a button, 0 released it, non-numeric rejected with a clean 400.
  New lessons recorded (`docs/LESSONS_LEARNED.md` 25-28): footprint-fixer regexes break across KiCad
  file-format eras and **"removed: 0" from an idempotent fixer is a red flag, not success**; shield
  footprints carry the real board outline on `B.Fab` (used it for a genuine Arduino-shaped Edge_Cuts);
  don't wire a rail nothing uses (single-pin net = ERC error); project-local libs need
  `sym-lib-table`/`fp-lib-table`.
- **2026-09-17** - **Debugged the reflex machine's coin input, and generalised inputs as a result.**
  User reported "all magnets turn on and never turn off". **Not a bug**: `STATE_RESET` entry does
  `setAllPWM(PWM_ON)` (all 10 magnets = targets armed) and `updateLeds()` lights LED1 in RESET; they DO
  switch off, via `handleResetTimeout()` after `RESET_TIMEOUT_MS` = **60s**, which the short sim never
  reached. The magnets flickering OFF->ON is the known PWM sampling artifact (held at 100/255 = ~39% duty).
  **The real finding**: the game never actually started - `Status LED 1 ON` proves it stayed in RESET
  (a running speed-1 game shows **LED4**). Coin credit never accumulates. Verified three ways: 6 spread
  clicks, 4 spread clicks, and one atomic 3-pulse burst delivered in 180ms - S1 refused every time.
  **Root cause of the modelling** (user's own insight): a coin acceptor is not a button - the firmware
  counts edges inside a 300ms window (1-2=500, 3-5=1000, 6=2000, 7+ discarded), and each UI click is a
  separate round trip landing 100s of ms apart, so each reads as its own 1-pulse coin.
  Built in response (all generic, per the user's "make it scalable / feed it the type / let me change it"):
  - `POST /sim/pulse` + `pulse_burst()` - atomic pipelined burst injection, **returns `burst_ms`** so you
    can see whether it fitted the firmware's window.
  - `pulse` input type (aliases coin/encoder/flow/tacho/counter) - count box + **Inject** button.
  - `POST /sim/serial` + `write_serial`/`read_serial`. Caveat: Wokwi writes to the primary `Serial`;
    this board takes commands on `Serial1`, so it can't drive THIS firmware.
  - **Editable io type in the UI**, persisted to both `io_map.json` and `manifest.json` via
    `POST /api/projects/<id>/io`.
  **Still unresolved** (documented in `webview/ROADMAP.md` Phase 1d): why no coin credit even from an
  in-window burst. Leading suspect is the Mega `attachInterrupt(digitalPinToInterrupt(2), ...)` pin<->INTn
  mapping - **must be verified on real hardware before calling it a firmware bug**; it may equally be
  Wokwi's button model not driving the AVR external-interrupt path.
  Two self-inflicted traps recorded as lessons 29-30: modelling a pulse input as a button, and hitting my
  own lesson 21 (writing `
` inside a nested heredoc -> SyntaxError).
  **Registered the user's standing instruction** as STANDING RULES at the top of this file and in memory:
  update the docs as part of the work without being asked, keep the workspace clean, verify before
  claiming success.
- **2026-09-17** - Seven platform upgrades ("do them all"), see `webview/ROADMAP.md` Phase 1e for detail:
  serial console, **VCD waveform analyzer** (`webview/server/vcd.py`), scenario recorder, **DRC/ERC
  service** (`webview/services/drc/`), buzzer/tone output, display screenshot output, net highlighting.
  Live-verified: the DRC service (`ok: true | DRC errors: 0 | ERC: 0 errors` on uno-toggle) **through the
  service proxy with zero core changes** - the proof that the Phase 4 architecture actually works; and the
  VCD analyzer (7.6s, 8 channels).
  The VCD capture first failed with "success but no file": **Wokwi only dumps signals wired to a
  `wokwi-logic-analyzer` part**, and `projects/reflex-machine/test/wokwi/diagram.json` had none. Added one
  with `D0..D7` on the magnet + status pins. Now lesson 9 in `docs/LESSONS_LEARNED.md`, with the general
  form: **when an export "succeeds" but produces no artifact, suspect a missing probe declaration before
  suspecting the tool.** Wokwi quota after this session's runs: still well under 5 min of 50.
- **2026-09-17** - **PCB creation tested across scenarios + written up as `docs/PCB_CREATION_GUIDE.md`**
  (the user's ask: "a new agent, even a local downloaded one, should be able to create a PCB by only
  following your instructions, and know how to fix things when they occur").
  Built **`projects/blinky-555/`** from scratch as the no-MCU scenario, then broke it on purpose four
  ways, then tested a 4-layer conversion. Six real bugs found, all fixed and documented:
  1. footprint origins are on **pad 1, not the centre** -> a mounting hole went through a resistor pad.
     New tool `tools/fp_bbox.py` prints a footprint's real courtyard extent around its origin.
  2. `NE555P` `extends` `NE555D` and declares no pins -> new tool `tools/sym_pins.py` resolves that.
  3. silk value/ref text used a fixed 2.2 mm offset -> one tall part caused 56 of 60 warnings.
     Now derived from the courtyard bbox: **60 -> 3 silk warnings**.
  4. `make_sch.py` copied `ki_fp_filters`/`ki_locked` onto placed symbols -> a parity warning per part.
     **9 -> 0.** This CORRECTS lesson 5, which said it was unfixable.
  5. `make_outputs.py` hardcoded the gerber `--layers` list -> a 4-layer board would have shipped a fab
     zip with **no inner copper**, silently. Now read from the board.
  6. `pipeline.py --only a,b` parsed as one stage name, matched nothing, and **reported success having
     done nothing**. Comma lists now split; an unknown stage is a hard error.
  Key finding for the guide: **ERC does not catch a pin number the symbol doesn't have** - the pin just
  vanishes, ERC and DRC both pass, and only `sch-check`'s netlist comparison sees it. New sections 11
  and 12 in `docs/LESSONS_LEARNED.md`.
  Also, answering the user's questions mid-session: **`README.md` now documents how to run everything**
  (stages, the KiCad-Python-vs-system-Python trap, how to start the platform and services), and
  **the webview works fully offline** - three.js was coming from a CDN and is now vendored in
  `webview/app/vendor/`. Added a "Working offline" matrix: board design/fab is 100% offline; only Wokwi
  needs the internet (Proteus 8 is the local substitute).
- **2026-09-17** - **Audited the workspace for genuine project-agnosticism, then fixed what wasn't.**
  Verdict: the *runtime* was already generic (no hardcoded project names or part refs anywhere in
  `webview/server`, `webview/app`, `webview/tools` or `pipeline.py`; proven earlier by onboarding
  KiCad's own `pic_programmer`). The *generator layer* was not, and had already rotted:
  - **The "generic" stages were copied per project and had diverged** - 3 different versions of
    `make_sch.py`, 2 of `make_outputs.py`. `uno-toggle` and `reflex-machine` were still carrying bugs
    fixed only in `blinky-555`. **Fixed by making them shared**: new `tools/boardgen/` package
    (`project.py`, `kicad_paths.py`, `sexp.py`, `make_sch.py`, `check_sch.py`, `make_outputs.py`).
    A project's `gen/` now holds ONLY `netlist.py` + `make_pcb.py`. `pipeline.py` invokes the shared
    stages with `cwd` set to the project's gen dir; `make_pcb.py` imports `boardgen.*`.
    Detect this class of rot with: md5sum the files that should be identical, count distinct hashes.
  - **18 files hardcoded `C:\Program Files\KiCad\10.0`** -> now resolved once in
    `tools/boardgen/kicad_paths.py` ($KICAD_HOME, else newest installed version, else fallback).
  - Runtime artifacts were being kept (`server.log`, 4 `__pycache__` dirs, a stray `capture.vcd`) ->
    removed, and a `.gitignore` added (the workspace is not a git repo yet, but will be correct when
    it becomes one).
  Verified: full `pipeline.py blinky-555 --force` green through the shared package with **identical**
  results (0 errors / 0 unconnected / 0 parity / 3 silk warnings); `uno-toggle` and `reflex-machine`
  verified with the read-only `check` stage only - **per the user's choice, neither was rebuilt**, so
  their signed-off fab output is untouched.
  Two traps hit and recorded as lessons 13-14:
  1. The shared stages take an optional project id, but a project's own `make_pcb.py` runs as
     `make_pcb.py place` - reading argv naively resolved the project to `"place"`. The id must be
     **validated** against real projects before being accepted.
  2. **Writing a Windows path through a bash heredoc corrupted it into ASCII control characters**
     (0x08 backspace), and the corruption is *invisible*: the terminal renders a plausible-looking
     path and `grep` for the visible text finds nothing. Diagnose with `repr()`, never by reading.
     Swept all 98 text files for stray control characters - now 0.
  **Open finding, deliberately not acted on:** `uno-toggle` and `reflex-machine` both set
  `footprint_symbol_field_mismatch` to `ignore` in their `.kicad_pro`, so their "0 parity" is a
  suppressed rule rather than a clean board. The root cause is now fixed in the shared `make_sch.py`,
  so **both should drop that suppression the next time they are rebuilt**. `blinky-555` never
  suppressed it, which is why the bug surfaced there at all.
- **2026-09-18** - **Live simulation for boards with no microcontroller (LTspice), in the same webview.**
  blinky-555 had no simulation: Wokwi only runs firmware and has no 555. Built, all generic:
  `tools/boardgen/make_spice.py` (new shared `spice` pipeline stage - netlist.py -> LTspice deck -> run ->
  binary `.raw` parser -> freq/duty/levels/LED current + `expect` pass/fail -> `test/spice/transient.json`),
  opted in per project by a `SPICE = {...}` block in `netlist.py`; `webview/services/spice/` (port 8801,
  **no core server change**); manifest `spice_sim`; frontend **Run SPICE** replays the run in real time
  (D1 glows in 3D, new `voltage` output type, Analyzer waveforms with a playhead, supply slider 9-12 V
  as a run parameter). blinky-555: **1.385 Hz, 395/326 ms, 54.8 % duty, 14.8 mA** - matches the hand
  calculation. Verified in a real headless Edge driven over CDP (no JS errors, LED toggles on the
  simulated timing, 12 V reaches LTspice -> 21.1 mA). That browser test caught a real bug curl could not
  (rAF timestamp earlier than `performance.now()` -> negative playback time). Lessons: section 15.
  To use it: run `python webview/server/server.py` **and** `python webview/services/spice/service.py`.
- **2026-09-18** - User: "other simulations don't run". Cause: the server was started without
  `WOKWI_CLI_TOKEN` (not stored anywhere on this machine - it must be passed to each server start), so
  `wokwi-cli mcp` hung on its handshake and the UI showed nothing. `/sim/start` now fails fast with a
  clear "token not set, restart the server with it" message. Wokwi projects need the token; blinky-555
  (SPICE) does not.
  Follow-up: the previous agent never saved the token - it retyped it inline in each command from the
  chat. It now has a permanent home: a Windows USER env var (user sets it once), read by the server from
  the registry on every Start Simulation. See `webview/README.md`.
- **2026-09-18** - **`MANUFACTURING.md` in every generated project** (user: "size of each layer, every
  detail manufacturing would ask - holes, components"). New shared stage `tools/boardgen/make_fab_report.py`
  (`fabreport` in `pipeline.py`, read-only so safe on signed-off boards). Quick-answers box for price
  calculators (size in cm, layers, single-sided yes/no, mask, finish), outline, stackup per layer, copper
  per layer, every hole by size/plating **cross-checked against the real .drl** (blinky 187, uno-toggle
  228, reflex 671 - all match), measured closest-hole gap, fab-limit table, parts/BOM, DRC status,
  order-form answers, files to send. Real finding: reflex-machine has two same-net GND holes 0.489 mm
  apart (< JLCPCB's ~0.5 mm; DRC's 0.25 mm rule passed it) - recorded in its HANDOVER, not changed.
  All three boards are 2-layer: a "One Layer" calculator can't make them without a redesign.
- **2026-09-18** - User is worried about wrong connections and can't read a PCB. New shared stage
  `tools/boardgen/make_connections.py` (`connections` in `pipeline.py`) -> `CONNECTIONS.md` per project:
  every pin of every part, where its copper goes, in words, with pin names from the schematic and a
  per-pin schematic-vs-copper cross-check (blinky 24, uno-toggle 53, reflex 433 pins - 0 differences).
  Non-standard-library parts listed first. Hand-verified the risky pinouts against real datasheets:
  IRLZ44N G/D/S, 74HC595, DOIT ESP32 30-pin order - all correct. Still unverified: ESP32 row spacing
  (25.4 mm assumed) - needs a 1:1 paper print test. User asked next for an interactive 3D connection graph.
- **2026-09-18** - User asked "would a new agent know how to go A to Z?". Audit found the playbook a
  fresh agent starts from was stale and partly harmful: it said "copy reflex-machine's gen/ scripts" (the
  exact cause of the diverged-copies bug), ran the old per-project scripts instead of `pipeline.py`,
  recommended heredocs (which corrupted files twice), and never mentioned MANUFACTURING.md /
  CONNECTIONS.md / SPICE-vs-Wokwi / io_map. Rewrote `docs/NEW_BOARD_PLAYBOOK.md` around one **A-to-Z
  checklist (steps A-M)**, pointed CLAUDE.md + README at it, added the 3 new shared stages to
  PCB_CREATION_GUIDE. Remaining gap: no `pipeline.py --new <id>` scaffold yet.
- **2026-10-27/28** - Platform-first roadmap (branch `improve/roadmap-v1`, public repo Mhamednoui/PCB_Designer;
  plan in `docs/PLATFORM_PLAN.md`, statuses in `ROADMAP.md`). P0 made the gates honest and independent: netlist
  lint, parts check, JLCPCB + per-net current DRC rules, native decap distance, review stage, gerber LVS,
  SPICE LED asserts, generic firmware pinmap. Mutation suite 39/39 (tiered, parallel). Parts registry (`parts/`)
  with verification tiers, pins-by-function, fixtures rebuilt on it. Declarative stage registry
  (`tools/boardgen/stages.json`) with input-hash cache, per-run HTML report, toolchain capture. CI + pre-commit
  (`tools/ci_checks.py`), ADRs 0001-0012, design IR (`ir` stage, `tools/boardgen/ir/`). P2 electrical analyzer
  in progress: rule engine, Finding taxonomy, waivers v2, `--explain` done; electrical data in records + IR v2
  done; next P2-T3. reflex-machine routes reliably again (MD-T12). Agent types pcb-light / pcb-worker added.

- **P2-T4** - first three electrical rules EL-ABSMAX, EL-CONTENTION, EL-OD-PULLUP (`tools/boardgen/rules/el_*.py`, docs in `docs/rules/`, fixtures in `tests/rules/fixtures/`) and the new pipeline stage `electrical` (after `ir`; `tools/boardgen/check_electrical.py`, findings to `PCB_FINDINGS_FILE`). Mutations M-volt / M-pullup / M-contend are active; the harness gained a `delete` op (drop the .kicad_pcb so a netlist-topology mutation reaches the stage after the IR cross-check). Fixture results: blinky 0 errors / 3 NOT_JUDGED, uno-toggle 0 / 0, reflex 0 / 18; reflex I2C_SDA/SCL (spare header J16, no on-board pull-up) is NOT_JUDGED because the net leaves the board.

- **2026-10-28 (supervisor)** - merged P2-T9 (requirements engine, `requirements` stage after `electrical`), P2-T6
  (EL-BUDGET/DROPOUT/THERMAL, `projects/synth-ldo` reproduces ref-esp32 power numbers within 2 %) and P2-T5
  (EL-FLOAT/LEVEL/NETSPEC; reflex +5V NET_SPEC corrected). reflex-machine EL-BUDGET (10 coils x 1.5 A = 15 A > 10 A
  fuse/copper) waived as an accepted, fail-safe design limit until 2027-04-30 (owner to measure coil current).
  Mutation runner: LF-normalised copies, `.history` ignored, crash-only single retry, failing tails always printed.
  Full suite 49/49 + 4/4 controls.
- P2-T10a: `release` stage + RELEASE_GATE.md (pcba blocks on any NOT_JUDGED/NOT_EVALUATED/0 requirements; hand blocks on its own cells), generated docs/RULES.md with a stale-check in ci_checks, M-release + CTRL-release mutations. All 5 fixtures pass release as hand with no new waivers.
- **2026-10-28 (supervisor, end of day)** - merged P2-T10a (release coverage gate as the `release` stage, generated
  `docs/RULES.md`) and PA-8 (scaffold commands, CONTRIBUTING). Fixed the scaffold's project template (it showed an
  invalid ASSEMBLY form) and declared `ASSEMBLY = "hand"` on the 3 through-hole fixtures. Next: P2-T10b -> P2 exit.
