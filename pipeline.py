"""Top-level pipeline runner - one command from a design to a fabricable, tested, viewable board.

    python pipeline.py <project-id>                 # run every applicable stage
    python pipeline.py <project-id> --only webview  # run one stage
    python pipeline.py <project-id> --skip route    # skip a slow stage
    python pipeline.py <project-id> --list          # show what would run, and why

WHAT THIS DOES AND DOESN'T AUTOMATE
-----------------------------------
The creative half of a board - what it should do, which parts, the pin map, which nets are inputs vs
outputs - is genuine engineering judgement plus a conversation with the person who wants the board. That
half is the PROMPT, and it produces three human/AI-authored files:

    projects/<id>/DESIGN_BRIEF.md          the spec and the decisions behind it
    projects/<id>/gen/netlist.py           every part and every connection (the single source of truth)
    webview/projects/<id>/io_map.json      which nets are inputs/outputs, and what to call them

Everything downstream of those is mechanical, and that is what this script runs. So the end-to-end story
is: one prompt writes those three files, then one command (this one) does all the rest.

STAGES (each is skipped automatically when it doesn't apply to the project)
  sch       schematic from netlist.py, then netlist compare + ERC        (needs gen/make_sch.py)
  place     footprints, board outline, silkscreen, pre-routed links      (needs gen/make_pcb.py)
  route     autoroute                                                    (needs gen/make_pcb.py)
  finish    ground pours, stitching vias                                 (needs gen/make_pcb.py)
  check     DRC incl. schematic parity - the gate before fab             (needs gen/make_pcb.py)
  outputs   gerbers/BOM/CPL/STEP/PDF/renders                             (needs gen/make_outputs.py)
  fabreport MANUFACTURING.md: size, layers, holes, parts, order-form answers (any scripted board)
  connections CONNECTIONS.md: every pin of every part and where its copper goes, in plain words
  pinmap    firmware pin map vs netlist cross-check                      (needs test/pinmap.py)
  spice     transient LTspice run of the whole board + expected-vs-measured (needs a SPICE block in netlist.py)
  webview   export GLB, cache icons, build manifest, onboard to viewer   (needs any .kicad_pcb)

A project that is only a .kicad_pcb (imported, drawn by hand, downloaded) simply has every design stage
skipped and goes straight to `webview` - which is why this works for any project, not just ones authored
by this workspace's scripts.
"""
import argparse
import os
import subprocess
import sys
import time

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "tools"))
from boardgen.kicad_paths import PYTHON as KICAD_PYTHON  # noqa: E402

# The generic stages live in ONE place and are shared by every project (see tools/boardgen/project.py).
# Only netlist.py and make_pcb.py - the two genuinely board-specific files - stay in projects/<id>/gen.
BOARDGEN = os.path.join(WORKSPACE_ROOT, "tools", "boardgen")


def project_paths(project_id):
    project_dir = os.path.join(WORKSPACE_ROOT, "projects", project_id)
    return {
        "dir": project_dir,
        "gen": os.path.join(project_dir, "gen"),
        "test": os.path.join(project_dir, "test"),
    }


def build_stages(project_id):
    """Each stage: (name, why-it-applies check, cwd, command). Uses KiCad's Python for anything that
    imports pcbnew, and the plain interpreter for the rest."""
    paths = project_paths(project_id)
    gen, test = paths["gen"], paths["test"]

    def gen_script(name):
        return os.path.isfile(os.path.join(gen, name))

    # A scripted board is one with a netlist.py; the shared stages read it from the cwd we set below.
    scripted = gen_script("netlist.py")

    def shared(name, *args):
        return [KICAD_PYTHON, os.path.join(BOARDGEN, name), *args]

    def has_spice_block():
        # A plain text check - importing netlist.py here would drag in the project's own imports.
        path = os.path.join(gen, "netlist.py")
        if not os.path.isfile(path):
            return False
        with open(path, encoding="utf-8") as f:
            return any(line.startswith("SPICE = ") for line in f)

    return [
        # Design-rule lint of netlist.py itself (pure Python, <1 s): catches design mistakes ERC/DRC cannot.
        ("lint", scripted, WORKSPACE_ROOT, [sys.executable, os.path.join(BOARDGEN, "lint_netlist.py"), project_id]),
        ("sch", scripted, gen, shared("make_sch.py")),
        ("sch-check", scripted, gen, shared("check_sch.py")),
        ("place", gen_script("make_pcb.py"), gen, [KICAD_PYTHON, "make_pcb.py", "place"]),
        ("route", gen_script("make_pcb.py"), gen, [KICAD_PYTHON, "make_pcb.py", "route"]),
        ("finish", gen_script("make_pcb.py"), gen, [KICAD_PYTHON, "make_pcb.py", "finish"]),
        ("check", gen_script("make_pcb.py"), gen, [KICAD_PYTHON, "make_pcb.py", "check"]),
        # Design review (kicad-happy analyzers + projects/<id>/waivers.json): decoupling distance, EMC, power tree.
        ("review", gen_script("make_pcb.py"), WORKSPACE_ROOT,
         [sys.executable, os.path.join(BOARDGEN, "make_review.py"), project_id]),
        ("outputs", scripted, gen, shared("make_outputs.py")),
        # Read-only: measures the finished board + its drill file, so it's safe on a signed-off board.
        ("fabreport", scripted, WORKSPACE_ROOT, shared("make_fab_report.py", project_id)),
        ("connections", scripted, WORKSPACE_ROOT, shared("make_connections.py", project_id)),
        ("pinmap", os.path.isfile(os.path.join(test, "pinmap.py")), test, [sys.executable, "pinmap.py"]),
        ("spice", has_spice_block(), WORKSPACE_ROOT,
         [sys.executable, os.path.join(BOARDGEN, "make_spice.py"), project_id]),
        ("webview", True, os.path.join(WORKSPACE_ROOT, "webview", "tools"),
         [sys.executable, "onboard.py", project_id]),
    ]


