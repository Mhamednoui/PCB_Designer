"""Generic manifest generator - works for any project, never hardcodes one board.

Reads the project's design from whichever source it has (this workspace's scripted `gen/netlist.py`, or
any KiCad project's `.kicad_pcb` - see collect_design), merges this platform's per-project
`io_map.json` / `actions.json`, and writes `manifest.json`. The frontend only ever reads that manifest -
never netlist.py, never the KiCad files.

Usage: python build_manifest.py <project-id>
"""
import sys
import os
import re
import json
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_pcb  # noqa: E402

WEBVIEW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(WEBVIEW_DIR)


def load_netlist(project_id):
    """This workspace's scripted convention. Returns None if the project wasn't built that way - most
    KiCad projects aren't, and those go through the .kicad_pcb path instead (see collect_design)."""
    path = os.path.join(WORKSPACE_ROOT, "projects", project_id, "gen", "netlist.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"netlist_{project_id}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Reference-designator prefix -> a generic KiCad symbol, used for icons when the design came from a
# .kicad_pcb (which records footprints, not schematic symbols). Only symbols verified to exist in
# KiCad 10's standard libraries; anything unmapped simply gets no icon, which the frontend handles.
GENERIC_SYMBOL_BY_PREFIX = {
    "R": "Device:R", "C": "Device:C", "L": "Device:L", "D": "Device:D", "Q": "Device:Q_NMOS",
    "F": "Device:Fuse", "Y": "Device:Crystal", "J": "Connector_Generic:Conn_01x01",
    "P": "Connector_Generic:Conn_01x01", "SW": "Switch:SW_Push", "S": "Switch:SW_Push",
}


def generic_symbol_for(ref):
    prefix = re.match(r"^[A-Za-z]+", ref or "")
    if not prefix:
        return None
    prefix = prefix.group(0).upper()
    return GENERIC_SYMBOL_BY_PREFIX.get(prefix) or GENERIC_SYMBOL_BY_PREFIX.get(prefix[0])


def collect_design(project_id):
    """The design data (components + nets), from whichever source this project actually has.

    1. `gen/netlist.py` - this workspace's scripted pipeline. Richest: real schematic symbols, so icons
       are the exact part symbols, and parts carry their functional `group`.
    2. `<project>.kicad_pcb` - EVERY KiCad project has one, however it was authored. Slightly less rich
       (no schematic symbols, so icons fall back to generic per-reference-prefix ones), but it makes the
       platform work for any project rather than only ones built by this workspace's scripts.
    """
    nl = load_netlist(project_id)
    if nl:
        nets = {net: sorted(f"{ref}.{pin}" for ref, pin in refs) for net, refs in nl.nets().items()}
        components = [{
            "ref": p["ref"], "value": p["value"], "symbol": p["lib_id"],
            "footprint": p.get("footprint"), "pins": p["pins"], "group": p.get("group"),
        } for p in nl.PARTS]
        return getattr(nl, "PRJ_NAME", project_id), components, nets, "gen/netlist.py"

    project_dir = os.path.join(WORKSPACE_ROOT, "projects", project_id)
    if not os.path.isdir(project_dir):
        raise SystemExit(f"no such project: {project_dir}")
    pcb_path = kicad_pcb.find_pcb(project_dir)
    if not pcb_path:
        raise SystemExit(
            f"project '{project_id}' has neither gen/netlist.py nor a .kicad_pcb in {project_dir}\n"
            f"The platform needs one of them to know the board's components and nets."
        )
    data = kicad_pcb.parse_pcb(pcb_path)
    for component in data["components"]:
        component["symbol"] = generic_symbol_for(component["ref"])
    return data["name"], data["components"], data["nets"], os.path.basename(pcb_path)


def icon_rel_path(lib_id):
    """Only return a path if that icon was actually cached by build_icon_cache.py."""
    if not lib_id or ":" not in lib_id:
        return None
    lib, symbol = lib_id.split(":", 1)
    # kicad-cli sym export svg names its output "<symbol>_unit1.svg" (unit1 = representative icon).
    rel = f"assets/icons/{lib}/{symbol}_unit1.svg"
    if os.path.isfile(os.path.join(WEBVIEW_DIR, "app", rel)):
        return rel
    return None


def load_json(path, default):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def build(project_id):
    name, components, nets_out, source = collect_design(project_id)
    for component in components:
        component["icon"] = icon_rel_path(component.get("symbol"))

    proj_dir = os.path.join(WEBVIEW_DIR, "projects", project_id)
    io_map = load_json(os.path.join(proj_dir, "io_map.json"), {"inputs": [], "outputs": []})
    io = (
        [{**item, "kind": "input"} for item in io_map.get("inputs", [])]
        + [{**item, "kind": "output"} for item in io_map.get("outputs", [])]
    )
    actions = load_json(os.path.join(proj_dir, "actions.json"), [])

    manifest = {
        "id": project_id,
        "name": name,
        "model": "model.glb",
        "components": components,
        "nets": nets_out,
        "io": io,
        "actions": actions,
    }
    # Optional live simulation backing (see webview/ROADMAP.md "live simulation"). Purely a
    # file-presence check - a project either has wokwi_map.json (real Wokwi MCP backend) or it doesn't.
    # The map itself is read by the backend directly, never shipped to the frontend as-is.
    manifest["live_sim"] = os.path.isfile(os.path.join(proj_dir, "wokwi_map.json"))
    # Boards with no MCU simulate through SPICE instead (webview/services/spice): a project opts in
    # with a SPICE = {...} block in its netlist.py. Only the defaults the UI needs are shipped.
    nl = load_netlist(project_id)
    spice = getattr(nl, "SPICE", None) if nl else None
    manifest["spice_sim"] = bool(spice)
    if spice:
        manifest["spice"] = {"supplies": spice.get("supplies", {}), "tstop": spice.get("tstop"),
                             "probes": spice.get("probes", [])}

    os.makedirs(proj_dir, exist_ok=True)
    out_path = os.path.join(proj_dir, "manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"wrote {out_path}")
    print(f"  design source: {source}")
    print(f"  {len(components)} components, {len(nets_out)} nets, {len(io)} io entries, "
          f"{len(actions)} actions")
    if not io:
        print("  NOTE: no io_map.json yet - the dashboard will be empty until you write one "
              "(see webview/README.md 'Add a new project').")
    unknown_io = sorted({e["net"] for e in io if e["net"] not in nets_out})
    if unknown_io:
        print(f"  WARNING: {len(unknown_io)} io_map net(s) do not exist on this board - check for typos:")
        for net in unknown_io:
            print(f"    {net}")
    missing_icons = sorted({c["symbol"] for c in components if c["symbol"] and not c["icon"]})
    if missing_icons:
        print(f"  {len(missing_icons)} symbol(s) have no cached icon yet - run build_icon_cache.py:")
        for s in missing_icons:
            print(f"    {s}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python build_manifest.py <project-id>")
        sys.exit(1)
    build(sys.argv[1])
