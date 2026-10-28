"""Scaffold commands (PA-8):  python pipeline.py --scaffold <kind> <NAME>

kinds: rule (id like EL-FOO), stage, mutation, part (NAME = LCSC id, delegates to tools/parts.py new), block, project.
Templates live in tools/boardgen/templates/. Existing files are never overwritten (all targets are checked first, so a
refusal leaves nothing half-written). Files are written with LF. Fab profiles: no profile file format exists yet
(fab rules are code in fab_rules.py), so there is nothing to scaffold for them.

    rule      tools/boardgen/rules/<id>.py (auto-registered: the engine imports every rules/*.py),
              docs/rules/<ID>.md, tests/rules/fixtures/<ID>/{green,red}.json, and a "status": "planned" mutation M-<id>
              in tests/mutations/mutations.json. The stub reports NOT_JUDGED, so `ci_checks.py rules` stays red until the
              rule, its fixtures and the mutation are filled in (that is the to-do list).
    stage     tools/boardgen/<name>.py (fail-closed stub) + an entry APPENDED to tools/boardgen/stages.json
    mutation  a planned entry appended to tests/mutations/mutations.json
    block     blocks/<name>.json
    project   projects/<name>/{README.md, gen/netlist.py, gen/make_pcb.py}
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TEMPLATES = os.path.join(HERE, "templates")

RULE_RE = re.compile(r"^[A-Z]{2,4}-[A-Z0-9-]+$")              # same as rules/engine.py ID_RE
SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")        # stage / project / block names
MUT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
KINDS = ("rule", "stage", "mutation", "part", "block", "project")


class ScaffoldError(Exception):
    pass


def _template(name, subs):
    with open(os.path.join(TEMPLATES, name), encoding="utf-8", newline="") as f:
        text = f.read().replace("\r\n", "\n")
    for k, v in subs.items():
        text = text.replace("@%s@" % k, v)
    return text


def _plan_files(root, files):
    """files: {relative path: text}. Refuse if any target exists; then write all (LF)."""
    clash = [p for p in files if os.path.exists(os.path.join(root, p))]
    if clash:
        raise ScaffoldError("refusing to overwrite existing file(s): %s" % ", ".join(sorted(clash)))
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return sorted(files)


def _append_json_item(path, item, array_key=None, indent=2):
    """Append one item to a JSON array file (top-level, or under array_key) WITHOUT reformatting the rest."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    data = json.loads(text)
    arr = data[array_key] if array_key else data
    if any(isinstance(x, dict) and x.get("id", x.get("name")) == item.get("id", item.get("name")) for x in arr):
        raise ScaffoldError("%s already has an entry %r" % (os.path.basename(path), item.get("id", item.get("name"))))
    close = text.rfind("]")                          # the array's closing bracket is the last "]" in both files
    head = text[:close].rstrip()
    pad = " " * indent
    if array_key:
        entry = pad * 2 + json.dumps(item, indent=2, ensure_ascii=False).replace(chr(10), nl + pad * 2)
    else:
        entry = pad + json.dumps(item, ensure_ascii=False)
    new = head + "," + nl + entry + nl + (pad if array_key else "") + text[close:]
    json.loads(new)                                  # never leave an invalid file behind
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)


def _mutation_item(mid, description, fixture="blinky-555"):
    return {"id": mid, "fixture": fixture, "description": description, "op": {"type": "none"}, "stages": [],
            "expect_stage": "TODO", "expect_text": "", "status": "planned",
            "needs": "scaffold: fill op / stages / expect_stage / expect_text, run it, then delete \"status\""}


def scaffold_rule(root, rid):
    if not RULE_RE.match(rid):
        raise ScaffoldError("rule id %r must match [A-Z]{2,4}-[A-Z0-9-]+ (e.g. EL-MY-CHECK)" % rid)
    mod, mid = rid.lower().replace("-", "_"), "M-" + rid.lower()
    subs = {"ID": rid, "MOD": mod, "MUT": mid}
    mpath = os.path.join(root, "tests", "mutations", "mutations.json")
    with open(mpath, encoding="utf-8") as f:
        if any(m["id"] == mid for m in json.load(f)):
            raise ScaffoldError("mutation %s already exists in mutations.json" % mid)
    files = {"tools/boardgen/rules/%s.py" % mod: _template("rule.py.tmpl", subs),
             "docs/rules/%s.md" % rid: _template("rule.md.tmpl", subs),
             "tests/rules/fixtures/%s/green.json" % rid: _template("fixture.json.tmpl", dict(subs, EXPECTED="[]")),
             "tests/rules/fixtures/%s/red.json" % rid: _template("fixture.json.tmpl", dict(subs, EXPECTED="[]"))}
    made = _plan_files(root, files)
    _append_json_item(mpath, _mutation_item(mid, "TODO the mistake rule %s must catch" % rid))
    return made + ["tests/mutations/mutations.json (+%s, planned)" % mid]


