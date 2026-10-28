"""Rule engine (P2-T1; spec docs/design/P2_ELECTRICAL_ANALYZER.md sections 1 and 8).

A rule is a pure function of the design IR, registered with metadata that makes it explainable and provable:

    @rule(id="LINT-SHORT", severity="ERROR", needs=("parts",), doc="docs/rules/LINT-SHORT.md",
          fixture="tests/rules/fixtures/LINT-SHORT", mutation="M-merge", legacy_id="short")
    def check(ctx):
        for ref, p in sorted(ctx.ir["parts"].items()):
            ctx.examined()
            if ...:
                yield ctx.finding("ERROR", "why text", where={"ref": ref}, ...)

ctx.ir exposes ONLY the sections named in `needs` (a rule cannot silently read anything else); ctx.examined(n) counts items
looked at; ctx.not_judged(...) emits a NOT_JUDGED finding (counted as examined but not judged).
The registry validates at load time: id format + uniqueness (on `@rule`), then (`validate()`) that the doc file, the fixture
directory (green.json + red.json) and the mutation id exist. A rule missing any of them is "not supported" and fails
validation - which `run()`, `ci_checks.py` and `--explain` all call.
Fixture format: <fixture>/green.json = {"ir": {...}, "expected": []} (must produce no finding) and
<fixture>/red.json = the same IR after the mutation, with "expected" = a list of {field: value} subsets of the findings
it must produce (at least one ERROR); `line` is compared against Finding.line() so legacy output stays byte-identical.
"""
import json
import os
import re

from boardgen import waivers as _waivers
from boardgen.rules.finding import Finding, SEVERITIES

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))          # the workspace root
ID_RE = re.compile(r"^[A-Z]{2,4}-[A-Z0-9-]+$")
IR_SECTIONS = ("meta", "parts", "nets", "board", "assembly", "fab_profile", "requirements", "electrical")
TIERS = ("hand", "pcba")
_NOT_RULES = {"engine", "finding", "__init__", "__main__"}


class RuleError(Exception):
    """A rule is registered wrongly or is missing its doc / fixture / mutation."""


class Rule:
    def __init__(self, fn, id, severity, needs, doc, fixture, mutation, applies, tiers, legacy_id, expect_items):
        self.fn, self.id, self.severity, self.needs = fn, id, severity, tuple(needs)
        self.doc, self.fixture, self.mutation = doc, fixture, mutation
        self.applies, self.tiers, self.legacy_id, self.expect_items = applies, frozenset(tiers), legacy_id, expect_items


class _View:
    """Read-only access to the declared IR sections only. `derived` maps a section that is not stored in the IR (the
    electrical model, "electrical") to a callable that builds it on first access."""
    def __init__(self, rule, ir, derived=None):
        self._rule, self._ir, self._derived = rule, ir, derived or {}

    def __getitem__(self, key):
        if key not in self._rule.needs:
            raise KeyError("rule %s did not declare needs=(%r,): it may read only %s" % (self._rule.id, key, self._rule.needs))
        if key not in self._ir and key in self._derived:
            return self._derived[key]()
        return self._ir[key]

    def get(self, key, default=None):
        return self[key] if key in self._rule.needs and (key in self._ir or key in self._derived) else default


class Context:
    def __init__(self, rule, ir, shared=None):
        self.rule, self._raw_ir = rule, ir
        self._shared = shared if shared is not None else {}       # per-run cache, so the model is built once per run
        self.ir = _View(rule, ir, {"electrical": lambda: self.model.to_dict()})
        self.n_examined = 0

    @property
    def model(self):
        """The derived electrical model (boardgen.elec.model.ElecModel), built lazily once per run from the full IR.
        A rule must declare "electrical" in `needs` to use it."""
        if "electrical" not in self.rule.needs:
            raise KeyError("rule %s did not declare needs=('electrical',): it may not use ctx.model" % self.rule.id)
        if "model" not in self._shared:
            from boardgen.elec.model import build_model
            self._shared["model"] = build_model(self._raw_ir)
        return self._shared["model"]

    def examined(self, n=1):
        self.n_examined += n

    def finding(self, severity, why, **kw):
        kw.setdefault("legacy_id", self.rule.legacy_id)
        return Finding(self.rule.id, severity, why, doc=self.rule.doc, **kw)

    def not_judged(self, why, **kw):
        return self.finding("NOT_JUDGED", why, **kw)


