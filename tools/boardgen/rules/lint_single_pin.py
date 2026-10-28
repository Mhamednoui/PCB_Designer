"""LINT-SINGLE-PIN: adapter for lint's `single-pin` rule (a net that touches exactly one pin)."""
from boardgen.rules.engine import rule


@rule(id="LINT-SINGLE-PIN", severity="ERROR", needs=("nets",), doc="docs/rules/LINT-SINGLE-PIN.md",
      fixture="tests/rules/fixtures/LINT-SINGLE-PIN", mutation="M-split", legacy_id="single-pin")
def check(ctx):
    for net, n in sorted(ctx.ir["nets"].items()):
        ctx.examined()
        if len(n["pins"]) == 1:
            ref, pin = n["pins"][0].split(".", 1)
            yield ctx.finding("ERROR", "net %s touches only %s.%s" % (net, ref, pin),
                              where={"ref": ref, "pin": pin, "net": net}, target="%s/%s" % (ref, net),
                              refs=[ref], nets=[net],
                              fix="Connect net %s to a second pin, or delete it if it is a typo." % net)
