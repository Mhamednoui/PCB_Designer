# PCB Webview Platform - Roadmap

Written for: whoever (human or Claude session) continues this next - assume you have no memory of the
conversation that started it. Read this file fully before changing anything. Update it before you stop.

## What this is
A **generic, scalable, local viewing platform** for any board in this workspace's `projects/` folder:
a real 3D render of the actual PCB (exported from KiCad, not a mockup) plus a dashboard of every input
(buttons/switches/coin) and output (LEDs/actuators/displays), each shown with a component icon, its pin,
and its net - all read from a per-project **manifest**, never hardcoded per board.

**This platform does not do testing or PCB creation itself.** Those tools already exist separately
(`.claude/skills/kicad`, `.claude/skills/spice`, `gen/*.py`, the Wokwi CLI pipeline in
`projects/*/test/wokwi/`) and stay separate. This platform's backend calls them and shows the result in
an **Output Console** the user can open/close any time - from the user's side it looks like one running
application; under the hood it's two processes (a static/API backend + a static frontend) talking over
`localhost`. Never blur this line by reimplementing testing logic inside the frontend or the backend.

## Architecture
```
webview/
  ROADMAP.md              this file
  README.md               how to run it (start the server, open the browser)
  server/
    server.py             stdlib-only Python HTTP server: static files + a small JSON API
    actions.py            executes a project's declared "actions" (subprocess or file-read), logs results
  app/                     static frontend, no build step - open through the server, not file://
    index.html
    style.css
    main.js                Three.js scene, dashboard panel, console drawer
    assets/
      icons/<kicad-lib>/<symbol>.svg     shared icon cache across ALL projects, built once per symbol
  projects/
    <project-id>/
      model.glb            exported via `kicad-cli pcb export glb` from that project's real .kicad_pcb
      manifest.json         components/pins/nets/io/actions - generated, never hand-edited (see below)
      io_map.json            the one small hand-written file per project (which nets are inputs/outputs)
      run_log.jsonl          action run history, created at runtime by the backend - not checked in fresh
  tools/
    build_manifest.py     generic generator: <project's gen/netlist.py> + io_map.json -> manifest.json
    build_icon_cache.py   generic: `kicad-cli sym export svg` per library referenced by a project's parts,
                           skips libraries already cached
```

### The manifest contract (the "certain format" the platform reads)
`manifest.json` is the ONLY thing `app/main.js` reads to know about a project - never `netlist.py`,
never `.kicad_pcb`/`.kicad_sch` directly. Shape:
```json
{
  "id": "reflex-machine",
  "name": "Reflex Machine",
  "model": "model.glb",
  "components": [
    { "ref": "Q1", "value": "IRLZ44N", "symbol": "Transistor_FET:IRLZ44N", "footprint": "...",
      "pins": { "1": "MAG1_G", "2": "MAG1_OUT", "3": "GND" }, "group": "magnets",
      "icon": "assets/icons/Transistor_FET/IRLZ44N.svg" }
    // ... every part from netlist.py, icon path resolved by build_icon_cache.py
  ],
  "nets": { "MAG1_OUT": ["Q1.2", "J2.2", "D11.2", "D21.2"], ... },
  "io": [
    { "net": "BTN_S1", "kind": "input", "type": "button", "label": "S1", "ref": "J13" },
    { "net": "MAG1_PWM", "kind": "output", "type": "led", "label": "Magnet 1 driver", "ref": "A1" }
    // from io_map.json - the one manual per-project file, see below
  ],
  "actions": [
    { "id": "pinmap-check", "label": "Pin cross-check (firmware vs netlist)", "kind": "script",
      "cwd": "projects/reflex-machine/test", "cmd": ["python", "pinmap.py"] },
    { "id": "electrical-report", "label": "Electrical check (Stage 1)", "kind": "file",
      "path": "projects/reflex-machine/test/electrical/REPORT.md" },
    { "id": "spice-report", "label": "SPICE report (Stage 2)", "kind": "file",
      "path": "projects/reflex-machine/test/spice/REPORT.md" }
    // Wokwi actions deliberately NOT wired yet - costs the user's simulation-minute quota,
    // must be opt-in per click, never triggered automatically. See Phase 3.
  ]
}
```

### `io_map.json` (the one hand-written file per project)
Net names alone don't reliably say "this is a button" vs "this is a status LED" across different
projects' naming conventions - that has to be declared once, by whoever wires up a new project:
```json
{
  "inputs": [
    { "net": "BTN_S1", "type": "button", "label": "S1", "ref": "J13" },
    { "net": "COIN_IN", "type": "coin", "label": "Coin", "ref": "U2" }
  ],
  "outputs": [
    { "net": "MAG1_PWM", "type": "led", "label": "Magnet 1", "ref": "Q1" },
    { "net": "LED1", "type": "led", "label": "Status LED 1", "ref": "J14" },
    { "net": "SEG_DATA", "type": "seven-segment", "label": "Score display", "ref": "U3" }
  ]
}
```
**`ref` is optional but write it anyway** - it's the component whose icon/highlight represents this
entry. Without it the frontend falls back to inferring a ref from the net's connected parts, and that
fallback is unreliable: see the "same icon everywhere" bug below.

