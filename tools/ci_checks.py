#!/usr/bin/env python3
"""CI / pre-commit gate (PLATFORM_PLAN 11.1). Needs neither KiCad, Freerouting nor LTspice.

  python tools/ci_checks.py all
  python tools/ci_checks.py compile secrets ctrlchars     (the fast pre-commit set)

Sub-checks: compile schemas selftests rules elec secrets ctrlchars ruff. Each prints PASS/FAIL; exit 1 on any FAIL.
Everything that needs KiCad, Freerouting, LTspice or the network (pipeline stages, mutation suite, fab
output) is NOT covered here - it runs locally. See docs/CONTRIBUTING.md.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "boardgen"))

BINARY_EXT = {".glb", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf", ".step", ".stp", ".woff", ".woff2",
              ".ico", ".exe", ".msi", ".drl", ".kicad_prl", ".raw", ".bin", ".hex", ".elf", ".gz", ".pyc"}


def tracked(pattern=None):
    cmd = ["git", "ls-files", "-z"] + ([pattern] if pattern else [])
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p and os.path.isfile(os.path.join(ROOT, p))]


def text_files():
    return [p for p in tracked() if os.path.splitext(p)[1].lower() not in BINARY_EXT]


def read_bytes(p):
    with open(os.path.join(ROOT, p), "rb") as f:
        return f.read()


def check_compile():
    bad = []
    files = tracked("*.py")
    for p in files:
        try:
            compile(read_bytes(p), p, "exec")
        except (SyntaxError, ValueError) as e:
            bad.append("%s: %s" % (p, e))
    print("  compiled %d first-party .py files" % len(files))
    return bad, []


def check_schemas():
    import parts
    bad = []
    try:
        recs = parts.load_all()                     # fail closed: raises listing every problem
        print("  parts registry: %d records valid (own validator)" % len(recs))
    except Exception as e:  # noqa: BLE001
        bad.append("parts.load_all: %s" % e)
    try:
        import jsonschema
        sch = json.loads(read_bytes("parts/schema.json"))
        n = 0
        for p in tracked("parts/records/*.json"):
            try:
                jsonschema.validate(json.loads(read_bytes(p)), sch)
                n += 1
            except jsonschema.ValidationError as e:
                bad.append("%s: jsonschema: %s" % (p, e.message))
        print("  jsonschema: %d records valid" % n)
    except ImportError:
        print("  jsonschema not installed: only the registry's own validator ran")
    sys.path.insert(0, ROOT)
    try:
        import pipeline
        pipeline.load_registry()
        print("  stages.json valid (pipeline.load_registry)")
    except SystemExit as e:
        bad.append("stages.json: %s" % e)
    try:
        ir_sch = json.loads(read_bytes("tools/boardgen/ir/schema.json"))
        if ir_sch.get("properties", {}).get("ir_version", {}).get("enum") != [2]:
            bad.append("ir/schema.json: ir_version must be pinned to [2]")
        try:
            import jsonschema
            jsonschema.Draft7Validator.check_schema(ir_sch)
            print("  design IR schema valid (jsonschema, draft 7)")
        except ImportError:
            print("  design IR schema parsed (jsonschema not installed: structure checked by the ir selftest)")
    except ValueError as e:
        bad.append("ir/schema.json: invalid JSON: %s" % e)
    except Exception as e:  # noqa: BLE001
        bad.append("ir/schema.json: %s" % e)
    muts = json.loads(read_bytes("tests/mutations/mutations.json"))
    if not isinstance(muts, list) or not muts:
        bad.append("mutations.json: need a non-empty array")
        muts = []
    ids = [m.get("id") for m in muts]
    for m in muts:
        for k in ("id", "description"):
            if not isinstance(m.get(k), str):
                bad.append("mutations.json %s: missing %s" % (m.get("id"), k))
        if m.get("status") != "planned" and not ("fixture" in m and "expect_stage" in m):
            bad.append("mutations.json %s: active entry needs fixture and expect_stage" % m.get("id"))
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        bad.append("mutations.json: duplicate id %s" % i)
    print("  mutations.json: %d entries checked" % len(ids))
    return bad, []


def check_selftests():
    bad = []
    for cmd in ([sys.executable, "tools/boardgen/parts.py", "--selftest"],
                [sys.executable, "tools/parts.py", "selftest"],
                [sys.executable, "tools/boardgen/ir/build.py", "--selftest"],
                [sys.executable, "tests/scaffold/test_scaffold.py"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        tail = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        print("  %s -> %s" % (" ".join(cmd[1:]), tail))
        if r.returncode != 0:
            bad.append("%s exited %d: %s" % (" ".join(cmd[1:]), r.returncode, tail))
    print("  SKIP: mutation suite and netlist/pinmap checks (need KiCad; run locally)")
    return bad, []


SECRET_PATTERNS = [
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("wokwi token", re.compile(r"\bwok_[A-Za-z0-9_\-]{20,}")),
    ("wokwi token assignment",
     re.compile(r"WOKWI_CLI_TOKEN\s*[=:]\s*['\"]?(?![$%<]|your|xxx|\.\.\.)[A-Za-z0-9_\-]{20,}", re.I)),
    ("secret assignment",
     re.compile(r"(?i)\b[\w-]*(?:api[_-]?key|token|secret|passw(?:or)?d)[\w-]*\s*[=:]\s*['\"][A-Za-z0-9+/_=\-]{32,}['\"]")),
]
SHA_OK = re.compile(r"(?i)sha-?256|hash|digest|checksum")


def check_secrets():
    bad = []
    for p in text_files():
        for n, line in enumerate(read_bytes(p).decode("utf-8", "replace").splitlines(), 1):
            if len(line) > 4000:
                continue
            for name, rx in SECRET_PATTERNS:
                if rx.search(line) and not (name == "secret assignment" and SHA_OK.search(line)):
                    bad.append("%s:%d: possible %s" % (p, n, name))
    return bad, []


CTRL = re.compile(rb"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def check_ctrlchars():
    bad = []
    for p in text_files():
        data = read_bytes(p)
        m = CTRL.search(data)
        if m:
            line = data.count(b"\n", 0, m.start()) + 1
            bad.append("%s:%d: control byte 0x%02x" % (p, line, data[m.start()]))
    return bad, []


def check_ruff():
    cmd = [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "F", "--output-format", "concise",
           "--no-cache", "--exit-zero"] + [p for p in tracked("*.py") if not p.startswith(".claude/")]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if "No module named ruff" in r.stderr:
        print("  SKIP: ruff not installed (pip install ruff); vendored .claude/skills is excluded")
        return [], []
    lines = [ln for ln in r.stdout.splitlines() if re.match(r"^.+:\d+:\d+: F\d+", ln)]
    errors = [ln for ln in lines if re.search(r": F(821|822|823|63\d|70\d) ", ln)]   # undefined names, syntax-type
    warns = [ln for ln in lines if ln not in errors]
    print("  pyflakes findings: %d (%d errors, %d warnings)" % (len(lines), len(errors), len(warns)))
    return errors, warns


def check_rules():
    """Rule-engine registry check (P2-T1): every registered rule has a doc, a fixture (green + red) and a mutation id that
    exists in mutations.json, its fixtures behave, and the engine's own tests pass."""
    bad = []
    for cmd in ([sys.executable, "tools/boardgen/rules", "--check"], [sys.executable, "tests/rules/test_engine.py"], [sys.executable, "tests/rules/test_el_conn_prot.py"], [sys.executable, "tests/req/test_eval.py"]):
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = r.stdout.strip().splitlines() or ["(no output)"]
        print("  %s -> %s" % (" ".join(cmd[1:]), lines[-1]))
        if r.returncode != 0:
            bad += ["%s exited %d" % (" ".join(cmd[1:]), r.returncode)] + ["    " + ln for ln in lines if "FAIL" in ln or ln.startswith("  ")][:10]
    return bad, []


