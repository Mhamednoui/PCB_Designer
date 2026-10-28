"""EL-DROPOUT: an LDO's lowest input voltage against its output plus the dropout it needs (spec P2 section 3, task P2-T6).

headroom = Vin_min - (series fuse/PTC drop at the peak current) - (Vout_max + dropout)
  Vin_min      model interval of the LDO input net (worst case over the declared source range)
  fuse drop    sum over series fuses of record fuse.r_max_ohm x the peak current they carry (budget)
  Vout_max     record regulator.vout.max
  dropout      record regulator.dropout row for the load: the smallest tabulated current >= the peak load (dropout only rises
               with current, so a single high-current row is an upper bound); its `max` else `typ`
Findings: ERROR headroom < 0 (also when a fuse resistance is unknown: that can only make it worse); WARN headroom < 0.1 V;
NOT_JUDGED the input voltage, vout.max, a dropout row or a fuse resistance is missing (the field is named).
Only topology "ldo" is judged; a switcher_module has no dropout, its Vin window is checked by the model.
"""
from boardgen.elec import devices as dev
from boardgen.rules.engine import rule

WARN_HEADROOM_V = 0.1


@rule(id="EL-DROPOUT", severity="ERROR", needs=("parts", "nets", "electrical", "external"), doc="docs/rules/EL-DROPOUT.md",
      fixture="tests/rules/fixtures/EL-DROPOUT", mutation="M-ldo")
def check(ctx):
    b = ctx.budget
    for e in sorted((x for x in b.edges if x.kind == "reg"), key=lambda x: x.ref):
        rg = dev.regulator(e.part) or {}
        if rg.get("topology") != "ldo":
            continue
        ctx.examined()
        ref, rec = e.ref, e.part.get("registry") or "no record"
        w = {"ref": ref, "net": e.up}
        d_out = b.demand(e.down)
        i_ma = d_out["peak"]
        vin = b.iv(e.up)
        vout_hi = dev.datum_value(rg.get("vout"), ("max", "typ"))
        drop_v, rows, how = dev.dropout_v(rg, i_ma)
        miss = []
        if vin is None:
            miss.append("input voltage of net %s (the model could not derive it)" % e.up)
        if vout_hi is None:
            miss.append("regulator.vout.max of %s" % rec)
        if drop_v is None:
            miss.append(how.replace("regulator.dropout", "regulator.dropout of %s" % rec))
        if miss:
            yield ctx.not_judged("not judged: %s dropout: missing %s" % (ref, "; ".join(miss)), where=w, target=ref)
            continue
        fdrop, fmissing, fparts = b.upstream_drop(e.up)
        headroom = vin[0] - fdrop - (vout_hi + drop_v)
        drops = "".join(" - %.3g (%s drop)" % (v, r) for r, v in fparts)
        msg = "%s headroom %.4g%s - %.4g (Vout max) = %.3g V; dropout needed %.3g V @ %.0f mA (%s rec%s)" % (
            ref, vin[0], drops, vout_hi, headroom, drop_v, i_ma, rec, "" if "tabulated" in how else "; " + how)
        lim = {"value": vout_hi + drop_v, "unit": "V", "source": "record %s: vout.max %.4g V + dropout %.3g V (%s)" % (rec, vout_hi, drop_v, how)}
        meas = {"value": vin[0] - fdrop, "unit": "V", "corner": "min"}
        if headroom < 0:
            yield ctx.finding("ERROR", msg + (" - fuse resistance unknown for %s, the real headroom is lower still" % ", ".join(fmissing) if fmissing else ""),
                              where=w, measured=meas, limit=lim, target=ref,
                              fix="Use a lower-dropout regulator (an LDL1117-class part needs ~0.35 V typ / 0.6 V max), raise the minimum "
                                  "input voltage, or lower the load current.")
        elif fmissing:
            yield ctx.not_judged("not judged: %s dropout %s but the series resistance of %s is missing (electrical.fuse.r_max_ohm)" % (
                ref, msg, ", ".join(fmissing)), where=w, target=ref)
        elif headroom < WARN_HEADROOM_V:
            yield ctx.finding("WARN", msg + " (< %.1f V)" % WARN_HEADROOM_V, where=w, measured=meas, limit=lim, target=ref,
                              fix="Less than 0.1 V of headroom: any extra cable or connector drop browns out the rail.")