## Phases

### Phase 0 - foundation - **DONE 2026-09-17**
- [x] Export the real board as GLB: `kicad-cli pcb export glb` (tracks/pads/zones/silkscreen included).
      `webview/projects/reflex-machine/model.glb`, 32MB.
- [x] Directory structure above created.
- [x] `tools/build_icon_cache.py` - exports one SVG per symbol actually used (via `kicad-cli sym export
      svg --symbol <name>`, not the whole library), output named `<symbol>_unit1.svg`. Reflex-machine:
      19/19 symbols exported clean on the first run.
- [x] `tools/build_manifest.py` - imports `gen/netlist.py` as a real Python module (uses its own
      `PARTS`/`nets()`), merges `io_map.json` + `actions.json` -> `manifest.json`. Reflex-machine:
      123 components, 110 nets, 20 io entries, 4 actions, 0 missing icons.
- [x] `projects/reflex-machine/io_map.json` - hand-written (5 inputs: S1/S2/S3/RST/coin; 15 outputs:
      10 magnets, 4 status LEDs, 1 seven-segment).
- [x] `server/server.py` - stdlib `http.server`/`ThreadingHTTPServer`, binds `127.0.0.1` only, path
      traversal guarded (`safe_join`), all routes from the design above implemented and curl-tested:
      static app files, static per-project files (model.glb, icons), `/api/projects`,
      `/api/projects/<id>/manifest`, `/api/projects/<id>/log`, `POST .../actions/<id>`.
- [x] `server/actions.py` - `kind: "script"` (subprocess, 60s timeout) and `kind: "file"` (read), nothing
      else. Verified live: `pinmap-check` actually runs `test/pinmap.py` and returns real output;
      `electrical-report`/`spice-report`/`wokwi-report` return the real Stage 1-3 report files.
- [x] `app/index.html` + `main.js` + `style.css` - Three.js (jsdelivr CDN, ES modules via importmap) +
      `GLTFLoader` + `OrbitControls`, project picker, iso/top/bottom camera presets, dashboard (icons +
      label + net + owning ref per io entry), Output Console drawer (open state in `localStorage`,
      history loaded from `/log` on project switch, live results appended on action click).
- [x] `webview/README.md` - run instructions + the "add a new project" recipe.
- [ ] Update workspace `README.md`, `CLAUDE.md`, `docs/NEW_BOARD_PLAYBOOK.md` - **in progress, do this
      next if you're picking this up cold.**
- [ ] **Not yet done by a human**: actually opening `http://127.0.0.1:8787/` in a real browser and
      looking at it. Everything above was verified with `curl` (all routes 200, actions return real
      output) but nobody has looked at the rendered page yet - do this before believing Phase 0 is
      genuinely finished. Report anything that looks wrong (WebGL context issues, CORS on the CDN
      imports, layout bugs) rather than assuming curl-passing means visually correct.

