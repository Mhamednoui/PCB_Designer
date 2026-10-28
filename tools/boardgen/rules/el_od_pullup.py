"""EL-OD-PULLUP: an open-drain / open-collector net needs a pull-up resistor to a rail (spec P2 section 3).

Net selection: any net with an open_collector pin, or an I2C-named net (SDA/SCL, optionally prefixed/suffixed).
A pull-up is a resistor whose far side is a rail (net of class `power`, or one fed by an EXTERNAL supply or a regulator)
with a known interval >= 1 V. Findings:
  ERROR       no resistor to a rail at all ("no pull-up"), or the resistor is too small for the weakest sink:
              R_min (-5 %) < Vrail_max / Iol_max.
  NOT_JUDGED  the rail's voltage is not known, or no sink states its maximum output current (value not checked).
Not modelled in v1: the rise-time upper bound (needs bus capacitance and mode).
"""
import re

from boardgen.rules.engine import rule

I2C_RE = re.compile(r"(^|[_/.])(SDA|SCL)\d*$", re.I)


def _iol_ma(pin):
    v = (pin.get("io") or {}).get("i_out_max_ma")
    if isinstance(v, dict):
        v = v.get("max")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@rule(id="EL-OD-PULLUP", severity="ERROR", needs=("parts", "nets", "electrical"), doc="docs/rules/EL-OD-PULLUP.md",
      fixture="tests/rules/fixtures/EL-OD-PULLUP", mutation="M-pullup")
def check(ctx):
    from boardgen.elec.model import R_TOL, element_type, parse_resistance
    model, parts, nets = ctx.model, ctx.ir["parts"], ctx.ir["nets"]
    for name, n in sorted(model.nets.items()):
        sinks = [d for d in n.drivers if d["kind"] == "sink_only"]
        if not sinks and not I2C_RE.search(name):
            continue
        ctx.examined()
        what = "open-drain driver %s" % sinks[0]["term"] if sinks else "I2C-named bus"
        conns = sorted({"%s.%s" % (r, pad) for r, p in parts.items() if element_type(p) == "CONN"
                        for pad, pin in p["pins"].items() if pin["net"] == name})
        conns = sorted({"%s.%s" % (r, pad) for r, p in parts.items() if element_type(p) == "CONN"
                        for pad, pin in p["pins"].items() if pin["net"] == name})
        pulls, unknown = [], []                      # (ref, rail net, rail interval, ohms (lo, hi))
        for ref, p in sorted(parts.items()):
            if element_type(p) != "R":
                continue
            ends = [pin["net"] for pin in p["pins"].values()]
            if len(ends) != 2 or name not in ends or ends[0] == ends[1]:
                continue
            far = ends[0] if ends[1] == name else ends[1]
            fn = model.nets.get(far)
            if nets.get(far, {}).get("class") != "power" and (fn is None or fn.source not in ("external", "regulator")):
                continue
            r = parse_resistance(p.get("value"))
            if fn is None or fn.interval is None:
                unknown.append((ref, far))
            elif fn.interval[0] >= 1.0:
                pulls.append((ref, far, fn.interval, None if r is None else (r * (1 - R_TOL), r * (1 + R_TOL))))
        if not pulls:
            if unknown:
                yield ctx.not_judged("not judged: net %s pull-up %s goes to rail %s whose voltage is not known"
                                     % (name, unknown[0][0], unknown[0][1]), where={"net": name}, target=name)
            elif conns:
                yield ctx.not_judged("not judged: net %s has no pull-up on the board and leaves it through %s; the pull-up "
                                     "must be on the peripheral (not declared in EXTERNAL)" % (name, ", ".join(conns)),
                                     where={"net": name}, target=name)
            else:
                yield ctx.finding("ERROR", "net %s: %s, no pull-up resistor to a rail" % (name, what),
                                  where={"net": name}, target=name,
                                  fix="Add a pull-up (e.g. 4.7 k for I2C, 10 k for a slow open-drain line) from %s to the "
                                      "supply the receiver uses." % name)
            continue
        iols = [(_iol_ma(ctx.ir["parts"][s["term"].split(".")[0]]["pins"][s["term"].split(".", 1)[1]]), s["term"]) for s in sinks]
        if not sinks or any(i is None for i, _t in iols):
            miss = [t for i, t in iols if i is None] or ["(none: I2C-named net without an open-drain pin)"]
            yield ctx.not_judged("not judged: net %s pull-up value: %s states no maximum low-level output current"
                                 % (name, miss[0]), where={"net": name}, target=name)
            continue
        iol = min(i for i, _t in iols)
        for ref, rail, iv, r in pulls:
            if r is None:
                continue
            need = iv[1] / (iol / 1000.0)
            if r[0] < need:
                yield ctx.finding("ERROR", "net %s: pull-up %s %.0f ohm < %.0f ohm minimum (%.4g V / %.4g mA sink limit)"
                                  % (name, ref, r[0], need, iv[1], iol),
                                  where={"ref": ref, "net": name}, target=ref,
                                  measured={"value": r[0], "unit": "ohm", "corner": "min"},
                                  limit={"value": need, "unit": "ohm", "source": "Vrail_max / Iol_max of %s" % iols[0][1]},
                                  fix="Raise %s to at least %.0f ohm." % (ref, need))
