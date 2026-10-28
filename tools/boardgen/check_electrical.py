"""Stage `electrical` (P2-T4): the electrical rules (EL-*) over the design IR.

    python tools/boardgen/check_electrical.py <project-id>

Reads projects/<id>/out/design.json (written by the `ir` stage, so this stage runs right after it), runs every registered
rule whose id starts with `EL-` through the rule engine, applies waivers (waivers.json entries with "check": "electrical";
a waiver can demote an ERROR only, never a NOT_JUDGED), prints one line per finding, a per-rule items table, and writes the
structured findings to $PCB_FINDINGS_FILE for the run report. Exit 1 on any unwaived ERROR or a missing / stale IR.
NOT_JUDGED is shown and counted but never fails this stage (hand boards, spec P2 section 4); the pcba release gate (P2-T10)
is where it blocks.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                    # tools/
from boardgen import project as _project                      # noqa: E402
from boardgen.rules import engine as _engine                  # noqa: E402

CHECK = "electrical"


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: check_electrical.py <project-id>")
    path = os.path.join(_project.PROJECTS, pid, "out", "design.json")
    if not os.path.isfile(path):
        print("FAILED: %s missing - run the `ir` stage first (it builds the design IR this stage judges)" % path)
        return 1
    with open(path, encoding="utf-8") as f:
        ir = json.load(f)
    _engine.REGISTRY.load_builtin()
    ids = sorted(r for r in _engine.REGISTRY.rules if r.startswith("EL-"))
    findings, stats = _engine.run(ir, only=ids)
    findings += _engine.apply_waivers(pid, CHECK, findings, stats)
    for f in findings:
        print(f.line())
    out_path = os.environ.get("PCB_FINDINGS_FILE")
    if out_path:
        _engine.write_findings(out_path, findings, stats)
    print("\n%-14s %8s %7s %11s %7s %7s" % ("rule", "examined", "judged", "NOT_JUDGED", "errors", "waived"))
    for rid in ids:
        s = stats.get(rid, {})
        if s.get("skipped"):
            print("%-14s %s" % (rid, "not applicable (nothing on this design for the rule to judge)"))
            continue
        print("%-14s %8d %7d %11d %7d %7d" % (rid, s.get("examined", 0), s.get("judged", 0), s.get("not_judged", 0),
                                              s.get("errors", 0), s.get("waived", 0)))
    nj = sum(1 for f in findings if f.severity == "NOT_JUDGED")
    errors = [f for f in findings if f.severity == "ERROR" and f.waived is None]
    if errors:
        print("FAILED: %d electrical errors" % len(errors))
        return 1
    print("electrical OK: %s (%d rules, %d NOT_JUDGED - allowed for hand boards, blocks a pcba release)" % (pid, len(ids), nj))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
