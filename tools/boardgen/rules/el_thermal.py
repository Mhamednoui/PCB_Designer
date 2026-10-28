"""EL-THERMAL: junction temperature of power-dissipating parts at the peak current (spec P2 section 3, task P2-T6).

Tj = Ta + P x theta_JA against the record's tj_max. Ta = 40 C by default (spec section 8; `meta.ambient_c` overrides when the IR
carries it). The record theta_JA is the datasheet TEST-BOARD value and is COPPER-DEPENDENT: when a record lists several, the
largest (most pessimistic) is used; the achieved theta_JA of the real layout is not modelled and every finding says so.
  LDO        P = Vin_max x (Iout + Iq) - Vout_typ x Iout; Vin_max = model interval high corner minus the series fuse drop
  MOSFET     P = Id^2 x Rds(on); Id = sum of EXTERNAL `out` currents on the drain net; Rds(on) from the record row with the
             largest tested Vgs <= the gate net's high corner (25 C maximum: the rise with temperature is not modelled)
  resistor   P = I^2 R for the resistors the budget gives a current to; ERROR above the record p_max_mw, WARN above 50 % of it
Findings: ERROR Tj > tj_max (P > p_max for a resistor); WARN Tj within 10 C of tj_max (resistor > 50 % derating);
NOT_JUDGED any needed field missing (named). Not modelled: duty cycle, thermal time constants, neighbours, airflow.
"""
from boardgen.elec import devices as dev
from boardgen.elec.budget import ldo_power_w
from boardgen.rules.engine import rule

AMBIENT_C = 40.0
WARN_C = 10.0
DERATE = 0.5
THETA_NOTE = "theta_JA from datasheet test board: copper-dependent (the real layout's copper area changes it; not modelled)"


def _ambient(ctx):
    meta = ctx.ir.get("meta") or {}
    v = meta.get("ambient_c") if isinstance(meta, dict) else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else AMBIENT_C


def _tj_verdict(ctx, ref, part, p_w, ta, what, where):
    """Shared Tj judgement -> findings (generator). `what` describes P."""
    rec = part.get("registry") or "no record"
    th = dev.theta_ja(part) if part.get("electrical_status") == "ok" else None
    tjm = dev.tj_max(part) if part.get("electrical_status") == "ok" else None
    miss = []
    if th is None:
        miss.append("electrical.theta_ja of %s" % rec)
    if tjm is None:
        miss.append("electrical.tj_max of %s" % rec)
    if miss:
        yield ctx.not_judged("not judged: %s dissipates %.3g W (%s) but the record lacks %s" % (ref, p_w, what, "; ".join(miss)),
                             where=where, target=ref)
        return
    theta, row = th
    tj = ta + p_w * theta
    msg = "%s Tj %.0f C %s %.0f C (%s; Ta %.0f C, theta_JA %.0f C/W; %s)" % (
        ref, tj, ">" if tj > tjm else "<=", tjm, what, ta, theta, THETA_NOTE)
    meas = {"value": tj, "unit": "C", "corner": "max"}
    lim = {"value": tjm, "unit": "C", "source": "record %s tj_max; theta_JA %s (%s)" % (rec, theta, row.get("cond", ""))}
    if tj > tjm:
        yield ctx.finding("ERROR", msg, where=where, measured=meas, limit=lim, target=ref,
                          fix="Cut the dissipation (lower the dropout across the regulator, e.g. a buck stage), add copper under the "
                              "tab/heatsink to lower theta_JA, or lower the peak current. The datasheet theta_JA is for ST's test board.")
    elif tj > tjm - WARN_C:
        yield ctx.finding("WARN", msg + " - within %.0f C of the limit" % WARN_C, where=where, measured=meas, limit=lim, target=ref,
                          fix="Less than %.0f C of margin; confirm the real copper area / airflow." % WARN_C)


@rule(id="EL-THERMAL", severity="ERROR", needs=("parts", "nets", "electrical", "external"), doc="docs/rules/EL-THERMAL.md",
      fixture="tests/rules/fixtures/EL-THERMAL", mutation="M-heat")
