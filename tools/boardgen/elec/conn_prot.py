"""Command line for EL-CONN-PROT (P2-T7): the per-net protection class table and the findings of one project.

    python tools/boardgen/elec/conn_prot.py <project-id | path/to/design.json> [--table] [--no-waivers]

Needs out/design.json (python pipeline.py <id> --only ir). Applies projects/<id>/waivers.json (check "electrical").
Exit 1 = an unwaived ERROR, 2 = usage / no IR. Rule logic lives in boardgen/rules/el_conn_prot.py.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # tools/
from boardgen import project as _project                                                          # noqa: E402
from boardgen.rules import engine                                                                  # noqa: E402
from boardgen.rules.el_conn_prot import classify                                                   # noqa: E402


def _table(rows, notes):
    out = ["%-16s %-12s %-14s %-9s %s" % ("net", "connector", "kind", "class", "protection / missing")]
    for r in rows:
        extra = ", ".join(r["protection"]) if r["protection"] else ""
        if r["missing"]:
            extra += ("  " if extra else "") + "MISSING: " + ", ".join(r["missing"])
        if r["kind"] == "signal" and r["hops"]:
            extra += ("  " if extra else "") + "(%d series R)" % r["hops"]
        out.append("%-16s %-12s %-14s %-13s %s" % (r["net"], r["connector"], r["kind"], r["cls"], extra))
    out += ["NOT_JUDGED: " + n[1] for n in notes]
    return "\n".join(out)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    path = args[0] if args[0].endswith(".json") else os.path.join(_project.PROJECTS, args[0], "out", "design.json")
    if not os.path.isfile(path):
        print("no %s - run: python pipeline.py %s --only ir" % (path, args[0]))
        return 2
    ir = json.load(open(path, encoding="utf-8"))
    rows, notes = classify(ir)
    if "--table" in argv:
        print(_table(rows, notes))
    findings, stats = engine.run(ir, only=["EL-CONN-PROT"])
    if "--no-waivers" not in argv and not args[0].endswith(".json"):
        findings += engine.apply_waivers(args[0], "electrical", findings, stats)
    for f in findings:
        print(f.line() + ("   [WAIVED: %s]" % f.waived.get("why") if f.waived else ""))
    s = stats["EL-CONN-PROT"]
    print("EL-CONN-PROT: examined %s, not judged %s, errors %s, waived %s" % (s.get("examined"), s.get("not_judged"), s.get("errors"), s.get("waived")))
    return 1 if any(f.severity == "ERROR" and not f.waived for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