### Phase 1 - make it actually useful to look at
- [x] Camera presets (top/bottom/iso) instead of only free-orbit. Done in Phase 0.
- [x] Click a dashboard `io[]` entry -> highlight its component with a `BoxHelper` outline and re-target
      orbit controls on it. **Mesh-naming question resolved**: KiCad's GLB exporter names each top-level
      component node after its real reference designator (`R33`, `U3`, `D18`, confirmed by inspecting
      the exported GLB's node list directly) - `scene.getObjectByName(ref)` just works, no lookup table
      needed.
- [ ] Net view: click a net -> list every pin on it (already in the manifest's `nets[]`), no need to
      touch the 3D model for this part.
- [ ] Multi-select / persistent highlight list (currently only one component highighted at a time).

### Phase 2 - live simulation - **DONE 2026-09-17** for reflex-machine
The frontend never simulates anything itself - it calls a real `wokwi-cli mcp` subprocess (the actual
Wokwi simulator, running the real compiled firmware) over MCP (JSON-RPC over stdio), through the backend.
This is the "separate tool working in the background, called via API" the user asked for, replacing an
earlier client-side JS reimplementation attempt (removed - see the bugs-found section for why).

- [x] `webview/server/wokwi_mcp.py` - `WokwiSession` spawns `wokwi-cli mcp .` in a project's Wokwi test
      folder, does the JSON-RPC handshake, exposes `start_simulation()`, `set_control()`, `read_pin()`,
      `get_status()`, `stop()`. Requires `WOKWI_CLI_TOKEN` in `server.py`'s own environment.
- [x] `webview/projects/<id>/wokwi_map.json` - the one new per-project file: which net maps to which
      Wokwi part id/control (inputs) or part id/pin (outputs). Purely config, no code.
- [x] `build_manifest.py` sets `manifest.live_sim = true` when a project has `wokwi_map.json` - the
      frontend uses this to decide whether to show Start/Stop and press/indicator controls at all.
- [x] New routes: `POST .../sim/start`, `POST .../sim/stop`, `POST .../sim/press {net}`,
      `GET .../sim/outputs`. One live session per project at a time, guarded by a lock.
- [x] **Every start/stop cycle spends the project's real Wokwi quota** - `stop` computes elapsed seconds
      and appends a row to that project's own `test/wokwi/USAGE_LOG.md` automatically (parses and
      rewrites the running-total summary line), keeping the existing quota-tracking convention as the
      single source of truth rather than a second, separate counter inside the webview.
- [x] Frontend: a global Start/Stop Simulation button (disabled unless `manifest.live_sim`), a "Press"
      button next to each input (enabled only while running), and a live status dot next to each output,
      polled every 400ms from `/sim/outputs` while running.
- [x] Verified fully end to end through the actual HTTP API (not just the MCP probe): start -> press
      BTN_S1 -> poll outputs (correctly all `false`, since S1 needs coin credit the test never gave it -
      real firmware behavior, not a bug) -> stop -> `USAGE_LOG.md` updated itself correctly (23s/3000s).

**Known limitations, honestly, not swept under the rug:**
- The 7-segment display (`SEG_DATA`) has no live readout - decoding the 74HC595 shift-register bit
  stream into a digit would need either polling all 3 control pins and reconstructing the byte
  client/server-side, or reading the `wokwi-7segment` part's own displayed value if the MCP tool schema
  ever exposes it. Not attempted yet.
- Magnet output reads (`read_pin` on a PWM pin) are approximate for the same reason documented in
  `docs/LESSONS_LEARNED.md` section 9 (a single sample lands at a timing-dependent point in the PWM
  waveform) - fine for a live "on-ish/off-ish" dashboard dot, not for a pass/fail assertion.
- Only one live session across the whole platform at a time (a global lock, not per-project) - fine for
  a single local user, would need real per-project session isolation to support two people/tabs at once.
- Coin input in the sim is a raw press/release pulse, not the real optocoupler's pulse-count-banded
  value logic (1-2 pulses=500, 3-5=1000, 6=2000) - pressing "Coin" once in the webview does not by itself
  give the firmware a counted value the way a real coin acceptor's pulse train would. Confirm the real
  coin behavior before relying on this for anything but wiring checks.

### Phase 2b - quota safety + UI fixes (2026-09-17, same day, user feedback after first click-through)
- [x] **Server-enforced time limit**, not just a client-side countdown: `POST /sim/start` accepts
  `{"limit_s": N}` (clamped 1-300s), and the backend itself schedules a `threading.Timer` that stops the
  session and logs it even if the browser tab is closed or misbehaves. The frontend also polls
  `GET /sim/status` every 300ms so its UI catches up if the timer fires server-side.
- [x] `GET /api/projects/<id>/sim/quota` - reads (never writes) the current month's used/remaining
  seconds from `USAGE_LOG.md`, shown in the topbar before and during a run.
- [x] Frontend: a "Limit (s)" number input next to Start Simulation (default 10), a live "running: X.Xs /
  limit" readout while active, and "quota: Xs / 3000s left this month" when idle.
- [x] **Layout bug fixed**: the Output Console was `position: fixed`, overlaying the bottom of the page
  instead of resizing it - opening it hid part of the dashboard/3D view with no way to see or reach it.
  Restructured to a real flex column (`#body-flex` wraps `main` + `#console`); opening the console now
  shrinks `main` (which the existing `ResizeObserver` on `#viewport` picks up automatically), so
  everything stays visible and reachable. Added `overflow: auto` on `html, body` as a fallback safety net.
- [x] **Zoom bug, round 1**: `controls.minDistance`/`maxDistance` had been derived from the camera's
  `near`/`far` clipping planes (a ~12,500x range). Decoupled zoom range from clipping planes -
  `minDistance = radius*0.15`, `maxDistance = radius*4`, plus a slower `zoomSpeed`. **This alone did not
  fully fix it** - see round 2, same day.
- [x] **Zoom bug, round 2 (the actual fix, 2026-09-17)**: round 1 used `camera.near = Math.max(radius/1000,
  0.1)` - an absolute floor of `0.1` "for safety". Checked the GLB's real bounding box
  (`accessors[].min/max` in its JSON chunk) and found KiCad's glTF export uses real-world **meters** -
  this board is ~0.26m, so `radius ≈ 0.2`, and `minDistance = radius*0.15 ≈ 0.03` is *smaller* than that
  `0.1` near-plane floor. OrbitControls would happily dolly the camera closer than the near-clipping
  plane, so the model vanished in that dead zone - the exact same "disappears when you zoom in" bug as
  the original report, reintroduced by an absolute floor that looked safe for a "normal" 1-100-unit scene
  but wasn't for this sub-1-unit-scale model. **Fixed**: removed the floor entirely (`camera.near =
  radius / 1000`, no `Math.max`), and tightened `far` from `radius*100` to `radius*10` to keep the
  far/near depth-precision ratio reasonable now that `near` can be very small in absolute terms.
  **Lesson for any future project**: never assume a scene's absolute scale - always check a GLB's real
  bounding box before picking "safe-looking" absolute numbers for near/far/min/max; derive everything
  from the model's own measured `radius` instead, with no absolute floors or ceilings.
### Phase 2c - output-reading noise + a real limitation found (2026-09-17, same day)
User reported all-together-held magnets flickering randomly on/off with no clear pattern after pressing
RST. Root causes, both fixed or documented:
- [x] **Slow, staggered polling**: `/sim/outputs` read all 14 nets with 14 *sequential* MCP round-trips,
  taking seconds per poll instead of the intended 400ms, so different magnets were sampled seconds apart
  from each other. Fixed with `WokwiSession.read_pins_batch()` - pipelines every read over the single
  stdio connection (fire all requests, then collect all responses by id) instead of waiting for each one.
- [x] **PWM sampling noise**: magnets are held with `analogWrite(PWM_PINS[i], PWM_ON)` where
  `PWM_ON = 100/255` (~39% duty) - a genuine PWM wave, not a steady HIGH. A single instantaneous digital
  read has a ~61% chance of catching the LOW phase, independently per magnet per poll - exactly the
  "random" flicker reported. Fixed with `read_outputs_debounced()`: 6 rapid pipelined samples per poll,
  OR'd together (a magnet reads "on" if *any* of the 6 samples caught it high; a genuinely-off magnet
  never does). **Verified**: 4 consecutive real polls after RST now show all 10 magnets + LED1 solid ON,
  zero flicker (previously flickered on every poll).
- [x] **Also found (during the same debugging session): pressing a speed button without enough coin
  credit correctly does nothing** - that's real firmware behavior (`coinSum >= threshold` check), not a
  bug. The original bug report's "chaotic release-looking" flicker was actually the RESET-held state
  (never left it - S3 needs 2000 credit, only 1000 was given) being sampled unreliably, not a broken
  release sequence.
- [x] Attempted **live 7-segment digit decode** (read the 74HC595's Q1-Q7 output pins, decode to a digit)
  in response to "we have countdown and 7-seg, remember?" - built `decode_seven_segment()` and a
  `"display"` spec shape in `wokwi_map.json`, then **found a real tooling limitation** empirically:
  sampling the segment pins repeatedly across a known, stable 700ms blink cycle showed a slow "walking
  ones" pattern over ~2 real seconds instead of two stable states - i.e. synchronous `wokwi_read_pin`
  calls over MCP do not sample a consistent simulated instant for a rapidly-changing signal like a shift
  register; each call appears to nudge the simulation's virtual clock forward unpredictably between
  calls. **Reverted**: removed the `"display"` entry from `reflex-machine/wokwi_map.json` (the `.io-digit`
  UI element and `decode_seven_segment()` code stay in place, unused, for whenever this MCP behavior is
  better understood or a different read strategy is found) rather than ship a UI that shows `"?"`. Do not
  re-add live 7-segment decode without first re-verifying pin reads are stable against a known-static
  signal (a status LED, not a shift register) as a sanity baseline.

- [x] **Plain-language activity feed** ("Pressed S1", "Magnet 3 &rarr; ON") in a small always-visible
  panel above Inputs/Outputs - not another drawer to open. **Needs zero new per-project config**: it's
  built purely from the manifest's own `io[].label` values (already required for every project) and by
  diffing each `/sim/outputs` poll against its previous value, so any project with `wokwi_map.json`
  wired up gets this automatically. Logs a line on every Press click and on every output value change
  (skips the very first poll after start, so it doesn't spam "OFF" for every net just because their
  prior state was unknown).

### Phase 1b - visual + interaction upgrade (2026-09-17)
User: *"is there a way to make the LED in the 3D view turn on too? visual presentation, not just in the
side?"* and *"better view, better design, more interactive."*
- [x] **Real components light up in 3D.** When an output goes high, that component's mesh gets an
  emissive glow - an actual LED glowing on the board, not only a dot in the side panel. Colour is taken
  from the component's own value (`RED`/`GREEN`/`BLUE`/...), defaulting to warm yellow.
  **Generic**: the GLB names each node after its reference designator and `io_map.json` already carries
  the ref per output, so this needs no new per-project data.
  **Gotcha handled**: KiCad's GLB **shares materials between components** (uno-toggle has 8 parts but
  only 6 materials), so lighting one LED would light every part sharing that material. Each mesh's
  material is cloned once on first touch, and its original emissive stored for restoring.
- [x] **Click a part in the 3D view** to select it: highlights it, logs what it is (ref, value,
  footprint) to the activity feed, and scrolls + flashes the matching dashboard row. Dashboard rows
  route through the same `selectRef()`, so both directions stay in sync. Drags are ignored (moving the
  camera must not select).
- [x] **Better lighting**: ACES filmic tone mapping + sRGB output, and a key/fill/rim light set, so the
  board reads as a solid object and an emissive LED visibly glows. Canvas is now `alpha: true` over a
  CSS radial vignette instead of a flat scene colour, plus grab/grabbing cursors.

### Phase 1c - extensible input types (2026-09-17)
User: *"if we have different input format we should be able to add that, not just press - maybe analog
values"* and *"that's why I asked for the project to be scalable - maybe sound in the future, a sound
sensor, a speaker out."*
- [x] **`POST /sim/input {net, value}`** - generic: sets a simulator control to **any number** and leaves
  it there. `/sim/press` stays as the momentary special case (pulse + release). Wokwi's `set_control`
  already took a number, so analog needed no new simulator plumbing.
- [x] **Widget registry in `app/main.js`** (`INPUT_WIDGETS` + `INPUT_TYPE_ALIASES`): `momentary` →
  Press button, `toggle` → latching ON/OFF, `analog` → slider with a live value readout (throttled to
  ~120ms while dragging, since every send is a real round trip). Optional `min`/`max`/`step`/`default`/
  `unit` come from `io_map.json`.
- [x] **Adding a new input kind is one registry entry** - no backend, no per-project code. A sound
  sensor is just `type: "sensor"` with a range today.
- [x] Verified against the real simulator: `/sim/input` with `1` held BTN1 down (firmware toggled its
  LED), `0` released it (LED correctly stayed on - it's a toggle), and a non-numeric value was rejected
  with a clean `400`, not a crash.
### Phase 1d - pulse injection, serial, and editable io types (2026-09-17)
Driven by a real debugging session: the reflex machine's coin acceptor never registered credit, so the
game could never start. Root cause of the *modelling*: **a coin acceptor is not a button.** Its firmware
counts EDGES INSIDE A 300ms WINDOW (1-2 pulses=500, 3-5=1000, 6=2000, 7+ discarded), and every UI click
is a separate HTTP + MCP round trip landing 100s of ms apart - so each click read as its own 1-pulse coin.
- [x] **`POST /sim/pulse {net, count}`** + `WokwiSession.pulse_burst()` - injects the whole burst
      atomically, pipelining every `set_control` before reading any response, and **returns `burst_ms`**
      so you can see whether the burst actually fitted the firmware's window. Measured: 3 pulses in 180ms.
- [x] **`pulse` input type** (aliases: `coin`, `encoder`, `flow`, `tacho`, `counter`) - a pulse-count box
      plus an **Inject** button. Generic for any pulse-counting sensor.
- [x] **`POST /sim/serial {text}`** + `write_serial`/`read_serial` - drive firmware that takes UART
      commands (this board accepts `SET:PAYMENT` / `SET:SPD1` / `D`). **Caveat**: Wokwi's write_serial
      targets the primary `Serial`; this board reads commands on `Serial1` (to the ESP32), so it won't
      reach this particular firmware. Useful for projects whose command channel IS the USB serial.
- [x] **Editable io type in the UI** - a per-input dropdown (momentary / toggle / analog / pulse) that
      **persists**: `POST /api/projects/<id>/io {net,type}` writes it back to both `io_map.json` (the
      human source of truth) and `manifest.json` (what the frontend reads). You usually only discover
      something is a pulse input by watching it misbehave, so it shouldn't require editing files by hand.
- [ ] **UNRESOLVED**: even a 180ms 3-pulse burst did **not** produce coin credit (S1 stayed refused,
      LED1 still on). Coin credit does not accumulate in simulation by any method tried: 6 spread
      clicks, 4 spread clicks, or one atomic burst. Next thing to check is the coin ISR itself -
      `attachInterrupt(digitalPinToInterrupt(2), coinISR, FALLING)` on a **Mega** is a known-subtle
      pin↔INTn mapping (pin 2 is INT4, while `digitalPinToInterrupt(2)` returns 0). **Verify on real
      hardware before treating it as a firmware bug** - it may equally be that Wokwi's pushbutton model
      doesn't drive the AVR external-interrupt path. Do not assert either way without evidence.

- [ ] **Still to do for true "sound in/out"**: an output renderer for a speaker/buzzer (the data model
  already supports it - it needs a widget next to the LED dot and 7-seg digit), and a decision on
  whether audio should be *sonified in the browser* or just shown as a waveform/level.

### Phase 1e - seven platform upgrades (2026-09-17, "do them all")
All seven built. Verified means: run live against a real simulation, not just "the route returns 200".
- [x] **Serial console** - `GET /api/projects/<id>/sim/serial` + an Output/Serial/Analyzer tab strip in
      the console panel, polled while running. **Verified live** on reflex-machine; it correctly returned
      `{"text": "No serial output", "running": true}`, which is the *right* answer for this board - see
      the `Serial1` caveat in Phase 1d. Test it on `uno-toggle` or any USB-serial project to see text.
- [x] **VCD waveform analyzer** - `webview/server/vcd.py` (stdlib VCD parser -> `duty_pct`, `edges`,
      `freq_hz`, `state` per signal) + `POST /sim/capture` + a table in the Analyzer tab. This is the
      only honest way to read a PWM pin; single-sample pin reads are what produced the phantom
      "magnets flickering" bug earlier in the day.
      **First live test failed**: the tool reported success and wrote no file. Cause: Wokwi's VCD export
      only dumps signals wired to a **`wokwi-logic-analyzer`** part, and the diagram had none. Added one
      with `D0..D7` on the magnet + status pins -> **verified live**: 7.6s captured, 8 channels parsed,
      all reading 0% duty at idle (correct - nothing is driven before RESET). Written up as lesson 9.
- [x] **Scenario recorder** - a Record button collects clicks and `POST /api/projects/<id>/scenario`
      writes a Wokwi scenario YAML next to the diagram, turning a manual click-through into a headless
      regression run. Matters directly because simulation time is metered. *Built, not yet live-tested.*
- [x] **DRC/ERC service** - `webview/services/drc/` runs KiCad's own `kicad-cli pcb drc
      --schematic-parity` / `sch erc` on the project's real files. **Verified live**:
      `ok: true | DRC errors: 0 | ERC: 0 errors` for uno-toggle through `/api/services/drc/run`, and
      **with zero changes to the core server or frontend** - which is the actual proof that Phase 4's
      service architecture works as intended.
- [x] **Buzzer / tone output** - output type plus a WebAudio `playTone()` so a speaker pin is audible,
      not just a dot. *Built, not live-tested.*
- [x] **Display screenshot output** - `POST /sim/shot` + `take_screenshot`, for LCD/OLED parts whose
      state can't be read off pins at all. *Built, not live-tested.*
- [x] **Net highlighting** - clicking a net highlights every component on it. Highlights *components*,
      not copper: the GLB deliberately carries no trace geometry.

### Phase 3 - scale-proofing - **DONE 2026-09-17**
- [x] **A genuine genericity bug was found and fixed first.** Both generators hard-failed
      (`raise SystemExit`) without `projects/<id>/gen/netlist.py` - this workspace's *bespoke* convention.
      That meant no normal KiCad project (drawn in the GUI, imported, downloaded) could be onboarded at
      all: the runtime was generic, the onboarding tooling was not. Fixed with `tools/kicad_pcb.py`, a
      stdlib s-expression reader for `.kicad_pcb` - a file EVERY KiCad project has. `build_manifest.py`
      now uses `netlist.py` when present and falls back to the PCB otherwise.
      Verified equivalent on the same board: **both paths give 110 nets, and all 20 `io_map.json` nets
      resolve** (the PCB path additionally reports 2 mounting holes, which netlist.py doesn't model).
- [x] **Second project onboarded, with zero `server/`/`app/` changes**: KiCad's own bundled
      `pic_programmer` demo - a genuinely third-party project with no relationship to this workspace.
      63 components, 34 nets parsed straight from its `.kicad_pcb`; GLB exported; icons cached; dashboard
      populated from a hand-written `io_map.json`; served live by the unchanged backend with
      `live_sim: false` (it has no `wokwi_map.json`, so the Start Simulation button correctly disables).
- [x] **Icon cache dedup confirmed**: onboarding the second project exported 3 new symbols and **reused 3
      already cached** from the first project.
- [x] **One-command onboarding**: `python webview/tools/onboard.py <id>` - export GLB, cache icons,
      scaffold `io_map.json`/`actions.json` stubs, build manifest. Replaces the old 7-step manual recipe.
- [x] `build_manifest.py` now warns about `io_map.json` nets that don't exist on the board (typo catcher)
      and about an empty dashboard.

### Phase 4 - separate tools talking over APIs (architecture set 2026-09-17)
The user's direction: *"make it scalable, we can add more features later, make it separate tools running
on their own, that they talk with APIs."* The seam for this now exists and is **proven working**.
- [x] `server/services.py` - a service registry + proxy. Drop a `service.json` in
      `webview/services/<name>/` and the core exposes `/api/services` and proxies
      `/api/services/<name>/*` to `http://127.0.0.1:<port>/*`. See `API.md` for the full contract.
- [x] `webview/services/echo/` - a ~40-line working reference service. **Copy it to start a new one.**
- [x] Verified end to end: registry reports a down service honestly (short timeout, no UI hang), the
      proxy returns a useful error naming the port and start command instead of crashing, and once
      started, both GET and POST proxy through correctly with the request body preserved.
- [ ] Migrate/add real capabilities as services (SPICE runner, DRC runner, BOM pricing, design-review
      agent, firmware builder). **The core's own jobs are only** static files, the project registry,
      declared actions, and the Wokwi bridge - if a new feature wants to edit `server/server.py`, it
      almost certainly wants to be a service instead.

### Phase 5 - the actual goal: one prompt -> a whole board
The user's stated end goal: *"one prompt would allow me to generate a full design + full PCB + testing +
debugging + platform for view and simulation running."* Honest status of that:

**Already one command** (`python pipeline.py <project-id>`, at the workspace root): schematic -> netlist
compare + ERC -> place -> route -> finish -> DRC/parity -> fab outputs -> firmware pin cross-check ->
webview onboarding. It auto-skips stages a project doesn't have, so an imported `.kicad_pcb` runs only
the `webview` stage while a scripted project runs everything. Verified on both project types.

**Still the prompt's job** (genuine engineering judgement + a conversation, not something a script can
invent) - three files:
  - `projects/<id>/DESIGN_BRIEF.md` - what the board must do, and the decisions behind it
  - `projects/<id>/gen/netlist.py` - every part and connection (the single source of truth)
  - `webview/projects/<id>/io_map.json` - which nets are inputs/outputs and what to call them

So the realistic shape of the goal is **"one prompt writes those three files, then one command does all
the rest"** - and that is now true. Remaining work to make it feel like a single step:
- [ ] A `pipeline.py --new <id>` that scaffolds a project skeleton (brief template + netlist stub) so the
      prompt has a fixed target to fill in.
- [ ] Wire the test stages (SPICE, Wokwi lint/scenarios) into `pipeline.py` as services per Phase 4, so
      "testing + debugging" is part of the same one command rather than a separate procedure.
- [ ] Decide what `pipeline.py` should do on a board that is already finished and verified: today it
      would happily re-route it. It should refuse, or require `--force`, rather than silently redoing
      routing on a board someone already signed off.

### Phase 6 - SPICE simulation for boards with no MCU - **DONE 2026-09-18** (blinky-555)
Wokwi only runs firmware, so a board with no microcontroller (555 flasher, analog filter, power stage)
had no simulation at all. It now simulates through LTspice, inside the same webview.
- [x] `tools/boardgen/make_spice.py <id>` - shared pipeline stage (`spice` in `pipeline.py`). Builds an
      LTspice deck from the same `netlist.py` as the schematic/PCB, runs it, parses the binary `.raw`,
      measures each probe (freq, high/low ms, duty, levels) + every LED's current, checks the project's
      `expect` targets, writes `projects/<id>/test/spice/transient.json`. Opt-in per project with a
      `SPICE = {supplies, tstop, probes, expect}` block in `netlist.py`.
- [x] `webview/services/spice/` (port 8801) - `POST /run {project, supplies}` / `GET /result`. Added
      **with zero changes to `server/server.py`** - the second proof of the Phase 4 service seam.
- [x] Manifest gets `spice_sim` + default supplies. The frontend's button becomes **Run SPICE**, then
      replays the transient **in real time**: the output's part glows in 3D, a new `voltage` output type
      shows a node voltage live, and the Analyzer tab draws every waveform with a moving playhead.
      An `analog` input on a supply net becomes a run parameter (blinky: 9-12 V slider).
- [x] Verified in a real (headless Edge, CDP-driven) browser: no JS errors; LED toggles at the simulated
      395/326 ms; 12 V on the slider reaches LTspice (LED current 14.8 -> 21.1 mA, frequency unchanged -
      correct for a 555). blinky-555: **1.385 Hz / 54.8 % duty, matching the hand calculation**.

**Honest limitations:**
- It is a **recorded** simulation played back, not an interactive one - changing an input means a new
  run (~1 s). Fine for a board with no buttons; a board with a switch you flip mid-run would need
  LTspice PWL sources built from a recorded input timeline.
- Parts supported today: R, C (incl. polarised), LED, diode, the 555 family. Anything else is a **hard
  error**, never silently dropped. Add models in `build_circuit()`.
- The LED is a generic model (Vf ~1.95 V at 15 mA), LTspice's NE555 is "idealised" - timing is right,
  output drive/rail details are approximate.

## Bugs found and fixed after the fact (read before assuming the platform is stable)
- **Mouse wheel zoom jumped straight to min or max, no intermediate levels (2026-09-17) - FIXED, and it
  was not what three rounds of guessing assumed.** Two separate real causes, found only after adding a
  live zoom readout so the symptom became falsifiable:
  1. *No cache headers* (see the next entry) meant earlier fixes were never actually loaded by the browser.
  2. The real zoom bug: three.js r160+ `OrbitControls` scales the camera distance by
     `0.95 ^ (zoomSpeed * |deltaY| * 0.01)` - **proportional to the deltaY the mouse driver reports**.
     Free-spin / "smooth scrolling" wheels report deltaY in the thousands per notch instead of ~100,
     making a single notch a 10x+ jump straight to a clamp. `zoomSpeed` cannot fix this: the magnitude is
     hardware/driver dependent, so any value that feels right on one machine is wrong on another.
     **Fix**: `controls.enableZoom = false` and drive zoom ourselves from the wheel's **sign only**, with
     a fixed 8% step per notch (`zoomByNotches()` in `app/main.js`) - identical behaviour on every
     machine, ~78 intermediate levels across the min..max range. Confirmed working by the user.
     Also exposed as +/- buttons in the topbar using the same code path.
     **Lesson: never trust `deltaY` magnitude from a wheel event; use its sign and apply your own step.**
- **The frontend was being served with NO cache headers (2026-09-17) - this silently wasted three rounds
  of zoom "fixes"**. `server.py`'s `_send_file()` sent no `Cache-Control`, no `ETag`, no `Last-Modified`,
  so browsers heuristically cached `main.js`/`style.css` and kept running the OLD code across normal
  refreshes. Every frontend fix appeared to do nothing, which sent the debugging off chasing imaginary
  OrbitControls problems. **Fixed**: `_send_file()` now always sends
  `Cache-Control: no-store, no-cache, must-revalidate`. **If a frontend change ever seems to have no
  effect, verify what the browser is actually running (`curl -D - .../main.js`, and hard-refresh once)
  BEFORE theorising about the code.** Note a hard refresh (Ctrl+Shift+R) is still needed once to evict a
  copy cached before this fix landed.
- **Client-side JS "simulation" reimplementation, built then removed (2026-09-17)**: an early attempt at
  interactivity ported the firmware's state machine into a `sim.js` run entirely in the browser (free,
  instant, but not real). The user correctly redirected this: the platform should call the *real*
  testing tool (Wokwi) via API, not reimplement its logic - see Phase 2 above for what replaced it. If
  you find a stray reference to a per-project `sim.js` "simulation" field anywhere, it's stale - the
  live mechanism is `wokwi_map.json` + `live_sim`, not a JS plugin file.
- **"Every input/output showed the same icon" (2026-09-17)**: the frontend's fallback ref-inference
  (`findRefForNet` in `main.js`, used when `io_map.json` doesn't set `ref`) picked the alphabetically
  first `ref.pin` string touching a net. Since the Arduino Mega's own ref happens to be `A1` (and the
  ESP32 `A2`), and nearly every net in a microcontroller-based board eventually touches the MCU, this
  fallback resolved almost every dashboard entry to the Mega's own icon. **Fix applied**: added explicit
  `ref` to every entry in `reflex-machine/io_map.json` (the button connector `J13`, the optocoupler `U2`,
  each magnet's driver MOSFET `Q1..Q10`, the status-LED connector `J14`, the shift register `U3`) and
  changed `main.js` to prefer `item.ref` over the inferred fallback. **When onboarding a future project,
  always set `ref` explicitly per io entry - never rely on the fallback**, it will silently produce the
  same bug again for any board with a central MCU.

## Open questions / risks to flag to the user before assuming an answer
- ~~GLB mesh-naming convention unconfirmed~~ - **resolved 2026-09-17**, see Phase 1 above.
- ~~32MB model too heavy~~ - **hit a real bug from this 2026-09-17**: the first export used
  `--include-tracks --include-pads --include-zones --include-silkscreen --include-soldermask`, producing
  **30,594 separate primitives / ~1.38M vertices** - one tiny mesh per pad/silkscreen line. In the
  browser, zooming in made the whole model disappear. Two separate causes, both fixed:
  1. **Real bug regardless of model weight**: the camera had no `near`-plane safety margin and
     `OrbitControls` had no `minDistance` - zooming closer than `camera.near` clips everything. Fixed in
     `app/main.js` `frameModel()` (near = `radius/1000` not `radius/100`, `far` = `radius*100`,
     `controls.minDistance`/`maxDistance` now set).
  2. **Draw-call/GPU-driver-timeout risk independent of GPU power**: 30k+ primitives means 30k+ WebGL
     draw calls per frame; Windows' GPU driver timeout (TDR, ~2s) can kill the WebGL context if the
     driver can't submit that many calls fast enough - this is an API/driver overhead problem, not
     something a faster GPU alone fixes. **Re-exported without `--include-pads/--zones/--silkscreen`**
     (board body + component 3D models only, same as KiCad's own default 3D viewer) -> 6,768 primitives,
     143K vertices, 3.8MB. Not yet re-tested by the user in-browser after this fix - do that next.
     If they want the full copper/pad/silkscreen detail back for visual fidelity despite the resource
     cost, the fix then is to **merge primitives** (e.g. `BufferGeometryUtils.mergeGeometries` per
     material in Three.js, or re-export and post-process with a glTF optimizer like `gltfpack`/`gltf-transform`)
     rather than just re-adding the heavy flags - don't regress into the same bug.
- No decision yet on whether `server.py` should stay stdlib-only forever or whether a small dependency
  (e.g. Flask) is acceptable if the routing logic outgrows stdlib `http.server` - default to stdlib
  until it's genuinely painful, per this workspace's "don't add deps you don't need yet" pattern.