def check(ctx):
    b = ctx.budget
    ta = _ambient(ctx)
    # -- linear regulators
    for e in sorted((x for x in b.edges if x.kind == "reg"), key=lambda x: x.ref):
        rg = dev.regulator(e.part) or {}
        if rg.get("topology") == "switcher_module":
            ctx.examined()
            d_out = b.demand(e.down)
            vo = dev.datum_value(rg.get("vout"), ("typ", "max", "min"))
            eff = dev.datum_value(rg.get("efficiency_pct"), ("min", "typ"))
            if vo is None or eff is None:
                yield ctx.not_judged("not judged: %s (switcher module) loss: missing regulator.vout / regulator.efficiency_pct of %s" % (
                    e.ref, e.part.get("registry") or "no record"), where={"ref": e.ref}, target=e.ref)
                continue
            p_w = vo * d_out["peak"] / 1000.0 * (100.0 / eff - 1.0)
            what = "P %s%.3g W = %.3g V x %.0f mA x (1/%.0f %% - 1)" % ("at least " if d_out["unknown"] else "", p_w, vo, d_out["peak"], eff)
            yield from _tj_verdict(ctx, e.ref, e.part, p_w, ta, what, {"ref": e.ref, "net": e.up})
            continue
        if rg.get("topology") != "ldo":
            continue
        ctx.examined()
        w = {"ref": e.ref, "net": e.up}
        i_ma = b.demand(e.down)["peak"]
        vin = b.iv(e.up)
        vout = dev.datum_value(rg.get("vout"), ("typ", "max", "min"))
        miss = []
        if vin is None:
            miss.append("input voltage of net %s" % e.up)
        if vout is None:
            miss.append("regulator.vout of %s" % (e.part.get("registry") or "no record"))
        if miss:
            yield ctx.not_judged("not judged: %s dissipation: missing %s" % (e.ref, "; ".join(miss)), where=w, target=e.ref)
            continue
        fdrop, _fmissing, _p = b.upstream_drop(e.up)
        iq = dev.datum_value(rg.get("iq_ma"), ("max", "typ")) or 0.0
        p_w = ldo_power_w(vin[1] - fdrop, vout, i_ma, iq)
        what = "P %.3g W = (%.4g V in%s - %.4g V out) x %.0f mA at the high USB/input corner" % (
            p_w, vin[1] - fdrop, " after fuse drop" if fdrop > 0 else "", vout, i_ma)
        yield from _tj_verdict(ctx, e.ref, e.part, p_w, ta, what, w)
    # -- MOSFETs
    for ref, p in sorted(ctx.ir["parts"].items()):
        if b.etype[ref] != "FET":
            continue
        ctx.examined()
        by = {pin.get("name"): pin["net"] for pin in p["pins"].values()}
        w = {"ref": ref}
        d_net, g_net = by.get("D"), by.get("G")
        i_a, no_i = b.external_current_a(d_net) if d_net else (0.0, [])
        gate = b.iv(g_net) if g_net else None
        miss = []
        if i_a <= 0:
            miss.append("EXTERNAL i on the drain net %s (the load it switches)%s" % (d_net, " - undeclared: " + ", ".join(no_i) if no_i else ""))
        if gate is None:
            miss.append("gate drive voltage (net %s has no derived interval)" % g_net)
        rds = dev.fet_rds_on(p, gate[1]) if (gate is not None and p.get("electrical_status") == "ok") else None
        if gate is not None and rds is None:
            miss.append("electrical.rds_on at Vgs <= %.3g V of %s" % (gate[1], p.get("registry") or "no record"))
        if miss:
            yield ctx.not_judged("not judged: %s conduction loss: missing %s" % (ref, "; ".join(miss)), where=w, target=ref)
            continue
        ohm, _row = rds
        p_w = i_a * i_a * ohm
        what = "P %.3g W = %.3g A^2 x Rds(on) %.3g ohm at Vgs %.3g V (25 C maximum, rise with temperature not modelled)" % (
            p_w, i_a, ohm, gate[1])
        yield from _tj_verdict(ctx, ref, p, p_w, ta, what, w)
    # -- resistors carrying a derived current
    for ref, ri in sorted(b.res_i.items()):
        p = ctx.ir["parts"][ref]
        ohm = b._res[ref]["r"]
        ctx.examined()
        pmax = dev.p_max_mw(p) if p.get("electrical_status") == "ok" else None
        p_mw = (ri["peak"] / 1000.0) ** 2 * ohm * 1000.0
        w = {"ref": ref}
        if pmax is None:
            yield ctx.not_judged("not judged: %s dissipates %.3g mW (%s) but the record lacks electrical.p_max_mw" % (ref, p_mw, ri["desc"]),
                                 where=w, target=ref)
            continue
        meas = {"value": p_mw, "unit": "mW", "corner": "max"}
        lim = {"value": pmax, "unit": "mW", "source": "record %s p_max_mw (rated at its stated ambient)" % (p.get("registry") or "-")}
        msg = "%s dissipates %.3g mW (%s, I %.3g mA) vs %.0f mW rating" % (ref, p_mw, ri["desc"], ri["peak"], pmax)
        if p_mw > pmax:
            yield ctx.finding("ERROR", msg + " - over the rating", where=w, measured=meas, limit=lim, target=ref,
                              fix="Use a higher-value resistor or a power resistor; keep P under 50 % of the rating.")
        elif p_mw > DERATE * pmax:
            yield ctx.finding("WARN", msg + " - over %.0f %% derating" % (100 * DERATE), where=w, measured=meas, limit=lim, target=ref,
                              fix="Keep a resistor at or below 50 % of its power rating.")
