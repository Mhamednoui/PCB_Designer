"""Shared waiver loading for every checker stage: projects/<id>/waivers.json =
[{"check": "<stage>", "rule": "<id>", "refs": [...] | "nets": [...], "why": "<required, >= 20 chars>",
  "by": "<who>", "date": "<when>", "expires": "YYYY-MM-DD"}].
A waiver without refs/nets matches the whole rule. `check` defaults to "lint" (legacy).
Waivers v2 (P2-T1): `why` must be at least MIN_WHY characters; an `expires` date in the past makes the waiver an ERROR
(reported as a problem, not applied); a waiver demotes ONLY an ERROR finding to WAIVED - never NOT_JUDGED, WARN or INFO
(missing data is fixed in the record, not waived); an unused waiver is a WARN (`apply`)."""
import datetime
import json
import os

from boardgen import project as _project


MIN_WHY = 20


def today():
    return datetime.date.today()


def load(project_id, check):
    """-> (list of (index, waiver) for this check, list of problem strings)."""
    path = os.path.join(_project.PROJECTS, project_id, "waivers.json")
    if not os.path.isfile(path):
        return [], []
    try:
        data = json.load(open(path, encoding="utf-8"))
        assert isinstance(data, list)
    except (ValueError, AssertionError) as e:
        return [], [("waivers.json", "unreadable or not a list: %s" % e)]
    out, problems = [], []
    for i, w in enumerate(data):
        if not isinstance(w, dict) or w.get("check", "lint") != check:
            continue
        if not str(w.get("why", "")).strip():
            problems.append(("waivers.json[%d]" % i, "waiver for rule %r has no 'why'" % w.get("rule")))
            continue
        if len(str(w["why"]).strip()) < MIN_WHY:
            problems.append(("waivers.json[%d]" % i, "waiver for rule %r: 'why' must be at least %d characters"
                             % (w.get("rule"), MIN_WHY)))
            continue
        if w.get("expires") is not None:
            try:
                exp = datetime.date.fromisoformat(str(w["expires"]))
            except ValueError:
                problems.append(("waivers.json[%d]" % i, "waiver for rule %r: 'expires' %r is not YYYY-MM-DD"
                                 % (w.get("rule"), w["expires"])))
                continue
            if exp < today():
                problems.append(("waivers.json[%d]" % i, "waiver for rule %r expired on %s" % (w.get("rule"), exp)))
                continue
        out.append((i, w))
    return out, problems


def matches(w, rule, refs, nets):
    if w.get("rule") not in ((rule,) if isinstance(rule, str) else tuple(rule)):
        return False
    wr, wn = set(w.get("refs") or []), set(w.get("nets") or [])
    return bool((wr and wr & set(refs)) or (wn and wn & set(nets)) or (not wr and not wn))


def describe(w):
    return sorted(set(w.get("refs") or []) | set(w.get("nets") or [])) or "all"


def apply(findings, ws, problems=()):
    """Apply the waivers `ws` (from load) to Finding objects (boardgen.rules.finding): an unwaived ERROR matching a waiver
    gets `waived`. -> extra findings: one ERROR per load problem, one WARN per unused waiver."""
    from boardgen.rules.finding import Finding
    extra = [Finding("waiver", "ERROR", m, target=t) for t, m in problems]
    for i, w in ws:
        used = False
        for f in findings:
            if f.severity == "ERROR" and f.waived is None and matches(w, f.rule_ids, f.refs, f.nets):
                f.waived = {"why": w["why"], "by": w.get("by"), "date": w.get("date")}
                used = True
        if not used:
            extra.append(Finding("waiver", "WARN", "unused waiver (rule %r, %s)" % (w.get("rule"), describe(w)),
                                 target="waivers.json[%d]" % i))
    return extra
