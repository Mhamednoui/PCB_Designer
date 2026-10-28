# EL-NETSPEC

**What.** `NET_SPEC` voltage claims are verified against the model: if the derived interval is not inside the declared
one the status is `conflict` = ERROR. A claim that nothing derives is INFO "assumed, not derived"; a derived claim is OK.

**Why.** NET_SPEC feeds the other electrical rules as an assumption. A wrong claim hides real over-voltage or makes a
rule judge against a rail that does not exist.

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`. Severity ERROR; waivable with
`"check": "electrical"` and a `why`. 0 claims examined on a design that has NET_SPEC voltages is an ERROR.

**Inputs / basis.** `ctx.model` net `claim`, `status`, `interval`, `path` (`needs=("nets","electrical")`); nothing is
re-derived in the rule.

**NOT_JUDGED.** None emitted: a net without a claim is not a NET_SPEC item, and a claim without derivation is INFO (the
assumption is visible, not hidden). Which nets the model could not derive is in `python tools/boardgen/elec/model.py <id>`.

**Example fix.** `net +5V declared 5 V but derived 4.85..5.15 V` -> if the derived range is the truth, widen NET_SPEC to
`(4.75, 5.25)` (the claim was a point value); if the design is wrong, fix the source (regulator, divider, series element).

**Known limits.** Only voltage `v` claims; `i_max` claims are checked by EL-BUDGET. The quality of the verdict is the
quality of the model (generic +-5 % resistors, zero-drop 0R/fuses).
