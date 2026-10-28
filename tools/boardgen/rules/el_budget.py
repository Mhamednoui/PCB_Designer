"""EL-BUDGET: the peak current a rail has to carry against every limit on the path to it (spec P2 section 3, task P2-T6).

Demand comes from `boardgen.elec.budget` (record load_ma, resistors, LED branches, EXTERNAL `out` loads, regulators back-
propagated). Limits, per net:
  * the EXTERNAL supply pins that feed it (`i`, amps)               * the regulator that drives it (record regulator.i_max_ma)
  * a series fuse / PTC on the way (record fuse.i_hold_ma)           * the net's own `i_max` (NET_SPEC, the copper design figure)
Findings:
  ERROR       peak demand > limit (also when the total is only a LOWER BOUND because some loads are unknown: it is already over)
  WARN        peak demand > 80 % of a limit (margin < 20 %)
  NOT_JUDGED  a limit's record field is missing, or loads on the net have no derivable current (each missing field is named)
peak = design point (continuous worst case); duty cycles, inrush and temperature are not modelled.
"""
from boardgen.rules.engine import rule

MARGIN = 0.20


def _ma(v):
    return "%.0f mA" % v if v >= 100 else "%.3g mA" % v


def _limits(b, net, ir):
    """-> (limits, missing): limits = [(mA, label, source)], missing = [field names]."""
    lim, missing = [], []
    src = b.sources.get(net)
    if src is not None:
        if src["i_ma"] is None:
            missing.append("EXTERNAL i of %s" % ", ".join(src["terms"]))
        elif src["i_ma"] > 0:
            lim.append((src["i_ma"], "supply %s (EXTERNAL i)" % ", ".join(src["terms"]), "EXTERNAL i of %s" % ", ".join(src["terms"])))
    for e in b.edges:
        if e.down != net or e.up is None:
            continue
        rec = e.part.get("registry") or "no record"
        if e.kind == "reg":
            from boardgen.elec import devices as dev
            v = dev.datum_value((dev.regulator(e.part) or {}).get("i_max_ma"), ("max", "typ"))
            if v is None:
                missing.append("regulator.i_max_ma of %s (%s)" % (e.ref, rec))
            else:
                lim.append((v, "regulator %s output rating" % e.ref, "record %s regulator.i_max_ma" % rec))
        elif e.kind == "fuse":
            from boardgen.elec import devices as dev
            fd = dev.fuse(e.part) if e.part.get("electrical_status") == "ok" else None
            if fd is None or fd["i_hold_ma"] is None:
                missing.append("electrical.fuse.i_hold_ma of %s (%s)" % (e.ref, rec))
            else:
                lim.append((fd["i_hold_ma"], "%s hold current" % e.ref, "record %s fuse.i_hold_ma" % rec))
    imax = (ir["nets"].get(net) or {}).get("i_max")
    if isinstance(imax, (int, float)) and not isinstance(imax, bool) and imax > 0:
        lim.append((imax * 1000.0, "net %s i_max" % net, "NET_SPEC %s i_max" % net))
    return lim, missing


@rule(id="EL-BUDGET", severity="ERROR", needs=("parts", "nets", "electrical", "external"), doc="docs/rules/EL-BUDGET.md",
      fixture="tests/rules/fixtures/EL-BUDGET", mutation="M-load")
def check(ctx):
    b = ctx.budget
    for net in sorted(ctx.ir["nets"]):
        n = ctx.ir["nets"][net]
        if n.get("class") != "power":
            continue
        d = b.demand(net)
        if d["peak"] <= 0 and not d["unknown"]:
            continue
        limits, missing = _limits(b, net, ctx.ir)
        peak = d["peak"]
        lower = " (at least: %d load(s) have no derivable current)" % len(d["unknown"]) if d["unknown"] else ""
        biggest = sorted(d["loads"], key=lambda x: -x["peak"])[:2]
        top = "; biggest: " + ", ".join("%s %s" % (x["term"], _ma(x["peak"])) for x in biggest) if biggest else ""
        bad = False
        for ma, label, source in limits:
            ctx.examined()
            if peak > ma + 1e-9:
                bad = True
                yield ctx.finding(
                    "ERROR", "%s peak %s%s > %s %s%s" % (net, _ma(peak), lower, label, _ma(ma), top),
                    where={"net": net}, measured={"value": peak, "unit": "mA", "corner": "max"}, target=net,
                    limit={"value": ma, "unit": "mA", "source": source},
                    fix="Cut the load on %s, raise the limit (a stronger regulator / source / fuse, wider copper) or declare the "
                        "real current. Peak = every load at its design-point current at once." % net)
            elif not d["unknown"] and peak > (1.0 - MARGIN) * ma:
                yield ctx.finding(
                    "WARN", "%s peak %s is %.0f %% of %s %s (margin < %.0f %%)" % (net, _ma(peak), 100.0 * peak / ma, label, _ma(ma), 100 * MARGIN),
                    where={"net": net}, measured={"value": peak, "unit": "mA", "corner": "max"}, target=net,
                    limit={"value": ma, "unit": "mA", "source": source}, fix="Keep 20 % margin or document the duty cycle.")
        for field in missing:
            ctx.examined()
            yield ctx.not_judged("not judged: %s peak %s vs a limit whose data is missing: %s" % (net, _ma(peak), field),
                                 where={"net": net}, target=net)
        if d["unknown"]:
            ctx.examined()
            fields = sorted({u["field"] for u in d["unknown"]})
            yield ctx.not_judged("not judged: %s peak %s is a lower bound%s; missing: %s" % (
                net, _ma(peak), " (already over a limit)" if bad else "", "; ".join(fields[:6]) + (" ..." if len(fields) > 6 else "")),
                where={"net": net}, target=net)