def scaffold_stage(root, name):
    if not SLUG_RE.match(name):
        raise ScaffoldError("stage name %r must be lowercase letters/digits/hyphens (e.g. my-stage)" % name)
    spath = os.path.join(root, "tools", "boardgen", "stages.json")
    with open(spath, encoding="utf-8") as f:
        if any(s["name"] == name for s in json.load(f)["stages"]):
            raise ScaffoldError("stage %r already in stages.json" % name)
    mod = name.replace("-", "_")
    made = _plan_files(root, {"tools/boardgen/%s.py" % mod: _template("stage.py.tmpl", {"NAME": name, "MOD": mod})})
    entry = {"name": name, "description": "TODO what this stage does, one sentence.", "applies": "has_netlist",
             "interpreter": "system", "cwd": "root", "argv": ["{boardgen}/%s.py" % mod, "{project}"],
             "design_stage": False, "inputs": ["tools/boardgen/%s.py" % mod, "projects/{project}/gen/*.py"],
             "outputs": []}
    _append_json_item(spath, entry, array_key="stages")
    return made + ["tools/boardgen/stages.json (+%s, appended last: move it to its place in the order)" % name]


def scaffold_mutation(root, mid):
    if not MUT_RE.match(mid):
        raise ScaffoldError("mutation id %r must match [A-Za-z][A-Za-z0-9-]* (e.g. M-my-mistake)" % mid)
    _append_json_item(os.path.join(root, "tests", "mutations", "mutations.json"),
                      _mutation_item(mid, "TODO the mistake this models, one sentence."))
    return ["tests/mutations/mutations.json (+%s, planned)" % mid]


def scaffold_block(root, name):
    if not SLUG_RE.match(name):
        raise ScaffoldError("block name %r must be lowercase letters/digits/hyphens" % name)
    return _plan_files(root, {"blocks/%s.json" % name: _template("block.json.tmpl", {"NAME": name})})


def scaffold_project(root, name):
    if not SLUG_RE.match(name):
        raise ScaffoldError("project id %r must be lowercase letters/digits/hyphens (e.g. my-board)" % name)
    subs = {"NAME": name}
    return _plan_files(root, {
        "projects/%s/README.md" % name: _template("project_README.md.tmpl", subs),
        "projects/%s/gen/netlist.py" % name: _template("project_netlist.py.tmpl", subs),
        "projects/%s/gen/make_pcb.py" % name: _template("project_make_pcb.py.tmpl", subs)})


def scaffold_part(root, lcsc):
    if not re.match(r"^C\d+$", lcsc):
        raise ScaffoldError("part NAME is an LCSC id like C2895470")
    r = subprocess.run([sys.executable, os.path.join(root, "tools", "parts.py"), "new", lcsc], cwd=root)
    if r.returncode != 0:
        raise ScaffoldError("tools/parts.py new exited %d" % r.returncode)
    return ["(see tools/parts.py output: parts/records/)"]


def scaffold(kind, name, root=ROOT):
    """-> list of created/changed paths. Raises ScaffoldError."""
    fn = {"rule": scaffold_rule, "stage": scaffold_stage, "mutation": scaffold_mutation, "part": scaffold_part,
          "block": scaffold_block, "project": scaffold_project}.get(kind)
    if fn is None:
        raise ScaffoldError("unknown kind %r (use: %s)" % (kind, ", ".join(KINDS)))
    return fn(root, name)


def run_cli(kind, name):
    try:
        made = scaffold(kind, name)
    except ScaffoldError as e:
        raise SystemExit("ERROR: %s" % e)
    print("scaffolded %s %s:" % (kind, name))
    for p in made:
        print("  " + p)
    print("next: docs/CONTRIBUTING.md, section 'How to add a %s'" % kind)
