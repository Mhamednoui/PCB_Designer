# PCB workspace (KiCad 10.0.6)

## AI integration (Claude Code)
- `.mcp.json` - MCP servers, loaded when Claude Code opens this folder
  - `kicad` - Seeed-Studio kicad-mcp-server, runs in KiCad's Python (schematic/PCB analysis, net tracing, ERC/DRC)
  - `konnect` - mixelpixx/Konnect: create/edit schematics & PCBs, placement, routing, exports.
    Needs `downloads/konnect-pcm-v0.11.1-windows.zip` installed via KiCad > Plugin and Content Manager > Install from File.
    PCB tools need KiCad running with the board open (enable IPC API in Preferences > Plugins).
- `.claude/skills/` - kicad-happy skills: kicad, bom, datasheets, emc, spice, jlcpcb, pcbway, lcsc, digikey, mouser, element14

## Python tools (`.venv`)
Activate: `.venv\Scripts\Activate.ps1`
- `easyeda2kicad --full --lcsc_id=C2040` - import LCSC/JLCPCB part (symbol, footprint, 3D)
- KiKit needs pcbnew, so it is installed in KiCad's Python instead:
  `& "C:\Program Files\KiCad\10.0\bin\python.exe" -m kikit.ui fab jlcpcb board.kicad_pcb out/`
- `skidl` - circuits as Python code -> netlist / schematic
- `kicad-skip` - read/modify .kicad_sch and .kicad_pcb files from Python

## tools/ (source clones)
kicad-happy, kicad-mcp-server, Konnect, KiKit, skidl, easyeda2kicad.py,
InteractiveHtmlBom, Fabrication-Toolkit, awesome-kicad (big curated list)

## downloads/
- `freerouting-2.4.1-windows-x64.msi` - autorouter (Java bundled). Export Specctra DSN from PCB editor, route, import SES.
- `konnect-pcm-v0.11.1-windows.zip` - Konnect KiCad plugin

## Also install from KiCad Plugin and Content Manager
Fabrication Toolkit (JLCPCB outputs), Interactive Html Bom, Freerouting, KiKit
