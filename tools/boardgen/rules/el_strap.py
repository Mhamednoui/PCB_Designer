"""EL-STRAP: boot-time state of an MCU's strapping pins and its EN reset RC (spec P2 section 3, task P2-T8).

Data-driven: the rule knows no MCU. Every `blocks/<id>.strap.json` profile lists the strapping pins (name as in the part
record, internal default pull, allowed boot states, capacitor limit, download-mode requirement) and the reset pin's RC
window, each with its source citation. A part is covered when its registry record id is in the profile's
`applies_to.registry`. To support another MCU (RP2040, ATmega ...) add a profile file; no code change.

Per strap pin the rule derives the state at reset from the model: external pull resistors (to a rail of known voltage or
to ground; weaker than policy `ext_pull_max_ohm` = not decisive), else the internal default; capacitors on the net; a
switch to ground (BOOT button); anything else attached (connector, IC, ...). Findings:
  ERROR       state conflicts with the required boot state; a capacitor above the pin's limit; a pull that breaks download
              mode; EN without a pull-up or without a capacitor, or R / C outside the profile's window.
  WARN        GPIO0-style pin with no way to be pulled low (download mode unreachable).
  NOT_JUDGED  the level cannot be derived (net shared with another device, unknown rail, divider, weak pull).
Not applicable (no covered MCU on the design): the rule is skipped, examined 0, not an error.
"""
import glob
import json
import os
import re

from boardgen.rules.engine import rule

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_CACHE = {}


def profiles():
    """All blocks/*.strap.json (cached)."""
    d = os.path.join(ROOT, "blocks")
    if d not in _CACHE:
        out = []
        for p in sorted(glob.glob(os.path.join(d, "*.strap.json"))):
            with open(p, encoding="utf-8") as f:
                prof = json.load(f)
            prof["_file"] = os.path.basename(p)
            out.append(prof)
        _CACHE[d] = out
    return _CACHE[d]


def covered(ir):
    """[(ref, part, profile)] for every part of the IR whose registry record a profile names."""
    res = []
    for ref, p in sorted((ir.get("parts") or {}).items()):
        for prof in profiles():
            if p.get("registry") in prof["applies_to"]["registry"]:
                res.append((ref, p, prof))
    return res


def parse_capacitance(value):
    s = str(value).strip().replace("µ", "u").replace("μ", "u")
    m = re.match(r"^(\d+)([pnu])(\d+)$", s, re.I)                                 # 4n7
    if m:
        return float("%s.%s" % (m.group(1), m.group(3))) * {"p": 1e-12, "n": 1e-9, "u": 1e-6}[m.group(2).lower()]
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([pnum]?)F?$", s, re.I)
    if not m:
        return None
    return float(m.group(1)) * {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}[m.group(2).lower()]


def _fmt_r(x):
    return "%g k" % (x / 1e3) if x >= 1000 else "%g ohm" % x


def _fmt_c(x):
    for div, unit in ((1e-6, "uF"), (1e-9, "nF"), (1e-12, "pF")):
        if x >= div * 0.999:
            return "%g %s" % (x / div, unit)
    return "%g F" % x


def _cite(s):
    return (s or "").split(":")[0].split(";")[0]


class Net:
    """What hangs on one MCU pin's net (everything except the pin itself)."""

    def __init__(self, ctx, ref, pad, net):
        from boardgen.elec.model import element_type, parse_resistance
        self.net, self.pulls, self.caps, self.switches, self.others, self.unresolved = net, [], [], [], [], []
        parts, nets = ctx.ir["parts"], ctx.ir["nets"]
        for r, p in sorted(parts.items()):
            for pd, pin in sorted(p["pins"].items()):
                if pin["net"] != net or (r == ref and pd == pad):
                    continue
                et = element_type(p)
                is_sw = p.get("lib_id", "").startswith("Switch:")
                two = [q["net"] for q in p["pins"].values()]
                far = None
                if len(two) == 2 and two[0] != two[1]:
                    far = two[1] if two[0] == net else two[0]
                if (et in ("R", "C") or is_sw) and far is None:
                    self.others.append("%s.%s" % (r, pd))
                elif et == "R":
                    ohm = parse_resistance(p.get("value"))
                    fn = ctx.model.nets.get(far)
                    iv = fn.interval if fn else None
                    if ohm is None or iv is None:
                        self.unresolved.append("%s (%s to net %s, voltage not known)" % (r, p.get("value"), far))
                    elif iv[0] >= 1.0:
                        self.pulls.append((r, "high", ohm, far))
                    elif iv[1] <= 0.3:
                        self.pulls.append((r, "low", ohm, far))
                    else:
                        self.unresolved.append("%s to net %s (%.3g..%.3g V)" % (r, far, iv[0], iv[1]))
                elif et == "C":
                    c = parse_capacitance(p.get("value"))
                    if c is None:
                        self.unresolved.append("%s (value %r not a capacitance)" % (r, p.get("value")))
                    else:
                        self.caps.append((r, c, far))
                elif is_sw:
                    if nets.get(far, {}).get("class") == "ground":
                        self.switches.append(r)
                    else:
                        self.others.append("%s.%s" % (r, pd))
                else:
                    self.others.append("%s.%s" % (r, pd))

    def describe(self):
        bits = ["%s pull-%s %s to %s" % (r, "up" if st == "high" else "down", _fmt_r(o), far) for r, st, o, far in self.pulls]
        bits += ["capacitor %s %s to %s" % (r, _fmt_c(c), far) for r, c, far in self.caps]
        bits += ["button %s to GND" % r for r in self.switches]
        return " + ".join(bits) or "nothing attached"


