"""EL-LEVEL: does a driver's logic-high / logic-low reach the receiver's VIH / VIL in the worst case (spec P2 section 3, 8 Q1).

Examined: every net that has an `input`-class receiver AND at least one direct driver. (A level that reaches the pin through
a resistor network is not judged here; the net's voltage is covered by EL-ABSMAX and the `static_logic` requirements.)
Driver side = `net.levels` from the model (push-pull / tristate outputs with a usable VOH/VOL datum). Receiver side = the
pin's `vih.min` / `vil.max` from the record (numbers, or ratio:k*vdd evaluated against the receiver's supply net; when the
receiver is on another rail than the driver the worst corner of that rail is used, on the same rail the same corner).
  ERROR       VOH min < VIH min, or VOL max > VIL max (margin < 0).
  WARN        the margin is < 0.1 V.
  NOT_JUDGED  the driver is bidirectional / external / open-collector or has no usable VOH/VOL, the receiver has no VIH/VIL
              in its record, or a supply voltage is unknown.
"""
import re

from boardgen.rules.engine import rule

MARGIN_WARN_V = 0.1
_RATIO = re.compile(r"^ratio:([0-9.]+)\*vdd([+-][0-9.]+)?$")


def _limit(d, key, supply, corner):
    """Volts of a record datum's `key` (number or ratio string) with the supply corner index `corner`; None if unusable."""
    v = d.get(key) if isinstance(d, dict) else None
    if isinstance(v, str):
        m = _RATIO.match(v)
        if not m or supply is None:
            return None
        return float(m.group(1)) * supply[corner] + float(m.group(2) or 0)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@rule(id="EL-LEVEL", severity="ERROR", needs=("parts", "nets", "electrical"), doc="docs/rules/EL-LEVEL.md",
      fixture="tests/rules/fixtures/EL-LEVEL", mutation="M-level")
def check(ctx):
    model, parts = ctx.model, ctx.ir["parts"]

    def supply_of(term):
        ref, pad = term.split(".", 1)
        io = parts[ref]["pins"][pad].get("io") or {}
        sp = io.get("supply_pin")
        sp_pin = parts[ref]["pins"].get(sp) if sp else None
        return sp_pin["net"] if sp_pin else None

    for name, n in sorted(model.nets.items()):
        recs = sorted((r for r in n.receivers if r["class"] == "input"), key=lambda x: x["term"])
        if not recs or not n.drivers:
            continue
        if n.ir_class in ("ground", "power") or n.supply_sources or any(d["kind"] == "external_supply" for d in n.drivers):
            continue                                  # a rail: an input tied to it is a tie-off, not a logic level
        outs = [d for d in n.drivers if d["kind"] in ("push_pull", "tristate")]
        for r in recs:
            ctx.examined()
            ref, pad = r["term"].split(".", 1)
            where = {"ref": ref, "pin": pad, "net": name}

            def nj(why):
                return ctx.not_judged("not judged: %s on net %s: %s" % (r["term"], name, why), where=where, target=r["term"])
            if not outs or n.levels is None or len(n.drivers) != len(outs):
                kinds = sorted({"%s (%s)" % (d["term"], d["kind"]) for d in n.drivers})
                yield nj("output levels of the driver(s) %s are not modelled%s" % (
                    ", ".join(kinds), "" if n.levels is not None or not outs else " (no usable VOH/VOL or unknown supply: " + (n.reason or "see model") + ")"))
                continue
            io = parts[ref]["pins"][pad].get("io") or {}
            rs_net = supply_of(r["term"])
            rs = model.nets[rs_net].interval if rs_net in model.nets else None
            ds_net = supply_of(outs[0]["term"])
            same = rs_net == ds_net
            vih = _limit(io.get("vih"), "min", rs, 0 if same else 1)
            vil = _limit(io.get("vil"), "max", rs, 0)
            if vih is None and vil is None:
                yield nj("its record states no usable VIH/VIL%s" % (" (supply %s unknown)" % rs_net if rs is None and rs_net else ""))
                continue
            lo, hi = n.levels["low"], n.levels["high"]
            src = "%s record VIH/VIL vs %s VOH/VOL" % (r["term"], outs[0]["term"])
            for label, margin, have, need, corner, fx in (
                    ("high", None if vih is None else hi[0] - vih, hi[0], vih, "min", "VOH min %.3g V < VIH min %.3g V"),
                    ("low", None if vil is None else vil - lo[1], lo[1], vil, "max", "VOL max %.3g V > VIL max %.3g V")):
                if margin is None:
                    yield nj("its record states no usable %s" % ("VIH" if label == "high" else "VIL"))
                elif margin < 0 or margin < MARGIN_WARN_V:
                    yield ctx.finding(
                        "ERROR" if margin < 0 else "WARN",
                        "driver %s %s, %s" % (outs[0]["term"], fx % (have, need),
                                                  "margin %.3g V" % margin if margin >= 0 else "receiver on %s" % rs_net),
                        where=where, target=r["term"], nets=[name],
                        measured={"value": have, "unit": "V", "corner": corner},
                        limit={"value": need, "unit": "V", "source": src},
                        fix="Put a level shifter between %s and %s, or run both on the same rail." % (outs[0]["term"], r["term"]))
