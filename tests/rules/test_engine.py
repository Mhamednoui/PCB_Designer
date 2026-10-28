"""Rule-engine tests (P2-T1): python tests/rules/test_engine.py  (system Python, stdlib, no KiCad). Exit 1 on failure.
Covers: the dummy demo rule (green fixture passes, its mutation goes red), the registry check (a rule missing doc /
fixture / mutation is refused), typed Finding validation, `needs` enforcement, items-examined, waivers v2 (only
ERROR -> WAIVED, never NOT_JUDGED; short `why`; expired), --explain, and that the real rules' fixtures pass."""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(HERE, "demo"))
from boardgen import waivers                                    # noqa: E402
from boardgen.rules import engine                               # noqa: E402
from boardgen.rules.finding import Finding, FindingError        # noqa: E402
import demo_rule                                                # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else "  -> " + str(detail)))
    if not cond:
        FAILS.append(name)


def raises(exc, fn):
    try:
        fn()
    except exc as e:
        return str(e) or True
    return False


def main():
    demo = demo_rule.DEMO
    check("demo registry valid (doc, fixture, mutation exist)", demo.validate() == [], demo.validate())
    check("demo fixtures: green passes, mutation goes red", engine.check_fixtures(demo) == [], engine.check_fixtures(demo))
    check("engine self-test (incl. registry probe) on demo", engine.selftest(demo) == [], engine.selftest(demo))

    # the mutation really goes red, and the NOT_JUDGED / examined accounting is right
    red = json.load(open(os.path.join(HERE, "demo", "fixtures", "DEMO-NEGATIVE", "red.json"), encoding="utf-8"))["ir"]
    red["nets"]["X"] = {"v": None}
    found, stats = demo.run(red)
    st = stats["DEMO-NEGATIVE"]
    check("red: 1 ERROR + 1 NOT_JUDGED", [f.severity for f in found] == ["ERROR", "NOT_JUDGED"], [f.line() for f in found])
    check("items examined = judged + not_judged", (st["examined"], st["judged"], st["not_judged"]) == (3, 2, 1), st)
    found, stats = demo.run({"nets": {}})
    check("0 items examined with expect_items=True -> ERROR (fail closed)",
          [f.severity for f in found] == ["ERROR"], [f.line() for f in found])

    # the registry check refuses incomplete rules
    probe = engine.Registry(root=os.path.join(HERE, "demo"), mutation_ids={"M-x"})
    probe.rule("ZZ-NODOC", "ERROR", ("nets",), "nope.md", "fixtures/DEMO-NEGATIVE", "M-x")(lambda ctx: [])
    probe.rule("ZZ-NOFIX", "ERROR", ("nets",), "DEMO-NEGATIVE.md", "fixtures/none", "M-x")(lambda ctx: [])
    probe.rule("ZZ-NOMUT", "ERROR", ("nets",), "DEMO-NEGATIVE.md", "fixtures/DEMO-NEGATIVE", "M-none")(lambda ctx: [])
    check("registry flags missing doc / fixture / mutation", len(probe.validate()) == 4, probe.validate())
    check("run() refuses an invalid registry", bool(raises(engine.RuleError, lambda: probe.run({}))))
    check("bad id refused", bool(raises(engine.RuleError, lambda: probe.rule("bad id", "ERROR", (), "a", "b", "c"))))
    check("duplicate id refused", bool(raises(engine.RuleError, lambda: probe.rule("ZZ-NODOC", "ERROR", (), "a", "b", "c")(lambda c: []))))
    check("unknown IR section in needs refused", bool(raises(engine.RuleError, lambda: probe.rule("ZZ-SEC", "ERROR", ("bogus",), "a", "b", "c"))))

    # needs is enforced
    greedy = engine.Registry(root=os.path.join(HERE, "demo"), mutation_ids={"M-demo-negative"})
    greedy.rule("ZZ-GREEDY", "ERROR", ("nets",), "DEMO-NEGATIVE.md", "fixtures/DEMO-NEGATIVE", "M-demo-negative")(
        lambda ctx: [ctx.ir["parts"]])
    check("a rule cannot read an IR section it did not declare", bool(raises(KeyError, lambda: greedy.run({"nets": {}, "parts": {}}))))

    # typed Finding
    check("Finding rejects a bad severity", bool(raises(FindingError, lambda: Finding("X-Y", "FATAL", "w"))))
    check("Finding rejects a non-numeric measured value",
          bool(raises(FindingError, lambda: Finding("X-Y", "ERROR", "w", measured={"value": "5", "unit": "V"}))))
    check("Finding rejects a limit without source",
          bool(raises(FindingError, lambda: Finding("X-Y", "ERROR", "w", limit={"value": 5, "unit": "V"}))))
    a = Finding("X-Y", "ERROR", "w", where={"ref": "U1", "pin": "3"}, limit={"value": 1, "unit": "V", "source": "ds p3"})
    b = Finding("X-Y", "WARN", "other text", where={"ref": "U1", "pin": "3"}, limit={"value": 9, "unit": "A", "source": "ds p3"})
    check("fingerprint = f(rule, where, limit.source) only", a.fingerprint() == b.fingerprint())

    # waivers v2
    errs = [Finding("R-A", "ERROR", "boom", refs=["U1"]), Finding("R-A", "NOT_JUDGED", "no data", refs=["U1"]),
            Finding("R-A", "WARN", "meh", refs=["U1"])]
    ws = [(0, {"rule": "R-A", "refs": ["U1"], "why": "x" * 25, "by": "me", "date": "2026-10-28"})]
    extra = waivers.apply(errs, ws)
    check("waiver demotes only the ERROR", [f.waived is not None for f in errs] == [True, False, False], [f.waived for f in errs])
    check("demoted line is WAIVED, NOT_JUDGED stays", errs[0].line().startswith("WAIVED ") and errs[1].line().startswith("NOT_JUDGED "))
    check("used waiver -> no extra findings", extra == [], [e.line() for e in extra])
    only_nj = [Finding("R-A", "NOT_JUDGED", "no data", refs=["U1"])]
    extra = waivers.apply(only_nj, ws)
    check("a waiver aimed at NOT_JUDGED is unused (WARN) and hides nothing",
          only_nj[0].waived is None and [e.severity for e in extra] == ["WARN"], [e.line() for e in extra])

    tmp = os.path.join(ROOT, "projects", "_rule_test")
    os.makedirs(tmp, exist_ok=True)
    try:
        for why, expires, expect in (("too short", None, "at least 20"), ("y" * 25, "2000-01-01", "expired"),
                                     ("y" * 25, "soon", "not YYYY-MM-DD"), ("y" * 25, "2999-01-01", None)):
            w = {"check": "lint", "rule": "R-A", "why": why}
            if expires:
                w["expires"] = expires
            with open(os.path.join(tmp, "waivers.json"), "w", encoding="utf-8") as f:
                json.dump([w], f)
            got, probs = waivers.load("_rule_test", "lint")
            check("waiver why=%r expires=%r" % (why[:9], expires),
                  (expect is None and len(got) == 1 and not probs) or (expect and not got and expect in probs[0][1]), (got, probs))
    finally:
        for fn in os.listdir(tmp):
            os.remove(os.path.join(tmp, fn))
        os.rmdir(tmp)
    check("today() is a date", isinstance(waivers.today(), datetime.date))

    # real rules
    engine.REGISTRY.load_builtin()
    prob = engine.selftest()
    check("real rules: registry + fixtures + probe", prob == [], prob)
    check("real rules registered", sorted(engine.REGISTRY.rules) == ["EL-ABSMAX", "EL-BUDGET", "EL-CONN-PROT", "EL-CONTENTION", "EL-DROPOUT", "EL-FLOAT", "EL-LEVEL", "EL-NETSPEC", "EL-OD-PULLUP", "EL-STRAP", "EL-THERMAL", "LINT-SHORT", "LINT-SINGLE-PIN"], sorted(engine.REGISTRY.rules))
    text = engine.explain("single-pin")
    check("--explain renders doc, mutation, example", all(s in text for s in ("LINT-SINGLE-PIN", "Example fix", "mutation: M-split", "ERROR single-pin R1/OUT")), text)
    check("--explain works on the demo registry", "DEMO-NEGATIVE" in engine.explain("DEMO-NEGATIVE", demo))

    print("\n%s" % ("%d FAILED: %s" % (len(FAILS), FAILS) if FAILS else "all engine tests passed"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
