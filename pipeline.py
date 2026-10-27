"""Top-level pipeline runner - one command from a design to a fabricable, tested, viewable board.

    python pipeline.py <project-id>                 # run every applicable stage
    python pipeline.py <project-id> --only webview  # run one stage
    python pipeline.py <project-id> --skip route    # skip a slow stage
    python pipeline.py <project-id> --list          # show what would run, and why
    python pipeline.py --describe <stage> [<project-id>]   # one stage: what it does, inputs/outputs, caching
    python pipeline.py <project-id> --no-cache      # re-run even stages whose inputs are unchanged

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

STAGES - declared in tools/boardgen/stages.json (the registry). Array order is run order, and adding a
stage means adding ONE entry there; this file is a generic runner and needs no edit. Each stage is skipped
automatically when it doesn't apply to the project. Current stages (see `--list`, `--describe <stage>`):
  lint, parts, sch, sch-check, place, route, finish, check, review, outputs, lvs, fabreport, connections,
  pinmap (needs FIRMWARE in netlist.py), spice (needs SPICE in netlist.py), webview (works for any .kicad_pcb)

A project that is only a .kicad_pcb (imported, drawn by hand, downloaded) simply has every design stage
skipped and goes straight to `webview` - which is why this works for any project, not just ones authored
by this workspace's scripts.

INCREMENTAL RUNS
Stages that only READ the design (lint, sch-check, check, review, lvs, fabreport, connections, pinmap, spice)
declare their `inputs` and `outputs` in the registry. A stage whose inputs (file contents), command line,
registry entry and toolchain are identical to its last SUCCESSFUL run, and whose outputs are still present
and untouched, is reported `cached` and skipped. Never cached: failed stages, stages with no declared inputs,
design stages (sch/place/route/finish: they rewrite the design, and Freerouting is nondeterministic), and
anything the registry marks with a `no_cache_reason`. State: projects/<id>/.pipeline_cache.json (git-ignored).
`--no-cache` forces every stage to run (the mutation suite always passes it).
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "tools"))
from boardgen import kicad_paths  # noqa: E402

KICAD_PYTHON = kicad_paths.PYTHON

# The generic stages live in ONE place and are shared by every project (see tools/boardgen/project.py).
# Only netlist.py and make_pcb.py - the two genuinely board-specific files - stay in projects/<id>/gen.
BOARDGEN = os.path.join(WORKSPACE_ROOT, "tools", "boardgen")
REGISTRY = os.path.join(BOARDGEN, "stages.json")
CACHE_NAME = ".pipeline_cache.json"
CACHE_VERSION = 1

STAGE_FIELDS = {"name", "description", "applies", "interpreter", "cwd", "argv", "design_stage",
                "inputs", "outputs", "env", "no_cache_reason"}
REQUIRED_FIELDS = STAGE_FIELDS - {"env", "no_cache_reason"}
INTERPRETERS = ("kicad", "system")
CWDS = ("gen", "root", "webview_tools")


def project_paths(project_id):
    project_dir = os.path.join(WORKSPACE_ROOT, "projects", project_id)
    return {
        "dir": project_dir,
        "gen": os.path.join(project_dir, "gen"),
        "test": os.path.join(project_dir, "test"),
    }


# ------------------------------------------------------------------------------------------ registry
def load_registry(path=REGISTRY):
    """Read + validate the stage registry. Every mistake is a loud SystemExit naming the entry: a typo'd
    field silently ignored is exactly how a stage ends up un-cached or un-guarded without anyone noticing."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise SystemExit("cannot read stage registry %s: %s" % (path, e))
    entries = data.get("stages") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SystemExit("stage registry %s: need a non-empty top-level \"stages\" array" % path)
    seen = set()
    for i, e in enumerate(entries):
        who = "stage registry entry #%d (%s)" % (i + 1, e.get("name", "?") if isinstance(e, dict) else "?")
        if not isinstance(e, dict):
            raise SystemExit("%s: must be an object" % who)
        missing = sorted(REQUIRED_FIELDS - set(e))
        extra = sorted(set(e) - STAGE_FIELDS)
        if missing:
            raise SystemExit("%s: missing field(s) %s" % (who, ", ".join(missing)))
        if extra:
            raise SystemExit("%s: unknown field(s) %s (known: %s)" % (who, ", ".join(extra), ", ".join(sorted(STAGE_FIELDS))))
        if e["name"] in seen:
            raise SystemExit("%s: duplicate stage name" % who)
        seen.add(e["name"])
        if e["interpreter"] not in INTERPRETERS:
            raise SystemExit("%s: interpreter must be one of %s" % (who, INTERPRETERS))
        if e["cwd"] not in CWDS:
            raise SystemExit("%s: cwd must be one of %s" % (who, CWDS))
        for k in ("argv", "inputs", "outputs", "env"):
            if k in e and not (isinstance(e[k], list) and all(isinstance(x, str) for x in e[k])):
                raise SystemExit("%s: %s must be a list of strings" % (who, k))
        if not e["argv"]:
            raise SystemExit("%s: argv must not be empty" % who)
        if not isinstance(e["design_stage"], bool):
            raise SystemExit("%s: design_stage must be true or false" % who)
        if not e["inputs"] and not e.get("no_cache_reason"):
            raise SystemExit("%s: no inputs declared, so it is never cached - say why in \"no_cache_reason\"" % who)
        _applies_kind(e["applies"], who)
    return entries


