"""Stage `release` (P2-T10a): the release coverage gate (docs/design/P2_ELECTRICAL_ANALYZER.md 4.2, 4.4).

    python tools/boardgen/make_release_gate.py <project-id>

Recomputes everything from projects/<id>/out/design.json (engine.run over every EL- rule, the REQUIREMENTS evaluator and the
coverage table of ir/coverage.py) - it never parses another stage's text output, so it cannot read a stale result.
The assembly mode comes from the IR (ADR 0012):
  pcba        FAILS (exit 1) on any missing required field (coverage table, tier hand+pcba), any NOT_JUDGED electrical rule
              finding, any requirement NOT_EVALUATED, or zero requirements. One Finding per blocker, naming part / pin / field
              and how to fix it.
  hand        prints the same table, NOT_JUDGED is allowed (INFO); blocks only on the `hand` cells of 4.2: an EXTERNAL
              declaration for every connector, and regulator data (vout, dropout, theta_ja, tj_max; the thermal pair only for
              a linear regulator - a switcher module has no junction to heat).
  undeclared  WARN "assembly mode undeclared - judged as hand".
A separate "SIGNED OFF" line (assumption A4): a release may contain crosschecked parts but is not signed off until the owner
verifies them. It never fails the stage. Writes projects/<id>/out/RELEASE_GATE.md (deterministic, LF).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                      # tools/
from boardgen import project as _project                       # noqa: E402
from boardgen import parts as _parts                            # noqa: E402
from boardgen.elec.model import build_model                     # noqa: E402
from boardgen.ir import coverage as _cov, natkey                # noqa: E402
from boardgen.req import eval as _eval                          # noqa: E402
from boardgen.rules import engine as _engine                    # noqa: E402
from boardgen.rules.finding import Finding                      # noqa: E402

RULE = "REL"
FIX = {
    "registry record": "add a registry record for the part (tools/parts.py), then reference it with registry_part()",
    "EXTERNAL declaration": "declare what the connector faces in netlist.py EXTERNAL (a pin entry with direction/range, or list the ref under 'none')",
    "pin.class": "set the pin class (power_in/output/...) in the record's pins block, cited from the datasheet",
    "pin.abs_max": "add a cited electrical.pins[pad].abs_max (v_min/v_max, with src URL + page) to the record",
    "pin.vih": "add cited vih to electrical.pins[pad] in the record", "pin.vil": "add cited vil to electrical.pins[pad] in the record",
    "pin.voh": "add cited voh to electrical.pins[pad] in the record", "pin.vol": "add cited vol to electrical.pins[pad] in the record",
    "regulator.vout": "add electrical.regulator.vout (cited) to the record",
    "regulator.dropout": "add electrical.regulator.dropout (cited) to the record",
    "load_ma.typ": "add electrical.load_ma.typ (cited) to the record", "load_ma.peak": "add electrical.load_ma.peak (cited) to the record",
}


def _fix(field):
    return FIX.get(field, "add the cited '%s' value to the part's registry record (electrical block, with src)" % field)


def _is_switcher(ir, ref):
    return ((ir["parts"][ref].get("electrical") or {}).get("regulator") or {}).get("topology") == "switcher_module"


def _blocks(mode_hand, tier, field, ir, refs):
    """Does a missing coverage cell block this release? pcba: always. hand: only tier-hand cells; the thermal pair of a
    switcher module is not applicable."""
    if not mode_hand:
        return True
    if tier != "hand":
        return False
    if field in ("theta_ja", "tj_max") and all(_is_switcher(ir, r) for r in refs):
        return False
    return True


def evaluate(ir):
    """-> dict(mode, hand, blockers, notes, rule_stats, req_summary, results, cov, signed)"""
    mode = (ir.get("assembly") or {}).get("mode")
    hand = mode != "pcba"
    blockers, notes = [], []
    # ---- coverage table (reused from ir/coverage.py)
    rows = _cov._project_table(ir)
    bad = {}
    for key, field, tier, ok, ref, pin in rows:
        if not ok:
            e = bad.setdefault((key, field, tier), {"refs": set(), "pins": set()})
            e["refs"].add(ref)
            if pin is not None:
                e["pins"].add(pin)
    for (key, field, tier), e in sorted(bad.items()):
        refs = sorted(e["refs"], key=natkey)
        pins = sorted(e["pins"], key=natkey)
        where = refs[0] + (" pins " + ",".join(pins) if pins else "")
        why = "%s: required field '%s' missing (record %s%s)" % (",".join(refs), field, key, "; pins " + ",".join(pins) if pins else "")
        if _blocks(hand, tier, field, ir, refs):
            blockers.append(Finding("REL-FIELD", "ERROR", why, target="%s.%s%s" % (refs[0], field, "(%s)" % ",".join(pins) if pins else ""), fix=_fix(field)))
        else:
            notes.append(Finding("REL-FIELD", "INFO", why + " - not required for a hand release", target="%s.%s" % (refs[0], field), fix=_fix(field)))
    # ---- electrical rules, recomputed
    _engine.REGISTRY.load_builtin()
    ids = sorted(r for r in _engine.REGISTRY.rules if r.startswith("EL-"))
    rfind, rstats = _engine.run(ir, only=ids)
    for f in rfind:
        if f.severity != "NOT_JUDGED":
            continue
        if hand:
            notes.append(Finding(f.rule, "INFO", f.why, target=f.target, fix=f.fix))
        else:
            blockers.append(Finding(f.rule, "ERROR", f.why, where=f.where, target=f.target,
                                    fix=f.fix or "supply the missing record/EXTERNAL data so the rule can judge it"))
    # ---- requirements, recomputed
    results = _eval.evaluate(ir, build_model(ir))
    for r in results:
        if r["result"] == "NOT_EVALUATED":
            if hand:
                notes.append(Finding("REQ-%s" % r["id"], "INFO", "%s: %s" % (r["text"], r["why"]), target=r["id"]))
            else:
                blockers.append(Finding("REQ-%s" % r["id"], "ERROR", "requirement not evaluated: %s (%s)" % (r["text"], r["why"]),
                                        target=r["id"], fix="give the evaluator the data it lacks, or rewrite the requirement in an evaluable kind"))
    if not results and not hand:
        blockers.append(Finding("REQ-NONE", "ERROR", "0 requirements: the board has nothing to be checked against", target="REQUIREMENTS",
                                fix="add REQUIREMENTS to netlist.py (path, path_absent, net_v, rail_peak, static_logic)"))
    # ---- sign-off (A4): informational only
    signed = []
    for rid in sorted({p["registry"] for p in ir["parts"].values() if p["registry"]}):
        try:
            tier = _parts.get(rid).get("verification")
        except _parts.RegistryError:
            tier = "missing"
        if tier != "verified":
            signed.append((rid, tier))
    return {"mode": mode, "hand": hand, "blockers": blockers, "notes": notes, "ids": ids, "rstats": rstats,
            "req": _eval.summary(results), "n_req": len(results), "rows": rows, "signed": signed}


def signoff_line(signed):
    if not signed:
        return "SIGNED OFF: yes - every registry part is at tier `verified`"
    return "SIGNED OFF: no - %d parts below `verified` (owner sign-off needed: %s)" % (
        len(signed), ", ".join("%s [%s]" % s for s in signed))


def render_md(pid, ev, verdict):
    rows = ev["rows"]
    out = ["# Release gate: %s" % pid, "",
           "Generated by `tools/boardgen/make_release_gate.py` from `out/design.json`. Do not edit.", "",
           "- assembly mode: **%s**%s" % (ev["mode"] or "undeclared", " (judged as hand, ADR 0012)" if ev["mode"] is None else ""),
           "- verdict: **%s** (%d blocker(s), %d non-blocking item(s))" % (verdict, len(ev["blockers"]), len(ev["notes"])),
           "- %s" % signoff_line(ev["signed"]), "", "## Field coverage", "", "| tier | required | present | NOT_JUDGED |", "|---|---|---|---|"]
    for tier in ("hand", "pcba"):
        sel = [r for r in rows if tier == "pcba" or r[2] == "hand"]
        ok = sum(1 for r in sel if r[3])
        out.append("| %s | %d | %d | %d |" % (tier, len(sel), ok, len(sel) - ok))
    out += ["", "## Electrical rules", "", "| rule | examined | judged | NOT_JUDGED | errors |", "|---|---|---|---|---|"]
    for rid in ev["ids"]:
        s = ev["rstats"].get(rid, {})
        if s.get("skipped"):
            out.append("| %s | n/a | | | |" % rid)
        else:
            out.append("| %s | %d | %d | %d | %d |" % (rid, s.get("examined", 0), s.get("judged", 0), s.get("not_judged", 0), s.get("errors", 0)))
    rq = ev["req"]
    out += ["", "## Requirements", "", "%d requirements: %d PASS, %d FAIL, %d NOT_EVALUATED, %d ERROR" % (
        ev["n_req"], rq["PASS"], rq["FAIL"], rq["NOT_EVALUATED"], rq["ERROR"]), ""]
    for title, items in (("Blockers", ev["blockers"]), ("Not required for this release (shown, never hidden)", ev["notes"])):
        out += ["## " + title, ""]
        if not items:
            out += ["none", ""]
            continue
        out += ["| item | rule | what is missing | how to fix |", "|---|---|---|---|"]
        for f in items:
            out.append("| %s | %s | %s | %s |" % (f.target, f.rule, f.why.replace("|", "/"), (f.fix or "").replace("|", "/")))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: make_release_gate.py <project-id>")
    path = os.path.join(_project.PROJECTS, pid, "out", "design.json")
    if not os.path.isfile(path):
        print("FAILED: %s missing - run the `ir` stage first" % path)
        return 1
    with open(path, encoding="utf-8") as f:
        ir = json.load(f)
    ev = evaluate(ir)
    findings = list(ev["blockers"])
    if ev["mode"] is None:
        findings.append(Finding("REL-MODE", "WARN", "assembly mode undeclared - judged as hand (declare ASSEMBLY = 'hand' or 'pcba' in netlist.py, ADR 0012)",
                                target="ASSEMBLY"))
        print("WARN REL-MODE ASSEMBLY: assembly mode undeclared - judged as hand")
    for f in ev["blockers"]:
        print(f.line() + "  -> fix: " + f.fix)
    verdict = "FAIL" if ev["blockers"] else "PASS"
    out_dir = os.path.join(_project.PROJECTS, pid, "out")
    with open(os.path.join(out_dir, "RELEASE_GATE.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_md(pid, ev, verdict))
    print(signoff_line(ev["signed"]))
    stats = {RULE: {"examined": len(ev["rows"]), "judged": sum(1 for r in ev["rows"] if r[3]), "not_judged": len(ev["blockers"]) + len(ev["notes"]),
                    "errors": len(ev["blockers"]), "waived": 0}}
    out_path = os.environ.get("PCB_FINDINGS_FILE")
    if out_path:
        _engine.write_findings(out_path, findings, stats)
    print("release gate %s: %s mode, %d blocker(s), %d non-blocking -> projects/%s/out/RELEASE_GATE.md" % (
        verdict, ev["mode"] or "undeclared(hand)", len(ev["blockers"]), len(ev["notes"]), pid))
    if ev["blockers"]:
        print("FAILED: %d release blocker(s)" % len(ev["blockers"]))
        return 1
    print("release OK: %s" % pid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
