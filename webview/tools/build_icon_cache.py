"""Generic icon cache builder - exports one SVG per symbol actually used by a project, shared across
ALL projects in app/assets/icons/<lib>/<symbol>_unit1.svg. Never re-exports a symbol already cached, so
onboarding a second project that reuses common libraries (Device, Connector, ...) costs nothing extra.

Usage: python build_icon_cache.py <project-id>
"""
import sys
import os
import subprocess
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_manifest  # noqa: E402  (shared design-collection + generic symbol mapping)

WEBVIEW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(WEBVIEW_DIR)
ICONS_DIR = os.path.join(WEBVIEW_DIR, "app", "assets", "icons")
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools"))
from boardgen.kicad_paths import CLI as KICAD_CLI, SYMBOLS as KICAD_SYMBOLS_DIR  # noqa: E402


def load_netlist(project_id):
    """Returns None when the project wasn't built with this workspace's scripted convention - that's
    normal for most KiCad projects, and build_manifest's design collector handles it."""
    path = os.path.join(WORKSPACE_ROOT, "projects", project_id, "gen", "netlist.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"netlist_{project_id}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def resolve_lib_file(nl, project_id, lib):
    project_libs = getattr(nl, "PROJECT_LIBS", ()) if nl else ()
    if lib in project_libs:
        return os.path.join(WORKSPACE_ROOT, "projects", project_id, "lib", f"{lib}.kicad_sym")
    # A project-local library still works without netlist.py, if the project keeps one in lib/.
    local = os.path.join(WORKSPACE_ROOT, "projects", project_id, "lib", f"{lib}.kicad_sym")
    if os.path.isfile(local):
        return local
    return os.path.join(KICAD_SYMBOLS_DIR, f"{lib}.kicad_sym")


def build(project_id):
    nl = load_netlist(project_id)
    if nl:
        # Scripted-pipeline project: exact schematic symbols per part.
        wanted = sorted({p["lib_id"] for p in nl.PARTS if p.get("lib_id") and ":" in p["lib_id"]})
    else:
        # Any other KiCad project: the .kicad_pcb has no schematic symbols, so use the same generic
        # per-reference-prefix symbols build_manifest.py assigns, keeping the two in sync by reusing it.
        design = build_manifest.collect_design(project_id)
        wanted = sorted({
            symbol for symbol in
            (build_manifest.generic_symbol_for(c["ref"]) for c in design[1])
            if symbol
        })
    if not wanted:
        print(f"no symbols to cache for '{project_id}'")
        return

    exported, skipped, failed = 0, 0, 0
    for lib_id in wanted:
        lib, symbol = lib_id.split(":", 1)
        out_dir = os.path.join(ICONS_DIR, lib)
        out_file = os.path.join(out_dir, f"{symbol}_unit1.svg")
        if os.path.isfile(out_file):
            skipped += 1
            continue

        lib_file = resolve_lib_file(nl, project_id, lib)
        if not os.path.isfile(lib_file):
            print(f"  SKIP {lib_id}: library file not found ({lib_file})")
            failed += 1
            continue

        os.makedirs(out_dir, exist_ok=True)
        result = subprocess.run(
            [KICAD_CLI, "sym", "export", "svg", "-o", out_dir, "--symbol", symbol, lib_file],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and os.path.isfile(out_file):
            print(f"  OK   {lib_id}")
            exported += 1
        else:
            print(f"  FAIL {lib_id}: {result.stderr.strip() or result.stdout.strip()}")
            failed += 1

    print(f"\n{exported} exported, {skipped} already cached, {failed} failed "
          f"(out of {len(wanted)} symbols used by '{project_id}')")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python build_icon_cache.py <project-id>")
        sys.exit(1)
    build(sys.argv[1])
