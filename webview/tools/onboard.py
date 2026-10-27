"""One-command onboarding for ANY KiCad project - the whole pipeline in one step.

    python onboard.py <project-id>

Expects `<workspace>/projects/<project-id>/` to contain a KiCad project (any `.kicad_pcb`; it does NOT
need this workspace's scripted `gen/netlist.py`). Does everything the platform needs:

  1. exports the board to `webview/projects/<id>/model.glb` (skipped if already present)
  2. caches the component icons it needs (shared across all projects, never re-exported)
  3. scaffolds `io_map.json` + `actions.json` stubs if they don't exist yet
  4. builds `manifest.json`

Afterwards the project shows up in the webview's project picker on the next page load. The only thing
left for a human is filling in `io_map.json` (which nets are inputs/outputs and what to call them) -
that's a judgement call no tool can make, see webview/README.md.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_icon_cache  # noqa: E402
import build_manifest  # noqa: E402
import kicad_pcb  # noqa: E402

WEBVIEW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(WEBVIEW_DIR)
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
from boardgen.kicad_paths import CLI as KICAD_CLI  # noqa: E402


def export_glb(pcb_path, out_path):
    """Board body + component 3D models only.

    Deliberately WITHOUT --include-tracks/pads/zones/silkscreen: those produced 30,000+ separate
    primitives on the first board here and crashed the browser's WebGL context on zoom (see
    webview/ROADMAP.md). This matches what KiCad's own 3D viewer shows by default.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = subprocess.run(
        [KICAD_CLI, "pcb", "export", "glb", "--force", "-o", out_path, pcb_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not os.path.isfile(out_path):
        raise SystemExit(f"GLB export failed:\n{result.stderr or result.stdout}")
    return os.path.getsize(out_path)


def scaffold(proj_dir, design_nets):
    """Write starter io_map.json / actions.json only if absent - never overwrite a human's work."""
    io_path = os.path.join(proj_dir, "io_map.json")
    if not os.path.isfile(io_path):
        with open(io_path, "w", encoding="utf-8") as f:
            json.dump({
                "_README": (
                    "Declare which nets are inputs (buttons/switches/sensors) and outputs "
                    "(LEDs/actuators/displays). 'ref' is optional but strongly recommended - it picks "
                    "which component's icon represents the entry and which part gets highlighted in 3D. "
                    "Net names must match the board exactly; run build_manifest.py to validate them."
                ),
                "_available_nets_sample": sorted(design_nets)[:25],
                "inputs": [],
                "outputs": [],
            }, f, indent=2)
        print(f"  scaffolded {io_path} (empty - fill this in to populate the dashboard)")

    actions_path = os.path.join(proj_dir, "actions.json")
    if not os.path.isfile(actions_path):
        with open(actions_path, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        print(f"  scaffolded {actions_path} (empty - add reports/scripts to show in the Output Console)")


def main(project_id):
    project_dir = os.path.join(WORKSPACE_ROOT, "projects", project_id)
    if not os.path.isdir(project_dir):
        raise SystemExit(f"no such project folder: {project_dir}")
    pcb_path = kicad_pcb.find_pcb(project_dir)
    if not pcb_path:
        raise SystemExit(f"no .kicad_pcb found in {project_dir}")

    proj_dir = os.path.join(WEBVIEW_DIR, "projects", project_id)
    os.makedirs(proj_dir, exist_ok=True)
    print(f"onboarding '{project_id}' from {os.path.basename(pcb_path)}")

    model_path = os.path.join(proj_dir, "model.glb")
    if os.path.isfile(model_path):
        print(f"  model.glb already present ({os.path.getsize(model_path) / 1e6:.1f} MB) - keeping it")
    else:
        size = export_glb(pcb_path, model_path)
        print(f"  exported model.glb ({size / 1e6:.1f} MB)")

    print("  caching icons...")
    build_icon_cache.build(project_id)

    _, _, nets, _ = build_manifest.collect_design(project_id)
    scaffold(proj_dir, nets.keys())

    print("  building manifest...")
    build_manifest.build(project_id)
    print(f"\ndone - reload the webview and pick '{project_id}' from the project dropdown.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python onboard.py <project-id>")
        sys.exit(1)
    main(sys.argv[1])
