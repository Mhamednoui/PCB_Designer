"""EL-CONTENTION: two outputs fighting on one net (spec P2 section 3).

ERROR when a net has >= 2 push-pull output pins (non-tristate), or a push-pull output on a ground net or on a net with a
`power_out` pin. NOT_JUDGED when bidirectional pins make it undecidable (a bidirectional pin counts as a driver only when
the record says which direction it has in this design, and records do not yet). Open-collector/open-drain pins are
sink-only and never contend with each other; tristate outputs are skipped (their enable logic is not modelled).
"""
from boardgen.rules.engine import rule


@rule(id="EL-CONTENTION", severity="ERROR", needs=("parts", "nets", "electrical"), doc="docs/rules/EL-CONTENTION.md",
      fixture="tests/rules/fixtures/EL-CONTENTION", mutation="M-contend")
def check(ctx):
    for name, n in sorted(ctx.model.nets.items()):
        pp = [d for d in n.drivers if d["kind"] == "push_pull"]
        bi = [d for d in n.drivers if d["kind"] == "bidirectional"]
        if not pp and not bi:
            continue
        ctx.examined()
        terms = [d["term"] for d in pp]
        if len(pp) >= 2:
            yield ctx.finding("ERROR", "net %s driven by %s" % (name, " and ".join(terms)),
                              where={"net": name}, target=name, refs=[t.split(".")[0] for t in terms],
                              fix="Give each output its own net, or put a gate/series element between them "
                                  "(or make one of them open-drain / tristate).")
            continue
        if pp and (n.ir_class == "ground" or n.supply_sources):
            other = "ground net %s" % name if n.ir_class == "ground" else "supply output %s on net %s" % (n.supply_sources[0]["term"], name)
            yield ctx.finding("ERROR", "output %s is shorted to %s" % (terms[0], other),
                              where={"net": name}, target=name, refs=[terms[0].split(".")[0]],
                              fix="Move %s to a signal net." % terms[0])
            continue
        if bi and (pp or len(bi) >= 2):
            yield ctx.not_judged("not judged: net %s has %s; bidirectional pin direction is not in the records"
                                 % (name, ", ".join(d["term"] for d in pp + bi)), where={"net": name}, target=name)
