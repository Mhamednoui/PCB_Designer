# Webview platform - API and background work

What every endpoint does, what runs in the background, and exactly which files a project needs.
Companion to `ROADMAP.md` (why things are the way they are) and `README.md` (how to run it).

## The two processes

| | What it is | Knows about a project via |
|---|---|---|
| **Frontend** `app/` | Static HTML/JS/Three.js. Renders the 3D board, dashboard, activity feed, console. **Never simulates or tests anything itself.** | `manifest.json` only - never KiCad files, never `netlist.py` |
| **Backend** `server/` | stdlib-only Python HTTP server on `127.0.0.1`. Serves files, runs declared actions, drives the real Wokwi simulator. | `manifest.json`, `wokwi_map.json`, and whatever a project's `actions` declare |

From the user's side it's one application. Under the hood the frontend only ever talks HTTP to the
backend, and the backend shells out to the real tools. Keep that separation.

## HTTP API

### Read
| Method | Path | Returns |
|---|---|---|
| GET | `/` and `/<file>` | the frontend (`app/`). Always sent `Cache-Control: no-store` - see ROADMAP for why |
| GET | `/projects/<id>/<file>` | that project's static files, i.e. `model.glb` |
| GET | `/api/projects` | `[{id, name}]` - every folder under `webview/projects/` containing a `manifest.json` |
| GET | `/api/projects/<id>/manifest` | the project's manifest (components, nets, io, actions, `live_sim`) |
| GET | `/api/projects/<id>/log` | action-run history from `run_log.jsonl`, so reopening the console shows past runs |
| GET | `/api/projects/<id>/sim/status` | `{running, elapsed_s, limit_s}` - the server's own view of the session |
| GET | `/api/projects/<id>/sim/quota` | `{used_s, remaining_s, quota_s}` - read (never written) from `USAGE_LOG.md` |
| GET | `/api/projects/<id>/sim/outputs` | `{net: bool}` - live pin reads, pipelined + debounced (see below) |

### Write
| Method | Path | Does |
|---|---|---|
| POST | `/api/projects/<id>/actions/<action-id>` | runs one action **declared in that project's manifest** (never an arbitrary command from the browser), appends the result to `run_log.jsonl` |
| POST | `/api/projects/<id>/sim/start` | body `{limit_s}` - spawns a real `wokwi-cli mcp` session. **Spends real Wokwi quota from here until stop.** |
| POST | `/api/projects/<id>/sim/stop` | stops it, computes elapsed, **writes a row to the project's `test/wokwi/USAGE_LOG.md`** |
| POST | `/api/projects/<id>/sim/press` | body `{net}` - pulses that input's control (press, 80ms, release). Momentary inputs only |
| POST | `/api/projects/<id>/sim/input` | body `{net, value}` - sets that input's control to **any number** and leaves it there. This is the generic one: toggles, potentiometers, sensor readings |

### Adding a new kind of input (analog, sensors, ...)
Inputs are **not** hardcoded to buttons. An input's `type` in `io_map.json` selects its widget, and the
backend already passes any number through to the simulator's control, so most new input kinds need
**no backend change at all**.

| `type` in io_map.json | Widget | Sends |
|---|---|---|
| `button`, `coin`, `push`, `momentary` | Press button | pulse via `/sim/press` |
| `toggle`, `switch`, `latching` | ON/OFF button that stays | `/sim/input` with `0` or `1` |
| `analog`, `pot`, `potentiometer`, `slider`, `sensor` | Slider + live value readout | `/sim/input` with the number |

Analog entries accept optional `min`, `max`, `step`, `default`, `unit`:
```json
{ "net": "MIC_OUT", "type": "sensor", "label": "Microphone level",
  "ref": "U2", "min": 0, "max": 1023, "step": 1, "unit": "adc" }
```
To add a genuinely new widget (a keypad, an XY pad, a waveform picker), add one entry to
`INPUT_WIDGETS` in `app/main.js` and one alias in `INPUT_TYPE_ALIASES`. Nothing else changes.

**Outputs** are the mirror image: `type: "led"` renders a lit/unlit dot **and glows the real component
in the 3D view**, `type: "seven-segment"` renders a digit readout. A future speaker/buzzer output would
be a new renderer next to those - the data (`io_map.json` + `wokwi_map.json`) already carries everything
it needs.

## Background work (things running outside a request)

1. **`wokwi-cli mcp` subprocess** (`server/wokwi_mcp.py`) - the real Wokwi simulator running your real
   compiled firmware. Spoken to over MCP (JSON-RPC on stdio). One session per project at a time, guarded
   by a lock because it's a single stdio pipe. A reader thread pumps its stdout into a queue.
2. **Auto-stop timer** (`threading.Timer`) - started with the session when `limit_s` is given. Stops and
   logs the session even if the browser tab is closed. This is why a session can never quietly burn quota.
3. **Action subprocesses** (`server/actions.py`) - `kind: "script"` actions run with a 60s timeout;
   `kind: "file"` actions just read a file. Only ever what the manifest declares.
4. **Frontend polling** (while a simulation runs) - `/sim/outputs` every 400ms, `/sim/status` every 300ms.
   Both stop on stop/auto-stop.