def _pin_findings(ctx, ref, part, spec, pol, by_name, prof):
    ctx.examined()
    ent = by_name.get(spec["pin"])
    if not ent:
        yield ctx.not_judged("not judged: %s has no pin named %s (profile %s)" % (ref, spec["pin"], prof["_file"]),
                             where={"ref": ref}, target=ref)
        return
    pad, pin = ent[0]
    term, net = "%s.%s" % (ref, pad), pin.get("net")
    label = "%s %s (%s)" % (term, spec["pin"], spec["function"])
    internal = spec["internal_pull"]
    n = None
    if net:
        n = Net(ctx, ref, pad, net)
        if n.others:
            yield ctx.not_judged("not judged: %s net %s also goes to %s; its level at reset depends on that device"
                                 % (label, net, ", ".join(n.others[:3])), where={"net": net, "ref": ref}, target=term)
            return
        if n.unresolved:
            yield ctx.not_judged("not judged: %s net %s: %s" % (label, net, "; ".join(n.unresolved[:2])),
                                 where={"net": net, "ref": ref}, target=term)
            return
    pulls = n.pulls if n else []
    states = {st for _r, st, _o, _f in pulls}
    limit = pol.get("ext_pull_max_ohm", 1e5)
    if len(states) > 1:
        yield ctx.not_judged("not judged: %s net %s has pulls in both directions (%s)" % (label, net, n.describe()),
                             where={"net": net, "ref": ref}, target=term)
        return
    if pulls and any(p[2] > limit for p in pulls):
        yield ctx.not_judged("not judged: %s net %s: pull above the %s decisive-pull policy limit (%s)"
                             % (label, net, _fmt_r(limit), n.describe()), where={"net": net, "ref": ref}, target=term)
        return
    if states:
        state, found = next(iter(states)), n.describe()
    elif internal != "none":
        state = "high" if internal == "up" else "low"
        found = "no external pull, internal weak pull-%s" % internal
    else:
        state, found = "floating", "no external pull, floating"
    if n and n.caps and not pulls:
        found += " + " + n.describe()
    need = spec["normal"]
    # 1. required boot level
    if "any" not in need:
        if state == "floating":
            yield ctx.not_judged("not judged: %s floats at reset but requires %s" % (label, "/".join(need)),
                                 where={"ref": ref}, target=term)
            return
        if state not in need:
            want_pull = "up" if need == ["high"] else "down"
            fix = ("Remove the external pull-%s from %s; the internal default already gives %s." % (
                "up" if state == "high" else "down", spec["pin"], need[0].upper())
                   if internal == want_pull else "Add a pull-%s resistor (10 k) on %s." % (want_pull, spec["pin"]))
            yield ctx.finding("ERROR", "%s: boot level must be %s [%s] but found %s -> %s" % (
                spec["pin"], need[0].upper(), _cite(spec["normal_src"]), found, state.upper()),
                where={"ref": ref, "net": net or ""}, target=term, fix=fix)
            return
    # 2. capacitor
    cmax = spec.get("cap_max_f")
    if n and cmax is not None and sum(c for _r, c, _f in n.caps) > cmax:
        tot = sum(c for _r, c, _f in n.caps)
        yield ctx.finding("ERROR", "%s: expected pull-up without a high-value capacitor [%s], found %s (> %s)" % (
            spec["pin"], _cite(spec["cap_src"]), n.describe(), _fmt_c(cmax)),
            where={"ref": ref, "net": net}, target=n.caps[0][0], measured={"value": tot, "unit": "F", "corner": "typ"},
            limit={"value": cmax, "unit": "F", "source": spec["cap_src"]},
            fix="Remove the capacitor on %s (it delays the boot level and may force download mode); debounce the "
                "BOOT button in firmware instead." % spec["pin"])
        return
    # 3. download mode
    dl = spec.get("download")
    if dl and dl.get("method") == "button_to_gnd":
        if not (n and n.switches):
            yield ctx.finding("WARN", "%s: no button to GND, download mode cannot be entered by hand [%s]"
                              % (spec["pin"], _cite(dl["src"])), where={"ref": ref, "net": net or ""}, target=term,
                              fix="Add a BOOT push-button from %s to GND." % spec["pin"])
    elif dl and dl.get("state") == "low" and state == "high":
        yield ctx.finding("ERROR", "%s: must be LOW for download mode [%s], found %s -> HIGH" % (
            spec["pin"], _cite(dl["src"]), found), where={"ref": ref, "net": net}, target=term,
            fix="Remove the pull-up on %s." % spec["pin"])