class Registry:
    def __init__(self, root=ROOT, mutation_ids=None):
        """root: base for the relative doc/fixture paths. mutation_ids: the ids a rule may name (default: the ids in
        tests/mutations/mutations.json)."""
        self.root, self._mutations, self.rules, self._valid = root, mutation_ids, {}, False

    def mutation_ids(self):
        if self._mutations is None:
            with open(os.path.join(ROOT, "tests", "mutations", "mutations.json"), encoding="utf-8") as f:
                self._mutations = {m["id"] for m in json.load(f)}
        return self._mutations

    def rule(self, id, severity, needs, doc, fixture, mutation, applies=None, tiers=TIERS, legacy_id=None,
             expect_items=False):
        if not ID_RE.match(id or ""):
            raise RuleError("rule id %r must match %s" % (id, ID_RE.pattern))
        if severity not in SEVERITIES[:3]:
            raise RuleError("%s: severity must be ERROR|WARN|INFO" % id)
        bad = [n for n in needs if n not in IR_SECTIONS]
        if bad:
            raise RuleError("%s: needs %s are not IR sections %s" % (id, bad, IR_SECTIONS))
        if not tiers or not set(tiers) <= set(TIERS):
            raise RuleError("%s: tiers must be a non-empty subset of %s" % (id, TIERS))

        def deco(fn):
            if id in self.rules:
                raise RuleError("duplicate rule id %s" % id)
            self.rules[id] = Rule(fn, id, severity, needs, doc, fixture, mutation, applies or (lambda ir: True), tiers,
                                  legacy_id, expect_items)
            self._valid = False
            return fn
        return deco

    def load_builtin(self):
        import importlib
        for fn in sorted(os.listdir(HERE)):
            mod = fn[:-3]
            if fn.endswith(".py") and mod not in _NOT_RULES and not mod.startswith("_"):
                importlib.import_module("boardgen.rules." + mod)

    def validate(self):
        """Every rule has a doc, a fixture (green.json + red.json) and a mutation that exists. -> list of problems."""
        problems = []
        for r in self.rules.values():
            if not os.path.isfile(os.path.join(self.root, r.doc)):
                problems.append("%s: doc %s does not exist" % (r.id, r.doc))
            for f in ("green.json", "red.json"):
                if not os.path.isfile(os.path.join(self.root, r.fixture, f)):
                    problems.append("%s: fixture %s/%s does not exist" % (r.id, r.fixture, f))
            if r.mutation not in self.mutation_ids():
                problems.append("%s: mutation %r is not a known mutation id" % (r.id, r.mutation))
        return problems

    def _require_valid(self):
        if not self._valid:
            problems = self.validate()
            if problems:
                raise RuleError("rule registry invalid (a rule without doc/fixture/mutation is not supported):\n  "
                                + "\n  ".join(problems))
            self._valid = True

    def get(self, key):
        """A rule by id or legacy id."""
        for r in self.rules.values():
            if key in (r.id, r.legacy_id):
                return r
        raise RuleError("unknown rule %r (known: %s)" % (key, ", ".join(sorted(self.rules))))

    def run(self, ir, only=None, tier=None):
        """Run rules over `ir` -> (findings, stats). stats[rule id] = {examined, judged, not_judged, errors, warns,
        waived, skipped}; examined = judged + not_judged, so a pass can never hide a skipped item. `only`: rule ids
        (or legacy names)."""
        self._require_valid()
        findings, stats, shared = [], {}, {}
        for rid in sorted(self.rules):
            r = self.rules[rid]
            if only is not None and rid not in only and r.legacy_id not in only:
                continue
            if tier is not None and tier not in r.tiers:
                continue
            if not r.applies(ir):
                stats[rid] = {"skipped": True}
                continue
            ctx = Context(r, ir, shared)
            out = list(r.fn(ctx) or [])
            for f in out:
                if not isinstance(f, Finding):
                    raise RuleError("%s yielded %r, not a Finding" % (rid, f))
            if r.expect_items and ctx.n_examined == 0:                    # fail closed: nothing examined is not a pass
                out.append(ctx.finding("ERROR", "rule examined 0 items on this design (fail closed)"))
            findings += out
            nj = sum(1 for f in out if f.severity == "NOT_JUDGED")
            stats[rid] = {"examined": ctx.n_examined, "judged": ctx.n_examined - nj, "not_judged": nj, "skipped": False,
                          "errors": sum(1 for f in out if f.severity == "ERROR"),
                          "warns": sum(1 for f in out if f.severity == "WARN"), "waived": 0}
        return findings, stats