def check_elec():
    """Electrical model tests (P2-T3): divider fixtures, blinky-555 hand calculations, synthetic LDO board, FET states,
    pull defaults, the ctx.model hook, reflex-machine counts."""
    bad = []
    for test in ("tests/elec/test_model.py", "tests/elec/test_budget.py"):
        r = subprocess.run([sys.executable, test], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        lines = r.stdout.strip().splitlines() or ["(no output)"]
        print("  %s -> %s" % (test, lines[-1]))
        if r.returncode != 0:
            bad += ["%s exited %d" % (test, r.returncode)] + ["    " + ln for ln in lines if "FAIL" in ln][:10]
            if r.stderr.strip():
                bad.append("    " + r.stderr.strip().splitlines()[-1])
    return bad, []


CHECKS = {"compile": check_compile, "schemas": check_schemas, "selftests": check_selftests, "rules": check_rules,
          "elec": check_elec, "secrets": check_secrets, "ctrlchars": check_ctrlchars, "ruff": check_ruff}


def main(argv):
    names = argv or ["all"]
    if "all" in names:
        names = list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print("unknown check(s): %s (valid: all %s)" % (", ".join(unknown), " ".join(CHECKS)))
        return 2
    failed = 0
    for n in names:
        print("[%s]" % n)
        try:
            bad, warns = CHECKS[n]()
        except Exception as e:  # noqa: BLE001
            bad, warns = ["check crashed: %r" % e], []
        for w in warns[:20]:
            print("  warn  " + w)
        if len(warns) > 20:
            print("  warn  ... %d more" % (len(warns) - 20))
        for b in bad:
            print("  " + b)
        print("%s %s" % ("FAIL" if bad else "PASS", n))
        failed += bool(bad)
    print("\n%s" % ("%d check(s) FAILED" % failed if failed else "all checks passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