### Why output reads are pipelined and debounced
`/sim/outputs` does **not** read pins one at a time, and does not take a single sample:
- **Pipelined**: all pin reads are written to the MCP pipe before collecting any responses. Reading 14
  nets sequentially took seconds per poll and sampled different nets seconds apart from each other.
- **Debounced (6 rapid samples, OR'd)**: PWM-driven outputs (`analogWrite`) are a real square wave, so a
  single instantaneous read is a coin flip. Six quick samples reliably catch an energised output while a
  genuinely-off pin never reads high in any of them.

## Adding new capabilities: services, not core changes

The core backend is deliberately small and **should stay that way**. Every capability added from here on
(SPICE runner, DRC runner, BOM/pricing, an AI design-review agent, a firmware builder, …) is its own
process with its own HTTP API, registered with the core, which only proxies to it.

| Method | Path | Does |
|---|---|---|
| GET | `/api/services` | every registered service + whether it's currently up (short timeout - a dead service must never hang the UI) |
| GET/POST | `/api/services/<name>/<anything>` | proxied to `http://127.0.0.1:<port>/<anything>` |

Register one by dropping `webview/services/<name>/service.json`:
```json
{ "name": "spice", "port": 8801, "health": "/health",
  "description": "Runs SPICE testbenches", "start": ["python", "service.py"] }
```

**`webview/services/echo/` is a working reference implementation** - copy that folder to start a new
service. It's ~40 lines and honours the whole contract.

Contract every service honours:
- listens on `127.0.0.1` only (local toolchain, never a network service)
- exposes its health path, 2xx when ready
- speaks JSON
- owns its domain completely - the core knows *where* it lives, never *what* it does

Services start/stop independently of the core, so one can crash, be restarted, or be rewritten in a
different language without touching anything else. If a service is down, the core returns a clear error
naming the service, its port and its start command - it does not crash or hang.

**Rule of thumb: if you're about to add a feature by editing `server/server.py`, it probably wants to be
a service instead.** The core's own jobs are only: static files, the project registry, declared actions,
and the Wokwi bridge.

### Existing services
| Service | Port | What it does |
|---|---|---|
| `drc` | 8802 | `POST /run {project}` - KiCad DRC (+ parity) and ERC on the real files |
| `spice` | 8801 | `POST /run {project, supplies?}` - LTspice transient of the board's netlist, returns metrics + waveforms; `GET /result?project=` - last run. The simulation backend for boards with no MCU |
| `echo` | - | reference implementation to copy |

## SPICE mode (boards with no microcontroller)
If `netlist.py` has a `SPICE = {...}` block, the manifest carries `spice_sim: true` and `spice.supplies`.
The frontend then shows **Run SPICE** instead of Start Simulation (Wokwi wins if a project has both),
calls the `spice` service, and replays the result in real time - outputs are thresholded at the midpoint
of their settled levels, `type: "voltage"` outputs show the node voltage, `analog` inputs on a supply
net become run parameters. Offline, no quota. Start the service first: `python webview/services/spice/service.py`.

## What a project needs

Under `projects/<id>/` (the real KiCad work) and `webview/projects/<id>/` (this platform's view of it):

| File | Where | Required? | Who writes it |
|---|---|---|---|
| `*.kicad_pcb` | `projects/<id>/` | **Yes** - or `gen/netlist.py` | KiCad / the design step |
| `gen/netlist.py` | `projects/<id>/` | Optional | this workspace's scripted pipeline. If present, gives richer data (real schematic symbols, functional groups) |
| `model.glb` | `webview/projects/<id>/` | **Yes** | generated by `onboard.py` |
| `manifest.json` | `webview/projects/<id>/` | **Yes** | generated - **never hand-edit** |
| `io_map.json` | `webview/projects/<id>/` | Needed for a non-empty dashboard | **a human/AI judgement call** - which nets are inputs vs outputs, and their labels |
| `actions.json` | `webview/projects/<id>/` | Optional | points at existing reports/scripts to expose in the Output Console |
| `wokwi_map.json` | `webview/projects/<id>/` | Optional - enables live simulation | maps nets to Wokwi part ids/pins; needs a working Wokwi setup in `projects/<id>/test/wokwi/` |
| `run_log.jsonl` | `webview/projects/<id>/` | Auto | created at runtime |

**Onboarding any project is one command**: `python webview/tools/onboard.py <id>` (export GLB → cache
icons → scaffold stubs → build manifest). Adding a project must never require editing `server/` or
`app/`; if it does, that's a genericity bug - fix the generator, don't special-case the project.

### Two design sources, one manifest
`build_manifest.py` reads whichever the project has:
- `gen/netlist.py` → exact schematic symbols, so icons are the real part symbols, plus functional groups.
- **any `.kicad_pcb`** → components, values, footprints and nets parsed directly (`tools/kicad_pcb.py`),
  with icons falling back to generic per-reference-prefix symbols (R→`Device:R`, Q→`Device:Q_NMOS`, …).

Verified equivalent on the same board: both paths produce **110 nets** and all `io_map.json` nets resolve
(the PCB path also reports the 2 mounting holes, which `netlist.py` doesn't model as parts). The PCB path
normalises KiCad's hierarchical `/NET` prefixes and drops its auto-generated `unconnected-(...)` nets, so
net names match either way.
