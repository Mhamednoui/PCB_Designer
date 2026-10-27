"""Review stage: `make_review.py <project-id> [--full]`. Runs the kicad-happy schematic, PCB and EMC
analyzers (read-only, safe on signed-off boards) into projects/<id>/test/review/ and writes review.json.
Gate (exit 1): unwaived finding that is severity=error AND confidence=deterministic, plus any unwaived
DC-001/DC-002 error (decoupling distance; heuristic but the one rule that finds real defects).
DS-001/SS-001/TE-001/GP-005 and every warning/info are report-only. Rules that are wrong for a board class
are silenced ONLY by waivers in projects/<id>/waivers.json with "check": "review" and a "why"."""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                    # tools/
from boardgen import project as _project                      # noqa: E402
from boardgen import waivers as _waivers                      # noqa: E402

SKILLS = os.path.join(os.path.dirname(os.path.dirname(HERE)), ".claude", "skills")
SCH_PY = os.path.join(SKILLS, "kicad", "scripts", "analyze_schematic.py")
PCB_PY = os.path.join(SKILLS, "kicad", "scripts", "analyze_pcb.py")
EMC_PY = os.path.join(SKILLS, "emc", "scripts", "analyze_emc.py")
REPORT_ONLY = {"DS-001", "SS-001", "TE-001", "GP-005"}      # procedural / noise: never gate
ALWAYS_GATE = {"DC-001", "DC-002"}                           # decoupling distance


def run(cmd, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable] + cmd, cwd=cwd, env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("analyzer failed (%s): %s" % (os.path.basename(cmd[0]), r.stderr[-600:]))


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: make_review.py <project-id> [--full]")
    full = "--full" in argv
    pdir = os.path.join(_project.PROJECTS, pid)
    out = os.path.join(pdir, "test", "review")
    os.makedirs(out, exist_ok=True)
    gi = os.path.join(out, ".gitignore")
    if not os.path.isfile(gi):
        open(gi, "w").write("*\n")                           # generated results never go in git
    sch = os.path.join(pdir, pid + ".kicad_sch")
    pcb = os.path.join(pdir, pid + ".kicad_pcb")
    s, p, e = (os.path.join(out, n) for n in ("sch.json", "pcb.json", "emc.json"))
    t0 = time.time()
    run([SCH_PY, sch, "-o", s], pdir)
    run([PCB_PY, pcb, "--schematic", s, "-o", p] + (["--full"] if full else []), pdir)
    run([EMC_PY, "-s", s, "-p", p, "-o", e], pdir)
    runtime = round(time.time() - t0, 1)

    ws, problems = _waivers.load(pid, "review")
    used = set()
    items = []
    for src, path in (("sch", s), ("pcb", p), ("emc", e)):
        for f in json.load(open(path, encoding="utf-8")).get("findings", []):
            rule, sev = f.get("rule_id", "?"), f.get("severity", "info")
            conf = f.get("confidence", "")
            refs, nets = f.get("components") or [], f.get("nets") or []
            gating = sev == "error" and rule not in REPORT_ONLY and (conf == "deterministic" or rule in ALWAYS_GATE)
            waiver = None
            if gating:
                for i, w in ws:
                    if _waivers.matches(w, rule, refs, nets):
                        waiver = w
                        used.add(i)
                        break
            items.append({"source": src, "rule": rule, "severity": sev, "confidence": conf,
                          "refs": refs, "nets": nets, "message": f.get("summary", ""),
                          "gating": gating, "waived": waiver is not None,
                          "why": waiver["why"] if waiver else None})
    fails = [i for i in items if i["gating"] and not i["waived"]]
    for i, w in ws:
        if i not in used:
            print("WARN waiver waivers.json[%d]: unused review waiver (rule %r, %s)"
                  % (i, w.get("rule"), _waivers.describe(w)))
    nfail = len(fails)
    for t, m in problems:
        print("ERROR waiver %s: %s" % (t, m))
        nfail += 1
    for f in fails:
        print("ERROR %s [%s] %s: %s" % (f["rule"], f["source"], ",".join(f["refs"] + f["nets"]), f["message"]))
    sev = {}
    for i in items:
        sev[i["severity"]] = sev.get(i["severity"], 0) + 1
    json.dump({"project": pid, "full": full, "runtime_s": runtime, "counts": sev,
               "gating_failures": nfail, "waived": sum(i["waived"] for i in items),
               "findings": items}, open(os.path.join(out, "review.json"), "w", encoding="utf-8"), indent=1)
    if nfail:
        print("FAILED: %d unwaived gating review findings (%.1fs, full=%s)" % (nfail, runtime, full))
        return 1
    print("review OK: %s (%s, %d waived, %.1fs, full=%s)"
          % (pid, sev, sum(i["waived"] for i in items), runtime, full))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