def apply_waivers(project_id, check, findings, stats=None):
    """Waivers v2 (docs/design section 1.3): a waiver demotes ONLY an unwaived ERROR to WAIVED, never NOT_JUDGED/WARN/INFO.
    -> extra findings (waiver problems, unused waivers). Keeps `stats[rule]['waived']` current when given."""
    ws, problems = _waivers.load(project_id, check)
    extra = _waivers.apply(findings, ws, problems)
    if stats is not None:
        for f in findings:
            if f.waived is not None and f.rule in stats:
                stats[f.rule]["waived"] += 1
    return extra


REGISTRY = Registry()
rule = REGISTRY.rule


def run(ir, only=None, tier=None):
    REGISTRY.load_builtin()
    return REGISTRY.run(ir, only=only, tier=tier)


# ------------------------------------------------------------------------------------------------ fixtures
def _subset(expected, actual):
    return all(actual.get(k) == v for k, v in expected.items())


def check_fixtures(reg):
    """Run every rule on its fixture: green must give no finding; red (the mutation) must give at least one ERROR and
    exactly the expected findings. -> list of problems."""
    problems = []
    for r in sorted(reg.rules.values(), key=lambda x: x.id):
        for name in ("green", "red"):
            path = os.path.join(reg.root, r.fixture, name + ".json")
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                findings, _stats = reg.run(data["ir"], only=[r.id])
            except Exception as e:  # noqa: BLE001
                problems.append("%s %s: %r" % (r.id, name, e))
                continue
            have = [dict(f.to_dict(), line=f.line()) for f in findings]
            want = data.get("expected", [])
            if name == "green" and have:
                problems.append("%s green fixture produced %d finding(s): %s" % (r.id, len(have), have[0]["line"]))
            if name == "red":
                if not any(h["severity"] == "ERROR" for h in have):
                    problems.append("%s red fixture (mutation %s) produced no ERROR - the rule would not catch it"
                                    % (r.id, r.mutation))
                if len(have) != len(want) or not all(_subset(w, h) for w, h in zip(want, have)):
                    problems.append("%s red fixture: findings differ from expected\n    have: %s\n    want: %s"
                                    % (r.id, [h["line"] for h in have], [w.get("line", w) for w in want]))
    return problems


def selftest(reg=None):
    """Registry valid, fixtures pass, and the registry check itself catches a rule with no doc / fixture / mutation."""
    reg = reg or REGISTRY
    if reg is REGISTRY:
        reg.load_builtin()
    problems = reg.validate() + check_fixtures(reg)
    probe = Registry(root=reg.root, mutation_ids={"M-probe"})
    probe.rule("ZZ-PROBE", "ERROR", ("parts",), "no/such.md", "no/such", "M-nope")(lambda ctx: [])
    caught = probe.validate()
    if len(caught) != 4:
        problems.append("registry check self-test: expected 4 problems for a rule with no doc/fixture/mutation, got %r"
                        % caught)
    return problems


# ----------------------------------------------------------------------------------------------- explain
def explain(key, reg=None):
    reg = reg or REGISTRY
    if reg is REGISTRY:
        reg.load_builtin()
    r = reg.get(key)
    bad = [p for p in reg.validate() if p.startswith(r.id + ":")]
    if bad:
        raise RuleError("; ".join(bad))
    with open(os.path.join(reg.root, r.doc), encoding="utf-8") as f:
        doc = f.read().rstrip()
    out = ["%s  (%s)%s" % (r.id, r.severity, "  legacy name: %s" % r.legacy_id if r.legacy_id else ""),
           "tiers: %s    needs IR sections: %s" % (", ".join(sorted(r.tiers)), ", ".join(r.needs) or "-"),
           "", doc, ""]
    desc = ""
    mpath = os.path.join(ROOT, "tests", "mutations", "mutations.json")
    if os.path.isfile(mpath):
        with open(mpath, encoding="utf-8") as f:
            desc = next((m.get("description", "") for m in json.load(f) if m["id"] == r.mutation), "")
    out += ["mutation: %s%s" % (r.mutation, " - " + desc if desc else ""), "fixture: %s" % r.fixture]
    with open(os.path.join(reg.root, r.fixture, "red.json"), encoding="utf-8") as f:
        red = json.load(f)
    findings, _s = reg.run(red["ir"], only=[r.id])
    out.append("example finding (from the red fixture):")
    for f in findings[:3]:
        out.append("  " + f.line())
        d = f.to_dict()
        out.append("  " + json.dumps({k: d[k] for k in ("where", "measured", "limit", "fingerprint")}, sort_keys=True))
    return "\n".join(out)


def write_findings(path, findings, stats):
    """Run-report hook: the stage's structured findings + per-rule stats as JSON (pipeline.py puts them in report.json)."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"findings": [x.to_dict() for x in findings], "rules": stats}, f, indent=1)
        f.write("\n")