def _applies_kind(spec, who="applies"):
    kind, _, arg = spec.partition(":")
    if kind in ("always", "has_netlist") and not arg:
        return kind, arg
    if kind in ("has_gen_script", "netlist_has_block") and arg:
        return kind, arg
    raise SystemExit("%s: bad applies %r (use always | has_netlist | has_gen_script:<file> | netlist_has_block:<NAME>)"
                     % (who, spec))


def applies(entry, project_id):
    kind, arg = _applies_kind(entry["applies"], entry["name"])
    gen = project_paths(project_id)["gen"]
    if kind == "always":
        return True
    if kind == "has_netlist":
        return os.path.isfile(os.path.join(gen, "netlist.py"))
    if kind == "has_gen_script":
        return os.path.isfile(os.path.join(gen, arg))
    # netlist_has_block: a plain text check - importing netlist.py here would drag in the project's own imports.
    path = os.path.join(gen, "netlist.py")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        return any(line.startswith(arg + " = ") for line in f)


def _sub(text, project_id):
    out = text.replace("{project}", project_id or "{project}").replace("{boardgen}", BOARDGEN)
    return os.path.normpath(out) if "{boardgen}" in text else out


def resolve_command(entry, project_id):
    interp = KICAD_PYTHON if entry["interpreter"] == "kicad" else sys.executable
    return [interp] + [_sub(a, project_id) for a in entry["argv"]]


def resolve_cwd(entry, project_id):
    return {"gen": project_paths(project_id)["gen"] if project_id else "projects/{project}/gen",
            "root": WORKSPACE_ROOT,
            "webview_tools": os.path.join(WORKSPACE_ROOT, "webview", "tools")}[entry["cwd"]]


# ----------------------------------------------------------------------------------------------- cache
_FILE_HASHES = {}      # (path, size, mtime_ns) -> sha256, so a big .kicad_pcb is hashed once per run
_TOOLCHAIN = []


def _stat_sig(path):
    try:
        st = os.stat(path)
        return "%s|%d|%d" % (path, st.st_size, st.st_mtime_ns)
    except OSError:
        return "%s|missing" % path


def toolchain_fingerprint():
    """Interpreter + KiCad install identity. Stat-based (no process spawn): a KiCad upgrade replaces these
    binaries, which changes the key and invalidates every cached result produced by the old one."""
    if not _TOOLCHAIN:
        _TOOLCHAIN.append("|".join([sys.version, kicad_paths.VERSION, _stat_sig(kicad_paths.PYTHON),
                                    _stat_sig(kicad_paths.CLI)]))
    return _TOOLCHAIN[0]


def expand(patterns, project_id):
    """Sorted unique repo-relative file paths (forward slashes) matching the globs, plus per-pattern counts."""
    files, counts = set(), []
    for pat in patterns:
        pat = pat.replace("{project}", project_id)
        hits = [h for h in glob.glob(os.path.join(WORKSPACE_ROOT, pat), recursive=True) if os.path.isfile(h)]
        counts.append((pat, len(hits)))
        files.update(os.path.relpath(h, WORKSPACE_ROOT).replace(os.sep, "/") for h in hits)
    return sorted(files), counts


def _file_hash(rel):
    path = os.path.join(WORKSPACE_ROOT, rel)
    st = os.stat(path)
    k = (path, st.st_size, st.st_mtime_ns)
    if k not in _FILE_HASHES:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _FILE_HASHES[k] = h.hexdigest()
    return _FILE_HASHES[k]


def uncacheable_reason(entry, project_id):
    """None if the stage may be cached, else a short human reason."""
    if entry["design_stage"]:
        return "design stage"
    if not entry["inputs"]:
        return entry.get("no_cache_reason") or "no inputs declared"
    set_env = [v for v in entry.get("env", []) if os.environ.get(v)]
    if set_env:
        return "environment override (%s) changes behaviour outside the declared inputs" % ", ".join(set_env)
    files, _ = expand(entry["inputs"], project_id)
    if not files:
        return "none of the declared inputs exist"
    return None


