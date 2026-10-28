# PCB workspace - start here

AI-assisted PCB design with KiCad. This file is the front door: it tells you which other file to
open for what you're trying to do. Don't read everything - jump to the row that matches your task.

| I want to... | Read |
|---|---|
| Understand the environment, installed tools, and what's set up | `CLAUDE.md` (auto-loaded every session) |
| See what MCP servers / Python tools / KiCad plugins exist and how to run them | `docs/TOOLING.md` |
| Build a **new** PCB project from scratch | `docs/NEW_BOARD_PLAYBOOK.md` - the **A-to-Z checklist** - then `docs/PCB_CREATION_GUIDE.md` (the tested procedure) |
| **A build failed and I need the fix** | `docs/PCB_CREATION_GUIDE.md` § "Failure catalogue" |
| Avoid mistakes already made once (KiCad 10 scripting traps, Freerouting quirks) | `docs/LESSONS_LEARNED.md` |
| Work on an **existing** project | that project's own `README.md` under `projects/<name>/` |
| **Order a board** (what the fab / price calculator asks) | that project's `MANUFACTURING.md` |
| **Check the connections without reading a PCB** | that project's `CONNECTIONS.md` - every pin, in words |
| View any board's real 3D layout + inputs/outputs in a browser | `webview/README.md` |
| **See the whole thing at a glance (pictures)** | `docs/diagrams/` — `workflow.svg`, `architecture.svg`, `status.svg` |
| **Actually run the scripts** (commands, stages, which Python) | "Running the scripts" below |

## Running the scripts

**One command does everything** (this is the normal path):
```bash
python pipeline.py uno-toggle            # full build: schematic -> place -> route -> checks -> fab files
python pipeline.py uno-toggle --list     # show which stages would run, change nothing
python pipeline.py uno-toggle --only place,route
python pipeline.py uno-toggle --skip route
```
Stages run in this order, and any that don't apply to a project are skipped automatically:

| Stage | What it does |
|---|---|
| `lint` | Design-rule lint of netlist.py (decoupling, polarity, LED resistors, shorts, pad/pin existence, registry use). Pure Python, <1 s. |
| `parts` | Registry parts vs live/cached LCSC + EasyEDA: MPN, footprint geometry, package, stock, freshness. |
| `sch` | Generate the schematic from netlist.py. |
| `sch-check` | Netlist compare (kicad-cli export vs netlist.py) plus ERC. |
| `place` | Footprints, board outline, silkscreen and pre-routed links. |
| `route` | Autoroute with Freerouting. |
| `finish` | Ground pours and stitching vias. |
| `check` | DRC including schematic parity - the gate before fab. |
| `ir` | Design IR (out/design.json): parts, nets, board geometry from netlist.py + .kicad_pcb; netlist-vs-board net cross-check; JSON-Schema validated. |
| `electrical` | Electrical rules EL-ABSMAX / EL-CONTENTION / EL-OD-PULLUP over out/design.json (runs after `ir`; NOT_JUDGED shown, never fails a hand board). |
| `review` | Design review (kicad-happy schematic/PCB/EMC analyzers + waivers.json): decoupling distance, EMC, power tree. |
| `outputs` | Gerbers, drill, BOM, CPL, STEP, schematic PDF and renders. |
| `lvs` | Independent connectivity of the fab zip itself (gerbers + drill), diffed against netlist.py. |
| `fabreport` | MANUFACTURING.md: size, layers, holes, parts, order-form answers. Read-only on the board. |
| `connections` | CONNECTIONS.md: every pin of every part and where its copper goes, in plain words. |
| `pinmap` | Firmware pin map vs netlist cross-check (enabled by a FIRMWARE block in netlist.py). |
| `spice` | Transient LTspice run of the whole board plus expected-vs-measured (enabled by a SPICE block in netlist.py). |
| `webview` | Export GLB, cache icons, build manifest, onboard to the viewer (works for any .kicad_pcb). |

Useful flags and checks: `--no-cache` (ignore the stage cache), `--describe <stage>`, `--explain RULE-ID`.
Each run writes a report to `projects/<id>/out/run/<ts>/report.html`.
```bash
python tools/ci_checks.py all
python tests/mutations/run_mutations.py --tier fast --jobs 4
python tools/parts.py            # parts registry CLI
```

`pipeline.py` **refuses to re-run design stages on a board that already has `out/fab`** — pass
`--force` if you really mean to rebuild a board that has been sent to fab.