def _reset_findings(ctx, ref, part, rs, by_name):
    ctx.examined()
    ent = by_name.get(rs["pin"])
    if not ent:
        yield ctx.not_judged("not judged: %s has no pin named %s" % (ref, rs["pin"]), where={"ref": ref}, target=ref)
        return
    pad, pin = ent[0]
    term, net = "%s.%s" % (ref, pad), pin.get("net")
    rec = rs["recommended"]
    fix = "Put %s from %s to 3V3 and %s from %s to GND." % (_fmt_r(rec["r_ohm"]), rs["pin"], _fmt_c(rec["c_f"]), rs["pin"])
    if not net:
        yield ctx.finding("ERROR", "%s %s is unconnected: the reset pin must not float" % (term, rs["pin"]),
                          where={"ref": ref}, target=term, fix=fix)
        return
    n = Net(ctx, ref, pad, net)
    if n.others or n.unresolved:
        yield ctx.not_judged("not judged: %s net %s: %s" % (term, net, "also goes to " + ", ".join(n.others[:3])
                                                            if n.others else "; ".join(n.unresolved[:2])),
                             where={"net": net, "ref": ref}, target=term)
        return
    ups = [p for p in n.pulls if p[1] == "high"]
    rlo, rhi = rs["pullup_r_ohm"]
    clo, chi = rs["c_f"]
    problems = []
    if not ups:
        problems.append("no pull-up to a rail (EN must not float)")
    elif not rlo <= ups[0][2] <= rhi:
        problems.append("pull-up %s %s outside %s..%s" % (ups[0][0], _fmt_r(ups[0][2]), _fmt_r(rlo), _fmt_r(rhi)))
    ctot = sum(c for _r, c, _f in n.caps)
    if not n.caps:
        problems.append("no capacitor to GND (no RC delay)")
    elif not clo <= ctot <= chi:
        problems.append("capacitance %s outside %s..%s" % (_fmt_c(ctot), _fmt_c(clo), _fmt_c(chi)))
    if problems:
        yield ctx.finding("ERROR", "%s: expected RC delay %s + %s [DS sec.9] found %s: %s" % (
            rs["pin"], _fmt_r(rec["r_ohm"]), _fmt_c(rec["c_f"]), n.describe(), "; ".join(problems)),
            where={"ref": ref, "net": net}, target=term, fix=fix)


def _pins_by_name(part):
    """{pin name: [(pad, {"name", "net"})]}. Unconnected pads are not in the IR's `pins`, so the names come from the
    registry record (an NC strap pin is the normal case); a pad with no net has net None."""
    from boardgen import parts as _parts
    try:
        names = {pad: p.get("name") for pad, p in _parts.get(part["registry"])["pins"].items()}
    except Exception:  # noqa: BLE001 - record missing: fall back to the pins the IR has
        names = {}
    for pad, pin in part["pins"].items():
        names.setdefault(pad, pin.get("name"))
    out = {}
    for pad in sorted(names, key=lambda x: (len(x), x)):
        net = part["pins"].get(pad, {}).get("net")
        out.setdefault(names[pad], []).append((pad, {"name": names[pad], "net": net or None}))
    return out


@rule(id="EL-STRAP", severity="ERROR", needs=("parts", "nets", "electrical"), doc="docs/rules/EL-STRAP.md",
      fixture="tests/rules/fixtures/EL-STRAP", mutation="M-strap", applies=lambda ir: bool(covered(ir)))
def check(ctx):
    for ref, part, prof in covered(ctx.ir):
        by_name = _pins_by_name(part)
        pol = prof.get("policy", {})
        for spec in prof["pins"]:
            yield from _pin_findings(ctx, ref, part, spec, pol, by_name, prof)
        if prof.get("reset"):
            yield from _reset_findings(ctx, ref, part, prof["reset"], by_name)