def input_key(entry, project_id):
    files, _ = expand(entry["inputs"], project_id)
    blob = json.dumps({"entry": entry, "argv": resolve_command(entry, project_id),
                       "toolchain": toolchain_fingerprint(),
                       "inputs": [(rel, _file_hash(rel)) for rel in files]}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def outputs_signature(entry, project_id):
    """(size, mtime) of every declared output, or None if a declared output pattern matches nothing."""
    sig = []
    for pat in entry["outputs"]:
        files, _ = expand([pat], project_id)
        if not files:
            return None
        for rel in files:
            st = os.stat(os.path.join(WORKSPACE_ROOT, rel))
            sig.append("%s|%d|%d" % (rel, st.st_size, st.st_mtime_ns))
    return sorted(sig)


def cache_path(project_id):
    return os.path.join(project_paths(project_id)["dir"], CACHE_NAME)


def load_cache(project_id):
    try:
        with open(cache_path(project_id), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") == CACHE_VERSION and isinstance(data.get("stages"), dict):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {"version": CACHE_VERSION, "stages": {}}


def save_cache(project_id, cache):
    path = cache_path(project_id)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError as e:
        print("(warning: could not write %s: %s)" % (CACHE_NAME, e))


def cache_lookup(entry, project_id, cache):
    """-> (key or None, reason, record or None). record is set only when the stage can be skipped."""
    why = uncacheable_reason(entry, project_id)
    if why:
        return None, why, None
    key = input_key(entry, project_id)
    rec = cache["stages"].get(entry["name"])
    if not rec:
        return key, "no earlier successful run recorded", None
    if rec.get("key") != key:
        return key, "inputs, command or toolchain changed since the last successful run", None
    sig = outputs_signature(entry, project_id)
    if sig is None or rec.get("outputs") != sig:
        return key, "declared outputs missing or modified since the last successful run", None
    return key, "unchanged since the last successful run", rec


# ----------------------------------------------------------------------------------------------- run
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


def describe(entry, project_id):
    print(f"stage: {entry['name']}")
    print(f"  {entry['description']}")
    print(f"  applies when : {entry['applies']}" + (
        f"  -> {'yes' if applies(entry, project_id) else 'NO'} for {project_id}" if project_id else ""))
    print(f"  interpreter  : {entry['interpreter']}    cwd: {entry['cwd']}")
    print(f"  command      : {' '.join(resolve_command(entry, project_id))}")
    print(f"  design stage : {'yes (fab-output guard applies; --force to re-run a finished board)' if entry['design_stage'] else 'no'}")
    if entry["inputs"]:
        print("  inputs (hashed by content): " + ", ".join(entry["inputs"]))
        print("  outputs (must be intact for a cache hit): " + (", ".join(entry["outputs"]) or "(none - a pass is the result)"))
        if entry.get("env"):
            print("  never cached while set: " + ", ".join(entry["env"]))
    else:
        print(f"  caching      : never - {entry.get('no_cache_reason')}")
    if project_id and os.path.isdir(project_paths(project_id)["dir"]) and entry["inputs"] and not entry["design_stage"]:
        _, reason, rec = cache_lookup(entry, project_id, load_cache(project_id))
        print(f"  cache now    : {'WOULD SKIP (cached)' if rec else 'would run'} - {reason}")


def main():
    parser = argparse.ArgumentParser(description="Run the board pipeline for a project.")
    parser.add_argument("project_id", nargs="?")
    parser.add_argument("--only", action="append", default=[],
                        help="run only these stages (comma-separated, or repeat the flag)")
    parser.add_argument("--skip", action="append", default=[],
                        help="skip these stages (comma-separated, or repeat the flag)")
    parser.add_argument("--list", action="store_true", help="show what would run, then exit")
    parser.add_argument("--describe", metavar="STAGE",
                        help="explain one stage (what, interpreter, command, inputs/outputs, caching), then exit")
    parser.add_argument("--force", action="store_true",
                        help="allow re-running design stages on a board that already has fab outputs")
    parser.add_argument("--no-cache", action="store_true",
                        help="run every stage even if its inputs are unchanged since the last successful run")
    args = parser.parse_args()

    registry = load_registry()
    names = [e["name"] for e in registry]

    if args.describe:
        if args.describe not in names:
            raise SystemExit("unknown stage: %s\nvalid stages: %s" % (args.describe, ", ".join(names)))
        if args.project_id and not os.path.isdir(project_paths(args.project_id)["dir"]):
            raise SystemExit(f"no such project: projects/{args.project_id}")
        describe(next(e for e in registry if e["name"] == args.describe), args.project_id)
        return

    if not args.project_id:
        parser.error("project_id is required (except with --describe)")
    if not os.path.isdir(project_paths(args.project_id)["dir"]):
        raise SystemExit(f"no such project: projects/{args.project_id}")

    stages = [(e, applies(e, args.project_id)) for e in registry]

    # Accept both `--only a,b` and `--only a --only b`. Without the split, `--only finish,check` parses
    # as one stage named "finish,check", matches nothing, and the run reports success having done
    # NOTHING - which is how this was found. Validate the names for the same reason: a typo must be a
    # loud error, never a silent no-op.
    def stage_list(values):
        return [s.strip() for v in values for s in v.split(",") if s.strip()]

    args.only, args.skip = stage_list(args.only), stage_list(args.skip)
    unknown = [s for s in args.only + args.skip if s not in names]
    if unknown:
        raise SystemExit("unknown stage(s): %s\nvalid stages: %s" % (", ".join(unknown), ", ".join(names)))

    planned = [
        e for e, ok in stages
        if ok and e["name"] not in args.skip and (not args.only or e["name"] in args.only)
    ]
    skipped = [e["name"] for e, ok in stages if not ok]
    planned_names = [e["name"] for e in planned]

    if args.list:
        print(f"project: {args.project_id}")
        print("would run: " + (", ".join(planned_names) or "(nothing)"))
        if skipped:
            print("not applicable to this project: " + ", ".join(skipped))
        return

    # A board with fab outputs has been generated, checked and (probably) signed off. Re-running place/
    # route/finish on it silently redoes the routing of a board someone already verified - exactly the
    # kind of destructive surprise a "run everything" command must not spring on you.
    rerunning_design = [e["name"] for e in planned if e["design_stage"]]
    fab_dir = os.path.join(project_paths(args.project_id)["dir"], "out", "fab")
    if rerunning_design and os.path.isdir(fab_dir) and os.listdir(fab_dir) and not args.force:
        raise SystemExit(
            f"'{args.project_id}' already has fab outputs in out/fab - it looks finished.\n"
            f"Re-running {', '.join(rerunning_design)} would regenerate and re-route that board.\n\n"
            f"  To refresh only the viewer:      python pipeline.py {args.project_id} --only webview\n"
            f"  To re-verify without changing:   python pipeline.py {args.project_id} --only check\n"
            f"  To really redo the design:       python pipeline.py {args.project_id} --force"
        )

    print(f"pipeline for '{args.project_id}': {', '.join(planned_names) or '(nothing)'}")
    if skipped:
        print(f"(skipping stages this project doesn't have: {', '.join(skipped)})")

    cache = load_cache(args.project_id)
    rows, failed = [], None
    for entry in planned:
        name = entry["name"]
        if failed:
            rows.append((name, "skipped", None))
            continue

        key = None
        t_check = time.time()
        if not args.no_cache:
            key, _, rec = cache_lookup(entry, args.project_id, cache)
            if rec:
                print(f"\n=== {name} ===")
                print(f"--- {name} cached (inputs unchanged since {rec.get('when', '?')}; "
                      f"last run {rec.get('seconds', 0):.1f}s; --no-cache to force)")
                rows.append((name, "cached", time.time() - t_check))
                continue
        elif not uncacheable_reason(entry, args.project_id):
            key = input_key(entry, args.project_id)      # still record the run so the NEXT one can be cached

        ok, secs = run_stage(name, resolve_cwd(entry, args.project_id), resolve_command(entry, args.project_id))
        rows.append((name, "ok" if ok else "FAILED", secs))
        if ok:
            out_sig = outputs_signature(entry, args.project_id) if key else None
            if key and out_sig is not None:
                cache["stages"][name] = {"key": key, "outputs": out_sig,
                                         "seconds": round(secs, 2), "when": time.strftime("%Y-%m-%d %H:%M:%S")}
            else:
                cache["stages"].pop(name, None)
        else:
            cache["stages"].pop(name, None)             # a failed stage is never cached
            failed = name
        save_cache(args.project_id, cache)

    print_summary(rows)
    if failed:
        print(f"\npipeline stopped at '{failed}'. Fix it, then re-run with "
              f"--only {failed} (or --skip the stages already done).")
        sys.exit(1)

    print("\npipeline complete.")


if __name__ == "__main__":
    main()
