"""LINT-SHORT: adapter for lint's `short` rule (a part whose connected pins are all on one net)."""
from boardgen.rules.engine import rule


@rule(id="LINT-SHORT", severity="ERROR", needs=("parts",), doc="docs/rules/LINT-SHORT.md",
      fixture="tests/rules/fixtures/LINT-SHORT", mutation="M-merge", legacy_id="short")
def check(ctx):
    for ref, p in sorted(ctx.ir["parts"].items()):
        ctx.examined()
        nets = {pin["net"] for pin in p["pins"].values()}
        if len(p["pins"]) >= 2 and len(nets) == 1:
            net = next(iter(nets))
            yield ctx.finding("ERROR", "all %d connected pins are on net %s (part is shorted)" % (len(p["pins"]), net),
                              where={"ref": ref, "net": net}, target=ref, refs=[ref], nets=[net],
                              fix="Reconnect at least one pin of %s to a different net." % ref)
