"""Scaffold selftest (PA-8): python tests/scaffold/test_scaffold.py  (system Python, stdlib, no KiCad).
Scaffolds every kind into a temp copy of the files it touches (the real repo is never modified) and proves: the rule
stub registers with the engine and reports NOT_JUDGED (never a pass), its registry check is clean, the planned mutation is
valid and skipped by the suite's rules, stage/block/project/mutation stubs are valid, and overwriting / bad names are refused."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from boardgen import scaffold                                   # noqa: E402
from boardgen.rules import engine                               # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "  -> " + str(detail)))
    if not cond:
        FAILS.append(name)


def refused(root, kind, name):
    try:
        scaffold.scaffold(kind, name, root)
    except scaffold.ScaffoldError:
        return True
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="scaffold_test_", dir=os.path.join(ROOT, "tests", "scaffold"))
    try:
        for rel in ("tests/mutations/mutations.json", "tools/boardgen/stages.json"):
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tmp, rel))
        rid = "TST-SCAFFOLD-A"
        made = scaffold.scaffold("rule", rid, tmp)
        check("rule: 5 outputs", len(made) == 5, made)
        check("rule: refuses to overwrite", refused(tmp, "rule", rid))
        check("rule: bad id refused", refused(tmp, "rule", "bad_id") and refused(tmp, "rule", "x-1"))
        muts = json.load(open(os.path.join(tmp, "tests", "mutations", "mutations.json"), encoding="utf-8"))
        m = next((x for x in muts if x["id"] == "M-tst-scaffold-a"), None)
        check("rule: planned mutation added", m is not None and m.get("status") == "planned", m)
        check("mutations.json: only planned entry appended", len(muts) == len(json.load(open(
            os.path.join(ROOT, "tests", "mutations", "mutations.json"), encoding="utf-8"))) + 1)
        # the generated module registers itself through the decorator, like any rules/*.py the engine imports
        path = os.path.join(tmp, "tools", "boardgen", "rules", "tst_scaffold_a.py")
        spec = importlib.util.spec_from_file_location("tst_scaffold_a", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        r = engine.REGISTRY.rules.get(rid)
        check("rule: registered with the engine", r is not None)
        if r is not None:
            reg = engine.Registry(root=tmp, mutation_ids={x["id"] for x in muts})
            reg.rules[rid] = r
            check("rule: registry check clean (doc, fixtures, mutation id)", reg.validate() == [], reg.validate())
            ir = json.load(open(os.path.join(tmp, r.fixture, "green.json"), encoding="utf-8"))["ir"]
            findings, stats = reg.run(ir, only=[rid])
            check("rule: stub is NOT_JUDGED, not a pass", [f.severity for f in findings] == ["NOT_JUDGED"], findings)
            del engine.REGISTRY.rules[rid]
        check("rule: written with LF", b"\r\n" not in open(path, "rb").read())
        # the real suite skips planned entries and ci_checks accepts them
        src = open(os.path.join(ROOT, "tests", "mutations", "run_mutations.py"), encoding="utf-8").read()
        check("suite skips status=planned", 'e.get("status") == "planned"' in src)

        check("mutation: appended", scaffold.scaffold("mutation", "M-tst-b", tmp) and refused(tmp, "mutation", "M-tst-b"))
        check("mutation: bad id refused", refused(tmp, "mutation", "not ok"))
        scaffold.scaffold("stage", "tst-stage", tmp)
        stages = json.load(open(os.path.join(tmp, "tools", "boardgen", "stages.json"), encoding="utf-8"))["stages"]
        check("stage: entry appended last", stages[-1]["name"] == "tst-stage", stages[-1]["name"])
        check("stage: entry passes the pipeline validator", _valid_registry(os.path.join(tmp, "tools", "boardgen", "stages.json")))
        check("stage: refuses duplicates/bad names", refused(tmp, "stage", "tst-stage") and refused(tmp, "stage", "Bad_Name"))
        scaffold.scaffold("block", "tst-block", tmp)
        check("block: valid JSON", json.load(open(os.path.join(tmp, "blocks", "tst-block.json"), encoding="utf-8"))["id"] == "tst-block")
        scaffold.scaffold("project", "tst-proj", tmp)
        gen = os.path.join(tmp, "projects", "tst-proj", "gen")
        for fn in ("netlist.py", "make_pcb.py"):
            src = open(os.path.join(gen, fn), encoding="utf-8").read()
            try:
                compile(src, fn, "exec")
                ok = True
            except SyntaxError as e:
                ok = str(e)
            check("project: %s compiles" % fn, ok is True, ok)
        nl = open(os.path.join(gen, "netlist.py"), encoding="utf-8").read()
        check("project: netlist has the required sections", all(k in nl for k in
              ("ASSEMBLY", "EXTERNAL", "REQUIREMENTS", "NET_SPEC", "registry_part")))
        check("project: refuses to overwrite", refused(tmp, "project", "tst-proj"))
        check("unknown kind refused", refused(tmp, "widget", "x"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("scaffold selftest: %s" % ("FAIL (%d)" % len(FAILS) if FAILS else "all ok"))
    return 1 if FAILS else 0


def _valid_registry(path):
    sys.path.insert(0, ROOT)
    import pipeline
    try:
        pipeline.load_registry(path)
        return True
    except SystemExit:
        return False


if __name__ == "__main__":
    sys.exit(main())
