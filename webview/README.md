# PCB Webview Platform

A local, generic viewer for any board in this workspace: a real 3D render of the actual PCB (exported
from KiCad) plus a dashboard of every input/output, and an Output Console that runs the testing tools
already built elsewhere in this workspace and shows their results. It does **not** run tests or build
PCBs itself - see `ROADMAP.md` for the full architecture and what's still open.

## Run it
```
cd webview/server
python server.py           # binds 127.0.0.1:8787 only
```
Then open **http://127.0.0.1:8787/** in a browser. Stop with Ctrl+C (or, on Windows, find the PID with
`netstat -ano | grep :8787` and `taskkill //PID <pid> //F` if it's backgrounded and Ctrl+C doesn't reach
it).

Do **not** open `app/index.html` directly (`file://`) - the model and manifest fetches need the server.

**For live simulation (Start/Stop buttons on a project with `wokwi_map.json`)** the server needs your
Wokwi token. Save it **once**, as a Windows user environment variable (kept in your Windows account, never
in a project file). In PowerShell:
```
[Environment]::SetEnvironmentVariable('WOKWI_CLI_TOKEN', '<your token>', 'User')   # https://wokwi.com/dashboard/ci
```
The server reads it from there on every Start Simulation (`wokwi_mcp._load_saved_token()`), so it works
even from a terminal opened before it was saved, and no restart is needed.
Every Start/Stop cycle spends that project's real Wokwi simulation-minute quota (free tier: 50 min/month)
- the backend logs each cycle automatically to that project's `test/wokwi/USAGE_LOG.md`.

**For boards with no microcontroller** (simulated with LTspice instead of Wokwi - offline, free):
```
python webview/services/spice/service.py     # port 8801, keep it running next to server.py
```
Then pick the project and press **Run SPICE**. See `API.md` "SPICE mode".

## Add a new project
1. Export its board: from the project's root, `kicad-cli.exe pcb export glb --force -o <out>.glb
   <project>.kicad_pcb` (board body + component 3D models only - **do not** add
   `--include-pads/--zones/--silkscreen`, that produced 30,000+ separate primitives and crashed the
   browser's WebGL context the first time - see `ROADMAP.md`'s "Bugs found and fixed" section).
2. `mkdir webview/projects/<id>` and copy the glb in as `model.glb`.
3. Write `webview/projects/<id>/io_map.json` by hand (see `ROADMAP.md` for the shape) - this is the one
   thing that can't be auto-derived: which nets are inputs vs outputs, what to call them, and (strongly
   recommended) an explicit `ref` per entry - see `ROADMAP.md`'s "same icon everywhere" bug for why the
   net-inference fallback alone isn't reliable.
4. Optionally write `webview/projects/<id>/actions.json` - point `kind: "file"` at any report the project
   already has (Stage 1/2/3 reports), `kind: "script"` at any cheap, already-existing script
   (`test/pinmap.py` and similar). Never invent new testing logic here - call what exists.
5. Optionally write `webview/projects/<id>/wokwi_map.json` (only if the project has a working Wokwi
   Stage 3 setup - `diagram.json`, real firmware, a `wokwi.toml` pointing at the compiled hex/elf) to get
   Start/Stop live simulation with press buttons and output indicators - see `ROADMAP.md`'s Phase 2 for
   the shape and `wokwi_mcp.py` for how it's driven. This is real Wokwi quota every time it runs.
6. `python webview/tools/build_icon_cache.py <id>` then `python webview/tools/build_manifest.py <id>` -
   both are generic, no per-project code to write or edit.
7. Restart the server (or just refresh the browser - the project picker re-reads `webview/projects/`
   on every page load) and pick the new project from the dropdown.

No file under `webview/app/` or `webview/server/` should ever need editing to add a project. If it does,
that's a bug in the generic design - fix the generator/backend, don't special-case the new project.

## Status (2026-09-17)
**Phases 0-2 done for `reflex-machine`.** 3D view (Three.js, real GLB, orbit controls + iso/top/bottom
presets, click-to-highlight any component), dashboard with real KiCad-derived icons, Output Console wired
to 4 free actions, and **real live simulation**: Start/Stop buttons spin up an actual `wokwi-cli mcp`
session running the real compiled firmware, a Press button next to each input calls the real simulated
button, and a live status dot next to each output polls the real pin state - all through the backend, the
frontend never simulates anything itself. Verified end to end through the real HTTP API (not just a
probe): start -> press -> poll -> stop, with the quota-spend automatically logged to
`test/wokwi/USAGE_LOG.md`.

Bugs found and fixed along the way (full details in `ROADMAP.md`): a too-heavy GLB export crashed WebGL
on zoom; the camera had no zoom-limit safety margin; the dashboard's icon-inference fallback resolved
almost everything to the Mega's own icon; an early client-side JS "simulation" reimplementation was
built then correctly redirected to the real Wokwi-backed approach instead.

Not yet re-verified in an actual browser after the live-simulation wiring (the HTTP API is confirmed, the
UI itself hasn't been clicked through yet) - do that next.

See `ROADMAP.md` for what's next (net view, live DRC action, 7-segment live readout, onboarding a second
project to prove the genericity).
