"""Shared waiver loading for every checker stage: projects/<id>/waivers.json =
[{"check": "<stage>", "rule": "<id>", "refs": [...] | "nets": [...], "why": "<required>"}].
A waiver without refs/nets matches the whole rule. `check` defaults to "lint" (legacy)."""
import json
import os

from boardgen import project as _project


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
        out.append((i, w))
    return out, problems


def matches(w, rule, refs, nets):
    if w.get("rule") != rule:
        return False
    wr, wn = set(w.get("refs") or []), set(w.get("nets") or [])
    return bool((wr and wr & set(refs)) or (wn and wn & set(nets)) or (not wr and not wn))


def describe(w):
    return sorted(set(w.get("refs") or []) | set(w.get("nets") or [])) or "all"
