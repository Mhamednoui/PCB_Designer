"""EL-NETSPEC: the NET_SPEC voltage claim must contain what the model derives (spec P2 sections 2.1 and 3).

Examined: every net with a NET_SPEC `v`.
  ERROR  model status `conflict`: the derived interval is not inside the declared one (either the claim or the design is wrong).
  INFO   model status `claimed-only`: nothing derives the net, so the claim is taken as an assumption ("assumed, not derived").
  OK     model status `derived` (the derivation lies inside the claim).
Nothing is re-derived here; the numbers come from `ctx.model` (boardgen/elec/model.py).
"""
from boardgen.elec.model import fmt
from boardgen.rules.engine import rule


@rule(id="EL-NETSPEC", severity="ERROR", needs=("nets", "electrical"), doc="docs/rules/EL-NETSPEC.md",
      fixture="tests/rules/fixtures/EL-NETSPEC", mutation="M-spec",
      applies=lambda ir: any(n.get("v") for n in ir["nets"].values()), expect_items=True)
def check(ctx):
    for name, n in sorted(ctx.model.nets.items()):
        if n.claim is None:
            continue
        ctx.examined()
        where = {"net": name}
        if n.status == "conflict":
            derived = n.interval
            yield ctx.finding("ERROR", "net %s declared %s but derived %s (%s)" % (name, fmt(n.claim), fmt(derived), n.path[-1] if n.path else n.reason),
                              where=where, target=name,
                              measured={"value": derived[1] if derived[1] > n.claim[1] + 1e-9 else derived[0], "unit": "V",
                                        "corner": "max" if derived[1] > n.claim[1] + 1e-9 else "min"},
                              limit={"value": n.claim[1] if derived[1] > n.claim[1] + 1e-9 else n.claim[0], "unit": "V",
                                     "source": "NET_SPEC v of net %s" % name},
                              fix="If the derived range is the truth, widen NET_SPEC %s to contain %s; if the design is wrong, "
                                  "fix the source (regulator, divider, series element)." % (name, fmt(derived)))
        elif n.status == "claimed-only":
            yield ctx.finding("INFO", "net %s %s assumed, not derived (%s)" % (name, fmt(n.claim), n.reason or "no derivation applies"),
                              where=where, target=name)