def run_stage(name, cwd, cmd):
    print(f"\n=== {name} ===")
    started = time.time()
    result = subprocess.run(cmd, cwd=cwd)
    elapsed = time.time() - started
    if result.returncode != 0:
        print(f"--- {name} FAILED after {elapsed:.1f}s (exit {result.returncode})")
        return False, elapsed
    print(f"--- {name} ok ({elapsed:.1f}s)")
    return True, elapsed


def print_summary(rows):
    print("\nsummary:")
    print(f"  {'stage':<14}{'result':<9}{'seconds':>8}")
    for name, status, secs in rows:
        print(f"  {name:<14}{status:<9}{'' if secs is None else format(secs, '.1f'):>8}")


def main():
    parser = argparse.ArgumentParser(description="Run the board pipeline for a project.")
    parser.add_argument("project_id")
    parser.add_argument("--only", action="append", default=[],
                        help="run only these stages (comma-separated, or repeat the flag)")
    parser.add_argument("--skip", action="append", default=[],
                        help="skip these stages (comma-separated, or repeat the flag)")
    parser.add_argument("--list", action="store_true", help="show what would run, then exit")
    parser.add_argument("--force", action="store_true",
                        help="allow re-running design stages on a board that already has fab outputs")
    args = parser.parse_args()

    if not os.path.isdir(project_paths(args.project_id)["dir"]):
        raise SystemExit(f"no such project: projects/{args.project_id}")

    stages = build_stages(args.project_id)

    # Accept both `--only a,b` and `--only a --only b`. Without the split, `--only finish,check` parses
    # as one stage named "finish,check", matches nothing, and the run reports success having done
    # NOTHING - which is how this was found. Validate the names for the same reason: a typo must be a
    # loud error, never a silent no-op.
    def stage_list(values):
        return [s.strip() for v in values for s in v.split(",") if s.strip()]

    args.only, args.skip = stage_list(args.only), stage_list(args.skip)
    known = {name for name, _, _, _ in stages}
    unknown = [s for s in args.only + args.skip if s not in known]
    if unknown:
        raise SystemExit("unknown stage(s): %s\nvalid stages: %s"
                         % (", ".join(unknown), ", ".join(n for n, _, _, _ in stages)))

    planned = [
        (name, cwd, cmd) for name, applies, cwd, cmd in stages
        if applies and name not in args.skip and (not args.only or name in args.only)
    ]
    skipped = [name for name, applies, _, _ in stages if not applies]

    if args.list:
        print(f"project: {args.project_id}")
        print("would run: " + (", ".join(n for n, _, _ in planned) or "(nothing)"))
        if skipped:
            print("not applicable to this project: " + ", ".join(skipped))
        return

    # A board with fab outputs has been generated, checked and (probably) signed off. Re-running place/
    # route/finish on it silently redoes the routing of a board someone already verified - exactly the
    # kind of destructive surprise a "run everything" command must not spring on you.
    design_stages = {"sch", "place", "route", "finish"}
    rerunning_design = [name for name, _, _ in planned if name in design_stages]
    fab_dir = os.path.join(project_paths(args.project_id)["dir"], "out", "fab")
    if rerunning_design and os.path.isdir(fab_dir) and os.listdir(fab_dir) and not args.force:
        raise SystemExit(
            f"'{args.project_id}' already has fab outputs in out/fab - it looks finished.\n"
            f"Re-running {', '.join(rerunning_design)} would regenerate and re-route that board.\n\n"
            f"  To refresh only the viewer:      python pipeline.py {args.project_id} --only webview\n"
            f"  To re-verify without changing:   python pipeline.py {args.project_id} --only check\n"
            f"  To really redo the design:       python pipeline.py {args.project_id} --force"
        )

    print(f"pipeline for '{args.project_id}': {', '.join(n for n, _, _ in planned) or '(nothing)'}")
    if skipped:
        print(f"(skipping stages this project doesn't have: {', '.join(skipped)})")

    rows, failed = [], None
    for name, cwd, cmd in planned:
        if failed:
            rows.append((name, "skipped", None))
            continue
        ok, secs = run_stage(name, cwd, cmd)
        rows.append((name, "ok" if ok else "FAILED", secs))
        if not ok:
            failed = name

    print_summary(rows)
    if failed:
        print(f"\npipeline stopped at '{failed}'. Fix it, then re-run with "
              f"--only {failed} (or --skip the stages already done).")
        sys.exit(1)

    print("\npipeline complete.")


if __name__ == "__main__":
    main()
