"""EL-ABSMAX: a pin's net voltage interval against the pin's absolute-maximum rating (spec P2 section 3).

Inputs: model net interval (worst case over tolerances) and ir parts[*].pins[*].abs_max {v_min, v_max, i_ma, cited}.
A rating given as "pin:N+off" is the voltage of pin N of the SAME part's net, plus off (e.g. "VCC + 0.5 V"); it is resolved
at that supply net's HIGH corner (a signal and its supply are assumed to track; an independent-rail worst case is not
modelled). Current ratings (i_ma) are not judged in v1: the model carries no per-pin current yet.
"""
import re

from boardgen.rules.engine import rule

REF_RE = re.compile(r"^pin:([A-Za-z0-9_]+)([+-][0-9.]+)?$")
EPS = 1e-9
USABLE = ("derived", "claimed-only", "conflict")


def _iv(model, net):
    n = model.nets.get(net)
    return (n.interval, n) if n is not None and n.status in USABLE and n.interval is not None else (None, n)


def _limit(model, part, spec, corner):
    """-> (value, why) ; value None = unresolvable (why says why). corner 'hi' for v_max, 'lo' for v_min."""
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return float(spec), None
    m = REF_RE.match(str(spec))
    pin = part["pins"].get(m.group(1)) if m else None
    if pin is None:
        return None, "rating %r does not name a pin of this part" % (spec,)
    iv, n = _iv(model, pin["net"])
    if iv is None:
        return None, "rating %s needs net %s, whose voltage is not known (%s)" % (spec, pin["net"], (n.reason if n else "no such net"))
    return iv[1 if corner == "hi" else 0] + float(m.group(2) or 0), None


@rule(id="EL-ABSMAX", severity="ERROR", needs=("parts", "nets", "electrical"), doc="docs/rules/EL-ABSMAX.md",
      fixture="tests/rules/fixtures/EL-ABSMAX", mutation="M-volt")
def check(ctx):
    from boardgen.elec.model import element_type, fmt
    model = ctx.model
    for ref, part in sorted(ctx.ir["parts"].items()):
        et = element_type(part)
        rid = part.get("registry")
        if part.get("kind") == "unregistered" and et in ("IC", "REG", "FET"):
            ctx.examined()
            yield ctx.not_judged("not judged: %s has no part record (no abs_max data)" % ref, where={"ref": ref})
            continue
        missing, unknown = [], []
        for pad, pin in sorted(part["pins"].items()):
            am = pin.get("abs_max")
            net = pin["net"]
            if not am or (am.get("v_max") is None and am.get("v_min") is None):
                nclass = ctx.ir["nets"].get(net, {}).get("class")
                if et in ("IC", "REG", "FET") and pin.get("class") not in ("passive", "nc") and nclass != "ground":
                    missing.append(pad)
                continue
            iv, n = _iv(model, net)
            if iv is None:
                unknown.append((pad, net, n.reason if n else "no such net"))
                continue
            for key, corner, bad, word in (("v_max", "hi", lambda v, l: v > l + EPS, "max"),
                                           ("v_min", "lo", lambda v, l: v < l - EPS, "min")):
                if am.get(key) is None:
                    continue
                lim, why = _limit(model, part, am[key], corner)
                if lim is None:
                    unknown.append((pad, net, why))
                    continue
                ctx.examined()
                v = iv[1] if word == "max" else iv[0]
                if bad(v, lim):
                    cmp_ = ">" if word == "max" else "<"
                    yield ctx.finding(
                        "ERROR", "pin %s: %.4g V %s %s %.4g V limit (abs_max %s, rec %s)" % (
                            pin.get("name"), v, word, cmp_, lim, key, rid or "-"),
                        where={"ref": ref, "pin": pad, "net": net},
                        measured={"value": v, "unit": "V", "corner": word}, target="%s.%s" % (ref, pad),
                        limit={"value": lim, "unit": "V", "source": "abs_max %s, record %s%s" % (
                            key, rid or "-", ", cited" if am.get("cited") else ", NOT cited")},
                        fix="Keep net %s within %s of %s.%s: add a divider / level shifter / regulator, or change the net's "
                            "supply (net voltage: %s)." % (net, "%.4g V" % lim, ref, pad, fmt(iv)))
        if missing:
            ctx.examined()
            yield ctx.not_judged("not judged: %s pin(s) %s have no abs_max (record %s)" % (ref, ", ".join(missing), rid or "-"),
                                 where={"ref": ref}, target=ref)
        if unknown:
            ctx.examined()
            pads = ", ".join("%s(%s)" % (p, nt) for p, nt, _w in unknown)
            yield ctx.not_judged("not judged: %s pin(s) %s: voltage not known (%s)" % (ref, pads, unknown[0][2]),
                                 where={"ref": ref}, target=ref)
