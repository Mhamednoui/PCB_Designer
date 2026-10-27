"""Mutation suite: inject one known mistake into a throw-away copy of a project and prove the pipeline
fails at the stage that is supposed to catch it.   (P0 exit gate, MD-T7; metric: PLATFORM_PLAN.md s4)

    python tests/mutations/run_mutations.py                  # run everything
    python tests/mutations/run_mutations.py --list           # show every entry, no side effects
    python tests/mutations/run_mutations.py --only M-pin,M-fp   # run a subset (comma list or repeat flag)
    python tests/mutations/run_mutations.py --keep -v        # keep projects/_mut_<id>/ and print failing output

A mutation that is not caught is a FINDING about a gate, not a flaky test: never loosen an entry to turn
the suite green. Fix the gate, or record the gap (`"status": "known-gap"`, with `"note"`).

mutations.json is a list of objects. Fields:
    id            unique, becomes projects/_mut_<id>/ (git-ignored; deleted after the run)
    fixture       an existing project under projects/ (copied; read-only source - use signed-off boards only
                  as fixtures, never mutate them in place)
    description   what mistake this models, one sentence
    op            one operation, or a list applied in order (vocabulary below)
    stages        pipeline stages to run: `pipeline.py _mut_<id> --force --only <stages>`; choose the CHEAPEST
                  range that can reach the catching stage. Prerequisite outputs (.kicad_pcb, the fab zip...)
                  are copied from the fixture, so a late stage can run alone.
    expect_stage  the stage that must FAIL (first failing stage), or null for a negative control that must
                  pass with exit 0
    expect_text   substring that must appear in the output (case-sensitive; "" = don't check)
    status        optional. "planned" = needs a later phase, skipped with a note, excluded from the catch rate.
                  "known-gap" = real gap, run but reported as GAP and does not fail the suite.
    needs / note  free text, shown for planned / known-gap entries

Op vocabulary (all paths are relative to the copied project; `{prj}` expands to `_mut_<id>`; the harness
aborts the entry with ERROR if an `old` string / pattern is not found, so a stale fixture cannot silently
turn a mutation into a no-op):
    {"type": "none"}                                              negative control
    {"type": "replace", "file": "gen/netlist.py", "old": "..", "new": "..", "count": 1}
                                                                  exact text replace in any text file
                                                                  (netlist.py edits, make_pcb.py, .kicad_pcb ...)
    {"type": "placements", "set": {"D1": [68.0, 24.0, 0]}}        rewrite entries of the dict literal in
                                                                  gen/make_pcb.py's placements() ("REF": (x, y, rot))
    {"type": "net_spec", "net": "OUT", "set": {"i_max": 2.0}}     merge keys into NET_SPEC[net] (appended to netlist.py)
    {"type": "json_set", "file": "{prj}.kicad_pro", "path": ["board", ...], "value": ..}
                                                                  set a nested JSON value (rules off in .kicad_pro)
    {"type": "zip_replace", "zip": "out/fab/{prj}_gerbers_JLCPCB.zip", "member": "*F_Cu.gtl",
     "old": "..", "new": "..", "regex": false}                    edit text inside one member of the fab zip
    {"type": "records", "from": "tests/parts/records"}            copy that records dir into the project as `records/`
                                                                  and point the parts registry at it (env
                                                                  PARTS_RECORDS_DIR, read by boardgen/parts.py), so a
                                                                  later `replace` on `records/<id>.json` mutates a
                                                                  TEST record, never parts/records
    {"type": "zip_append", "zip": "..", "member": "*F_Cu.gtl", "text": "..."}
                                                                  insert text before the member's final M02*

Output: one row per entry (id, expected stage, actual stage, verdict, seconds) and `catch rate N/M`.
Verdicts: CAUGHT, CLEAN (control passed), MISSED (exit 0), WRONG-STAGE, WRONG-TEXT, FALSE-ALARM (control
failed), GAP (known-gap), ERROR (harness could not set the entry up), SKIP (planned). Exit 1 unless all
runnable entries are CAUGHT/CLEAN/GAP. Python hygiene: children run with PYTHONDONTWRITEBYTECODE=1 and
`python -B`, because a stale .pyc within the same second as an edit makes a mutation a silent no-op.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PROJECTS = os.path.join(ROOT, "projects")
MUTATIONS = os.path.join(HERE, "mutations.json")
TEXT_EXT = (".kicad_pro", ".kicad_sch", ".kicad_pcb", ".kicad_dru", ".py", ".json", ".md", ".ino", ".toml")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "docs", ".pio", "*-routed.*", "*-backup*", "run",
                                "*.lck", "review", ".pipeline_cache.json")
TIMEOUT_S = 900


class SetupError(Exception):
    pass


# ----------------------------------------------------------------------------------------------- copy
def make_copy(fixture, pid):
    src, dst = os.path.join(PROJECTS, fixture), os.path.join(PROJECTS, pid)
    if not os.path.isdir(src):
        raise SetupError("fixture projects/%s does not exist" % fixture)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)
    # Files named after the project (<id>.kicad_pcb, out/fab/<id>_gerbers_JLCPCB.zip ...) are renamed, and the
    # id inside text files is rewritten, because netlist.PRJ_NAME decides which file names every stage opens.
    for base, dirs, files in os.walk(dst):
        for f in files:
            if f.startswith(fixture):
                os.replace(os.path.join(base, f), os.path.join(base, pid + f[len(fixture):]))
    for base, _, files in os.walk(dst):
        for f in files:
            p = os.path.join(base, f)
            if f.endswith(TEXT_EXT) and os.path.getsize(p) < 8_000_000:
                with open(p, encoding="utf-8", newline="") as fh:
                    s = fh.read()
                if fixture in s:
                    with open(p, "w", encoding="utf-8", newline="") as fh:
                        fh.write(s.replace(fixture, pid))
    return dst


# ----------------------------------------------------------------------------------------------- ops
def _path(dst, rel, pid):
    return os.path.join(dst, rel.replace("{prj}", pid).replace("/", os.sep))


def _read(p):
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _write(p, s):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def _sub(s, old, new, count, regex, where):
    if regex:
        out, n = re.subn(old, new, s, count=count or 0)
    else:
        n = s.count(old)
        out = s.replace(old, new, count) if count else s.replace(old, new)
    if not n:
        raise SetupError("op did not match anything in %s: %r" % (where, old[:80]))
    return out


def op_replace(dst, pid, op):
    p = _path(dst, op["file"], pid)
    _write(p, _sub(_read(p), op["old"].replace("{prj}", pid), op["new"].replace("{prj}", pid),
                   op.get("count", 1), op.get("regex", False), op["file"]))


def op_placements(dst, pid, op):
    p = _path(dst, "gen/make_pcb.py", pid)
    s = _read(p)
    for ref, (x, y, rot) in op["set"].items():
        s = _sub(s, r'"%s":\s*\([^)]*\)' % re.escape(ref), '"%s": (%s, %s, %s)' % (ref, x, y, rot), 1, True,
                 "gen/make_pcb.py placements %s" % ref)
    _write(p, s)


def op_net_spec(dst, pid, op):
    p = _path(dst, "gen/netlist.py", pid)
    _write(p, _read(p).rstrip("\n") + "\n\nNET_SPEC.setdefault(%r, {}).update(%r)   # mutation\n"
           % (op["net"], op["set"]))


def op_json_set(dst, pid, op):
    p = _path(dst, op["file"], pid)
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    node = data
    for k in op["path"][:-1]:
        node = node.setdefault(k, {})
    node[op["path"][-1]] = op["value"]
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _edit_zip(path, member_glob, fn):
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    hits = [i.filename for i, _ in items if fnmatch.fnmatch(i.filename, member_glob)]
    if len(hits) != 1:
        raise SetupError("zip member %r matched %d files in %s: %s" % (member_glob, len(hits), path, hits))
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for info, data in items:
            if info.filename == hits[0]:
                data = fn(data.decode("utf-8", "replace")).encode("utf-8")
            z.writestr(info.filename, data)
    os.replace(tmp, path)


def op_zip_replace(dst, pid, op):
    _edit_zip(_path(dst, op["zip"], pid), op["member"],
              lambda s: _sub(s, op["old"], op["new"], op.get("count", 1), op.get("regex", False), op["member"]))


def op_zip_append(dst, pid, op):
    def fn(s):
        i = s.rfind("M02*")
        if i < 0:
            raise SetupError("no M02* end-of-file marker in %s" % op["member"])
        return s[:i] + op["text"] + "\n" + s[i:]
    _edit_zip(_path(dst, op["zip"], pid), op["member"], fn)


ENV_EXTRA = {}     # project id -> extra environment for that entry's pipeline run


def op_records(dst, pid, op):
    src = os.path.join(ROOT, op.get("from", "tests/parts/records"))
    if not os.path.isdir(src):
        raise SetupError("records dir %s does not exist" % src)
    shutil.copytree(src, os.path.join(dst, "records"))
    ENV_EXTRA[pid] = {"PARTS_RECORDS_DIR": os.path.join(dst, "records")}     # honoured by boardgen/parts.py


OPS = {"none": lambda *a: None, "replace": op_replace, "placements": op_placements, "net_spec": op_net_spec,
       "json_set": op_json_set, "records": op_records, "zip_replace": op_zip_replace, "zip_append": op_zip_append}


def apply_ops(dst, pid, op):
    for o in (op if isinstance(op, list) else [op]):
        if o["type"] not in OPS:
            raise SetupError("unknown op type %r (known: %s)" % (o["type"], ", ".join(sorted(OPS))))
        OPS[o["type"]](dst, pid, o)


# ----------------------------------------------------------------------------------------------- run
def run_entry(e, keep):
    """-> (actual_stage, verdict, seconds, output)"""
    pid = "_mut_" + e["id"]
    dst = os.path.join(PROJECTS, pid)
    t0 = time.time()
    try:
        try:
            make_copy(e["fixture"], pid)
            apply_ops(dst, pid, e["op"])
        except (SetupError, KeyError, OSError, ValueError) as ex:
            return "-", "ERROR", time.time() - t0, "setup failed: %s: %s" % (type(ex).__name__, ex)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", **ENV_EXTRA.get(pid, {}))
        # --no-cache: a mutation must be judged by actually running its stages. A skip on matching hashes
        # would be a green result nobody earned, and the mutated copy is a fresh project every time.
        cmd = [sys.executable, "-B", "pipeline.py", pid, "--force", "--no-cache", "--only", ",".join(e["stages"])]
        try:
            r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=TIMEOUT_S,
                               text=True, encoding="utf-8", errors="replace")
            out, rc = (r.stdout or "") + (r.stderr or ""), r.returncode
        except subprocess.TimeoutExpired:
            return "-", "ERROR", time.time() - t0, "timed out after %ds" % TIMEOUT_S
        failed = re.findall(r"^--- (\S+) FAILED", out, re.M)
        actual = failed[0] if failed else ("-" if rc == 0 else "pipeline")
        want = e["expect_stage"]
        if want is None:
            verdict = "CLEAN" if rc == 0 else "FALSE-ALARM"
        elif rc == 0:
            verdict = "MISSED"
        elif actual != want:
            verdict = "WRONG-STAGE"
        elif e.get("expect_text", "") not in out:
            verdict = "WRONG-TEXT"
        else:
            verdict = "CAUGHT"
        if e.get("status") == "known-gap" and verdict in ("MISSED", "WRONG-STAGE", "WRONG-TEXT"):
            verdict = "GAP"
        return actual, verdict, time.time() - t0, out
    finally:
        if not keep and os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)


def tail(out, n=25):
    lines = [l for l in out.splitlines() if l.strip()]
    return "\n".join("      | " + l for l in lines[-n:])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", action="append", default=[], help="comma-separated mutation ids")
    ap.add_argument("--list", action="store_true", help="list entries and exit")
    ap.add_argument("--keep", action="store_true", help="keep projects/_mut_<id>/ after the run")
    ap.add_argument("-v", "--verbose", action="store_true", help="print the output tail of failing entries")
    args = ap.parse_args()

    with open(MUTATIONS, encoding="utf-8") as f:
        entries = json.load(f)
    ids = [e["id"] for e in entries]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit("duplicate ids in mutations.json: %s" % ", ".join(sorted(dup)))
    want = [s.strip() for v in args.only for s in v.split(",") if s.strip()]
    unknown = [w for w in want if w not in ids]
    if unknown:
        raise SystemExit("unknown mutation id(s): %s\nvalid: %s" % (", ".join(unknown), ", ".join(ids)))
    if want:
        entries = [e for e in entries if e["id"] in want]

    if args.list:
        for e in entries:
            tag = e.get("status", "")
            print("%-16s %-12s %-10s %-9s %s" % (e["id"], e["fixture"] if "fixture" in e else "-",
                                                 e.get("expect_stage") or "(pass)", tag or "active",
                                                 e["description"]))
        return 0

    for stale in [d for d in os.listdir(PROJECTS) if d.startswith("_mut_")]:
        shutil.rmtree(os.path.join(PROJECTS, stale), ignore_errors=True)

    t_all = time.time()
    rows, planned = [], []
    print("%-24s %-11s %-11s %-12s %7s" % ("id", "expected", "actual", "verdict", "secs"))
    for e in entries:
        if e.get("status") == "planned":
            planned.append(e)
            print("%-24s %-11s %-11s %-12s %7s  needs %s" % (e["id"], e.get("expect_stage") or "-", "-", "SKIP",
                                                            "-", e.get("needs", "a later phase")))
            continue
        actual, verdict, secs, out = run_entry(e, args.keep)
        rows.append((e, verdict))
        print("%-24s %-11s %-11s %-12s %7.1f" % (e["id"], e["expect_stage"] or "(pass)", actual, verdict, secs))
        sys.stdout.flush()
        if verdict not in ("CAUGHT", "CLEAN") and (args.verbose or verdict in ("ERROR",)):
            print(tail(out))

    muts = [(e, v) for e, v in rows if e["expect_stage"] is not None]
    ctrls = [(e, v) for e, v in rows if e["expect_stage"] is None]
    caught = sum(1 for _, v in muts if v == "CAUGHT")
    gaps = sum(1 for _, v in muts if v == "GAP")
    ctrl_ok = sum(1 for _, v in ctrls if v == "CLEAN")
    bad = [e["id"] for e, v in rows if v not in ("CAUGHT", "CLEAN", "GAP")]
    print("\ncatch rate %d/%d   (negative controls %d/%d clean, %d known gaps, %d planned and skipped)   runtime %.0fs"
          % (caught, len(muts), ctrl_ok, len(ctrls), gaps, len(planned), time.time() - t_all))
    if bad:
        print("FAILED entries: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