**If you run a script directly, use KiCad's Python, not the system one:**
```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" make_pcb.py place
```
Everything touching `pcbnew` (`make_sch.py`, `check_sch.py`, `make_pcb.py`, `make_outputs.py`) only
imports inside KiCad's interpreter. System `python` gives `ModuleNotFoundError: No module named
'pcbnew'`. `pipeline.py` itself runs under system Python and picks the right interpreter per stage.

The generic stages are **shared**, in `tools/boardgen/` - one copy for every board. A project's `gen/`
holds only `netlist.py` and `make_pcb.py`. Run a shared stage directly by naming the project:
```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" tools/boardgen/make_sch.py blinky-555
```
KiCad's own location is resolved once in `tools/boardgen/kicad_paths.py` (set `KICAD_HOME` to override,
otherwise the newest install wins) - don't hardcode it anywhere else.

Two helpers that don't need KiCad's Python:
```bash
python tools/sym_pins.py Timer:NE555P     # a symbol's real pin numbers (follows `extends` aliases)
python tools/fp_bbox.py Package_DIP:DIP-8_W7.62mm   # a footprint's real extent around its origin
python projects/<id>/gen/netlist.py       # print the parts + nets, flagging single-pin nets
```

**The 3D platform** (details in `webview/README.md`):
```bash
python webview/server/server.py           # then open http://127.0.0.1:8787/  - Ctrl+C to stop
python webview/tools/onboard.py <id>      # add a board to the platform (GLB + icons + manifest)
```
Background services are separate processes the platform proxies at `/api/services/<name>/`. Start the
ones you want; the platform works without them:
```bash
python webview/services/drc/service.py    # DRC/ERC on demand, port 8802
python webview/services/spice/service.py  # SPICE simulation for boards with no MCU, port 8801
```

## Working offline (no internet)

**Designing and fabricating a board is 100% offline.** Simulation is the only part that isn't, and
there's a local substitute. Nothing here needs a login except Wokwi.

| Works offline | Why |
|---|---|
| KiCad + every `gen/` script, `pipeline.py` | local install, local symbol/footprint libraries |
| Freerouting autorouting | local Java app under `tools/freerouting/` |
| ERC / DRC / schematic parity | `kicad-cli`, local |
| Gerbers, drill, BOM, CPL, STEP, PDF, renders | `kicad-cli`, local |
| The webview 3D platform | server binds `127.0.0.1`; three.js is **vendored** in `webview/app/vendor/` |
| The `drc` service, `tools/sym_pins.py`, the `pinmap` stage | pure local Python |
| LTspice + the `spice` skill | local simulator |
| PlatformIO firmware builds | offline once the AVR + ESP32 toolchains are cached — they already are |

| Needs internet | Offline substitute |
|---|---|
| **Wokwi live simulation** (cloud service + metered token) | **Proteus 8** — installed on this machine. Build `firmware.hex` with PlatformIO, load it into a Proteus schematic. Note Proteus has no ESP32 model. |
| `easyeda2kicad` / LCSC part import | import the parts you need *before* going offline; they land in `projects/<id>/lib/` and stay there |
| `lcsc` / `digikey` / `mouser` / `element14` skills, datasheet fetch | cache datasheets into `projects/<id>/datasheets/` while online |

So an offline agent can do the whole board — netlist, schematic, place, route, DRC, fab files — and can
view it in the 3D platform. What it cannot do is press a button in the browser and watch real firmware
respond, because that runs on Wokwi's servers. Plan around it: **pull any external parts and datasheets
you need while you still have a connection**, since that's the only step that can't be redone later.

## Layout
```
PCB/
  CLAUDE.md          environment + status + session log (auto-loaded by Claude Code)
  README.md          this file
  docs/              workspace-wide reference (tooling, new-board playbook, lessons learned)
  webview/           generic local 3D viewer + dashboard platform for any project - see webview/ROADMAP.md
  .mcp.json          MCP server config (kicad, konnect)
  .claude/skills/    kicad-happy skills (design review, EMC, SPICE, BOM, distributors, fab prep)
  .venv/             Python tools (easyeda2kicad, skidl, kicad-skip)
  tools/boardgen/    SHARED board-generation stages used by every project
  tools/             sym_pins.py, fp_bbox.py + reference clones of external KiCad/EDA repos
  downloads/         installers (Konnect PCM, Freerouting)
  projects/          one subfolder per board - the actual work
```

## Projects
- `projects/reflex-machine/` - 10-magnet reflex/whack-a-mole game controller, Mega+ESP32 shield.
  Board design done and verified; a pre-fabrication testing pipeline is in progress.
  See `projects/reflex-machine/README.md`.
- `projects/uno-toggle/` - 2 buttons, 2 LEDs on an Arduino Uno R3 shield. Done and verified, including
  live simulation in the webview. The simplest worked example of the full pipeline.
  See `projects/uno-toggle/README.md`.
- `projects/blinky-555/` - standalone NE555 1 Hz LED flasher, 70x45 mm, 2-layer through-hole. Built as the
  pipeline's test case for a board with **no MCU** (own outline, own mounting holes, real VCC rail).
  0 errors / 0 unconnected / 0 parity. **Simulated in the webview with LTspice** (1.385 Hz, as designed).
  See `projects/blinky-555/README.md`.
- `projects/pic-programmer/` - **not ours.** KiCad's own demo board, kept as the regression test that the
  webview platform works for any project. See its README.

## Working style
Small steps, low token use: do one thing, show the result, ask before the next. Never hand-edit
generated KiCad files - fix the generating script instead.

## Capturing what you learn
Write down anything non-obvious as soon as you find it, at the level it belongs:
- **A trap that could bite the next board** (KiCad API quirk, tool install gotcha, a script bug and its fix) ->
  `docs/LESSONS_LEARNED.md`.
- **A finding specific to one pipeline stage** (a test result, a measured value, why an approach was
  dropped) -> that stage's own file, e.g. `projects/<name>/test/<stage>/REPORT.md`.
- **A decision or open question specific to one project** -> that project's `HANDOVER.md`.
- **Anything that changes the workspace setup or a project's status** -> `CLAUDE.md` status + session log.
Keep it terse and factual - the goal is that a fresh session picks up exactly where you left off
without re-deriving what you already figured out.
