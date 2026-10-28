"""EL-FLOAT: an input pin on a net nothing drives or pulls (spec P2 section 3).

Examined: every net that has an `input`-class pin (CMOS/TTL inputs; analog pins separately). The net counts as DRIVEN when it,
or a net reachable from it through 2-pin resistors / inductors / fuses / diodes / LEDs (a DC path), is a ground or power
net, has a supply output, any driver (push-pull, tristate, open-collector, bidirectional, EXTERNAL in/bidir/supply) or a
model-derived source. Findings:
  ERROR       an `input` pin whose net is not driven in that sense (floating CMOS input).
  INFO        an `analog` pin that is not driven (bypass-cap-only control pins like the 555 CONTROL pin are fine).
  NOT_JUDGED  the DC path reaches a connector pin that is not declared in EXTERNAL, or a pin of a part with no record class
              (the other side may drive it).
Unconnected pads cannot occur here: registry_part() refuses a pad that is neither connected nor declared NC, and an
NC-declared pad is absent from the IR (so it is OK by construction).
"""
from boardgen.rules.engine import rule

_DC_PATH = ("R", "L", "FUSE", "DIODE", "LED")


@rule(id="EL-FLOAT", severity="ERROR", needs=("parts", "nets", "external", "electrical"), doc="docs/rules/EL-FLOAT.md",
      fixture="tests/rules/fixtures/EL-FLOAT", mutation="M-float")
def check(ctx):
    from boardgen.elec.model import element_type
    model, parts = ctx.model, ctx.ir["parts"]
    ext = ctx.ir["external"]
    ext_pins, ext_none = ext.get("pins", {}), set(ext.get("none", []))
    adj = {}                                              # net -> [(ref, far net)]
    for ref, p in parts.items():
        if element_type(p) in _DC_PATH:
            ends = [pin["net"] for pin in p["pins"].values()]
            if len(ends) == 2 and ends[0] != ends[1]:
                adj.setdefault(ends[0], []).append((ref, ends[1]))
                adj.setdefault(ends[1], []).append((ref, ends[0]))

    def verdict(net):
        """('driven', why) | ('open', None) | ('unknown', why) over the DC component of `net`."""
        seen, todo, unknown = {net}, [net], None
        while todo:
            cur = todo.pop()
            n = model.nets[cur]
            if n.ir_class in ("ground", "power") or n.supply_sources or n.drivers or n.source in ("ground", "external", "regulator"):
                return "driven", cur
            for p in parts.values():                      # a connector / unclassified pin on the net: the outside may drive it
                for pad, pin in p["pins"].items():
                    if pin["net"] != cur:
                        continue
                    et = element_type(p)
                    if et == "CONN" and p["ref"] not in ext_none and "%s.%s" % (p["ref"], pad) not in ext_pins:
                        unknown = unknown or "connector pin %s.%s is not declared in EXTERNAL" % (p["ref"], pad)
                    elif et in ("IC", "REG", "FET") and pin.get("class") is None:
                        unknown = unknown or "%s.%s has no class in its record (part %s)" % (
                            p["ref"], pad, p.get("registry") or "not in the registry")
            for _ref, far in adj.get(cur, []):
                if far not in seen:
                    seen.add(far)
                    todo.append(far)
        return ("unknown", unknown) if unknown else ("open", None)

    cache = {}
    for name, n in sorted(model.nets.items()):
        recs = [r for r in n.receivers if r["class"] in ("input", "analog")]
        if not recs:
            continue
        if name not in cache:
            cache[name] = verdict(name)
        v, why = cache[name]
        for r in sorted(recs, key=lambda x: x["term"]):
            ctx.examined()
            ref, pad = r["term"].split(".", 1)
            where = {"ref": ref, "pin": pad, "net": name}
            if v == "driven":
                continue
            if v == "unknown":
                yield ctx.not_judged("not judged: %s on net %s: %s" % (r["term"], name, why), where=where, target=r["term"])
            elif r["class"] == "analog":
                yield ctx.finding("INFO", "analog pin %s on net %s has no DC source (fine for a bypass-cap-only control pin)"
                                  % (r["name"], name), where=where, target=r["term"])
            else:
                yield ctx.finding("ERROR", "floating input %s: net %s has no driver, pull-up/pull-down or supply"
                                  % (r["name"], name), where=where, target=r["term"],
                                  fix="Tie %s to a rail or ground through a resistor (10 k), or drive it; if the pad is "
                                      "unused, declare it NC in the registry_part() call." % r["term"])
