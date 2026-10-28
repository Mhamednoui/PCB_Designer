# PCB workspace - project notes for Claude

Claude Code loads this file automatically every session in this folder.

## STANDING RULES (the user should never have to ask for these)
1. **Update the docs as part of the work, not when asked.** After any change, before reporting back:
   this file's Status + `docs/SESSION_LOG.md`, `docs/LESSONS_LEARNED.md` (any trap that cost real time),
   `webview/ROADMAP.md` (platform status + honest limitations), and the affected project's README.
   Correct anything the change made stale (counts, filenames, instructions).
2. **Keep the workspace clean.** Delete files that are no longer needed; don't leave intermediates,
   scratch scripts or dead references lying around.
3. **Check for errors after changing things** - compile/lint/run it. Don't report success you haven't seen.
4. **Small steps, low token use**: do one thing, show the result, ask before the next.

## Goal
AI-assisted PCB design with KiCad: Claude helps design schematics, lay out and route boards,
review designs, source parts, and prepare fabrication files (JLCPCB/PCBWay).

## Environment
- KiCad 10.0.6 at `C:\Program Files\KiCad\10.0` (KiCad Python 3.11.5 at `bin\python.exe`, `kicad-cli.exe` in `bin`)
- KiCad user dir: `C:\Users\nouir\Documents\KiCad\10.0` (pip `--user` installs for KiCad Python go to `3rdparty\Python311`)
- System Python 3.11.0, git, Node 26. No system Java (Freerouting is extracted under `tools/freerouting`).
- Windows: in PowerShell, piping text to a process adds a BOM; use the Bash tool for stdin tests.

## Folder layout
| Path | What |
|---|---|
| `.mcp.json` | MCP servers `kicad` (Seeed) and `konnect` (not installed) |
| `.claude/skills/` | 11 kicad-happy skills (kicad, bom, datasheets, emc, spice, jlcpcb, pcbway, lcsc, digikey, mouser, element14) |
| `.venv/` | easyeda2kicad, skidl, kicad-skip, fastmcp (kikit here is broken - no pcbnew) |
| `tools/boardgen/` | **SHARED** board-generation stages (make_sch, check_sch, make_outputs, sexp, kicad_paths) used by every project - never copy these into a project |
| `tools/` | `sym_pins.py`, `fp_bbox.py`, plus shallow git clones: kicad-happy, kicad-mcp-server, Konnect, KiKit, skidl, easyeda2kicad.py, InteractiveHtmlBom, Fabrication-Toolkit, awesome-kicad |
| `downloads/` | `konnect-pcm-v0.11.1-windows.zip` (unused), `freerouting-2.4.1-windows-x64.msi` |
| `README.md` | front door - which doc to read for which task |
| `docs/` | reference: `TOOLING.md`, `NEW_BOARD_PLAYBOOK.md`, `LESSONS_LEARNED.md`, `PLATFORM_PLAN.md`, `SESSION_LOG.md`; `adr/` decisions, `design/` designs |
| `parts/` | parts registry (schema + records, tiers, pins by function); CLI `tools/parts.py` |
| `tests/` | `tests/mutations/` mutation suite (gate catch-rate) |
| `.claude/agents/` | project agent types pcb-light, pcb-worker |
| `tools/boardgen/stages.json` | declarative stage registry (order, cache inputs); `ir/` design IR, `rules/` rule engine |
| `projects/` | put actual board projects here (one subfolder per board, each with its own `README.md`) |
| `webview/` | generic local 3D viewer + dashboard platform (any project) - see `webview/ROADMAP.md` |

## Tools and what each is for
- **kicad MCP** (Seeed-Studio kicad-mcp-server 3.4.7) - read/analyze schematics & PCBs, trace nets, ERC/DRC.
  Installed `--user -e` into KiCad Python. Verified: MCP initialize handshake OK.
- **konnect MCP** (NOT installed; mixelpixx/Konnect v0.11.1) - would create/edit schematics & PCBs, placement,
  routing, exports. Needs KiCad open with the board loaded + IPC API enabled for PCB tools.
- **kicad-happy skills** - design review, EMC, SPICE, BOM, datasheets, distributor search, fab prep. Pure Python, no deps.
- **KiKit 1.8.1** - installed in KiCad Python: `& "C:\Program Files\KiCad\10.0\bin\python.exe" -m kikit.ui ...` (verified)
- **easyeda2kicad 1.0.1** - `.venv\Scripts\easyeda2kicad.exe --full --lcsc_id=Cxxxx` imports LCSC parts (verified)
- **SKiDL 2.3.0 / kicad-skip 0.2.5** - circuits as Python / edit KiCad files from Python (import verified)
- **Freerouting 2.4.1** - autorouter, used by the `route` stage (DSN export -> route -> SES import)

## CONTINUING THE IMPROVEMENT WORK? Read `docs/SUPERVISOR_HANDOVER.md` FIRST
It holds the supervisor procedure, the agents in flight (branches/worktrees), the next queue and the owner's
standing instructions. Nothing about the ongoing work lives only in chat.

## Status (2026-10-28)
Goal is the **platform** (pipeline + gates + parts registry + webview), not any one board. The three projects
(blinky-555, uno-toggle, reflex-machine) are rebuildable regression fixtures. Read: `ROADMAP.md` (task status),
`docs/PLATFORM_PLAN.md` (plan), `AGENT_NOTES.md` (traps), `docs/SESSION_LOG.md` (history).
Pending user actions: approve MCP servers; Konnect is NOT installed. Freerouting IS used (extracted at
`tools/freerouting`, git-ignored). User also has CircuitMaker and Proteus 8 (GUI, manual use only).

## Asked for a NEW board? Start here
`docs/NEW_BOARD_PLAYBOOK.md` - **the A-to-Z checklist** (steps A-M: brief -> netlist -> pipeline ->
MANUFACTURING.md/CONNECTIONS.md -> simulation -> webview -> docs), what to ask the user, placement order,
what "done" means. Then `docs/PCB_CREATION_GUIDE.md` for the tested procedure and failure catalogue.
`docs/LESSONS_LEARNED.md` - the working pipeline, 30 numbered mistakes plus sections 8-17 (spice, wokwi, three.js, placement/silk/layers, what each check catches), KiCad 10 scripting API notes,
Freerouting usage. Update it whenever a new trap costs more than a few minutes.
