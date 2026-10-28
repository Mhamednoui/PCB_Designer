"""A dummy rule used ONLY to test the engine (it is not a real rule and is never loaded by the pipeline).
It owns a private Registry rooted at tests/rules/demo, so its doc, fixture and mutation live in the tests tree."""
import os

from boardgen.rules.engine import Registry

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = Registry(root=HERE, mutation_ids={"M-demo-negative"})


@DEMO.rule(id="DEMO-NEGATIVE", severity="ERROR", needs=("nets",), doc="DEMO-NEGATIVE.md",
           fixture="fixtures/DEMO-NEGATIVE", mutation="M-demo-negative", expect_items=True)
def check(ctx):
    for net, n in sorted(ctx.ir["nets"].items()):
        ctx.examined()
        if n["v"] is None:
            yield ctx.not_judged("net %s has no declared voltage" % net, where={"net": net})
        elif n["v"][0] < -0.3:
            yield ctx.finding("ERROR", "net minimum %g V is below -0.3 V" % n["v"][0], where={"net": net},
                              measured={"value": n["v"][0], "unit": "V", "corner": "min"},
                              limit={"value": -0.3, "unit": "V", "source": "demo: logic floor -0.3 V"},
                              fix="Move the net's minimum above -0.3 V.")
