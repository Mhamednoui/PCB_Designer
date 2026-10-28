# LINT-SHORT (legacy name `short`)

**What.** A part with two or more connected pins whose pins are ALL on the same net: the part is shorted out
(a resistor with both legs on one net, a capacitor across nothing, a connector with every pin tied together).

**Why.** Such a part does nothing and almost always hides a typo in `netlist.py` (a net name pasted twice). It is a
pure-graph check, so it needs no part records.

**Basis.** Netlist topology only. `needs`: `parts`. Severity ERROR; a waiver may demote it (WAIVED) with a `why`.

**Example fix.** `R("R2", "47k", "DISCH", "DISCH", G)` -> `R("R2", "47k", "DISCH", "TRIG", G)`: give the second pin
the net it was meant to have.

**Known limits.** Parts with a single connected pin are not judged (see LINT-SINGLE-PIN for single-pin nets).
Deliberate bridges such as a 0 R link or a solder jumper that shorts two pins of ONE part are not modelled; waive it.
