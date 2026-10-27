"""Run ERC + export netlist from the generated schematic and compare with netlist.py."""
import json
import os
import re
import subprocess
import sys

# Shared stage: the project comes from the argument or the working directory, not from where this
# file happens to live. See boardgen/project.py for why these scripts are no longer copied per project.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen import project as _project  # noqa: E402

HERE = _project.gen_dir(_project.project_id_from_argv(sys.argv))
NL = _project.load_netlist(_project.project_id_from_argv(sys.argv))
from boardgen.sexp import find, find_all, parse  # noqa: E402

from boardgen.kicad_paths import CLI  # noqa: E402  - resolved once, see kicad_paths.py
SCH = os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + ".kicad_sch")
OUT = os.path.join(NL.PRJ_DIR, "out")
os.makedirs(OUT, exist_ok=True)


FAILURES = []


def run(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True)
    if r.returncode not in (0, 5):
        print("CMD FAILED", args, r.returncode, r.stdout[-2000:], r.stderr[-2000:])
        FAILURES.append("kicad-cli %s exited %d" % (" ".join(args[:3]), r.returncode))
    return r


net_path = os.path.join(OUT, "netlist.net")
run(["sch", "export", "netlist", "--format", "kicadsexpr", "-o", net_path, SCH])
if not os.path.isfile(net_path):
    sys.exit("FAILED: kicad-cli produced no netlist at %s" % net_path)
with open(net_path, encoding="utf-8") as f:
    exported = parse(f.read())

got = {}
for n in find_all(find(exported, "nets"), "net"):
    name = find(n, "name")[1].lstrip("/")
    if name.startswith("unconnected-"):
        continue
    members = {(find(nd, "ref")[1], find(nd, "pin")[1]) for nd in find_all(n, "node")
               if not find(nd, "ref")[1].startswith("#")}
    if members:
        got[name] = members

want = NL.nets()
bad = 0
for name in sorted(set(want) | set(got)):
    if want.get(name) != got.get(name):
        bad += 1
        print("NET MISMATCH %s\n  want %s\n  got  %s" % (name, sorted(want.get(name, [])), sorted(got.get(name, []))))
print("netlist compare: %d nets expected, %d exported, %d mismatches" % (len(want), len(got), bad))

erc_path = os.path.join(OUT, "erc.json")
run(["sch", "erc", "--format", "json", "--severity-all", "-o", erc_path, SCH])
if not os.path.isfile(erc_path):
    sys.exit("FAILED: kicad-cli produced no ERC report at %s" % erc_path)
with open(erc_path, encoding="utf-8") as f:
    erc = json.load(f)
counts = {}
for sheet in erc.get("sheets", []):
    for v in sheet.get("violations", []):
        key = (v["severity"], v["type"])
        counts[key] = counts.get(key, 0) + 1
        if counts[key] <= 3:
            print("ERC %s %s: %s | %s" % (v["severity"], v["type"], v["description"],
                                         "; ".join(i.get("description", "") for i in v.get("items", []))))
print("ERC summary:", {"%s/%s" % k: c for k, c in sorted(counts.items())})
erc_errors = sum(c for (sev, _), c in counts.items() if sev == "error")
erc_warnings = sum(c for (sev, _), c in counts.items() if sev == "warning")
print("ERC: %d errors, %d warnings" % (erc_errors, erc_warnings))

# Warning types that mean a real wiring mistake rather than style. Names verified against
# KiCad 10's _eeschema.dll. Each fails the stage unless waived (waivers.json, "check": "sch-check").
PROMOTED = ("ground_pin_not_ground", "isolated_pin_label", "power_pin_not_driven",
            "pin_to_pin", "pin_not_driven")
from boardgen import waivers as _waivers  # noqa: E402
_wl, _wproblems = _waivers.load(os.path.basename(NL.PRJ_DIR), "sch-check")
for where, msg in _wproblems:
    FAILURES.append("%s: %s" % (where, msg))
fired = {}
for sheet in erc.get("sheets", []):
    for v in sheet.get("violations", []):
        if v["type"] not in PROMOTED or v["severity"] == "error":   # errors already fail above
            continue
        descs = [i.get("description", "") for i in v.get("items", [])]
        refs = [m for d in descs for m in re.findall(r"of ([^\s]+)\s*$", d)]
        if any(_waivers.matches(w, v["type"], refs, []) for _, w in _wl):
            continue
        fired.setdefault(v["type"], []).append("%s | %s" % (v["description"], "; ".join(descs)))
for t, items in sorted(fired.items()):
    print("PROMOTED ERC WARNING %s x%d:" % (t, len(items)))
    for it in items[:5]:
        print("   ", it)
    FAILURES.append("%d ERC %s (promoted warning)" % (len(items), t))
print("promoted ERC warnings fired: %s" % (sorted(fired) or "none"))
if bad:
    FAILURES.append("%d netlist mismatches" % bad)
if erc_errors:
    FAILURES.append("%d ERC errors" % erc_errors)
if FAILURES:
    sys.exit("FAILED: " + "; ".join(FAILURES))
