# LINT-SINGLE-PIN (legacy name `single-pin`)

**What.** A net that touches exactly one pin. Nothing else is connected to it.

**Why.** A net with one pin cannot carry a signal: it is a misspelt net name (`LED_A` vs `LED_a`), a forgotten
second part, or a wire to nowhere. DRC cannot see it (one pad, no ratsnest), so it passes ERC and DRC and ships.

**Basis.** Netlist topology only. `needs`: `nets`. Severity ERROR; a waiver may demote it (WAIVED) with a `why`.

**Example fix.** The net `OUT` touches only `R1.2`: connect `R2.1` to `OUT` as intended, or delete the pin from
`netlist.py` if the net is a typo.

**Known limits.** A deliberate test point or connector pin that is meant to float is reported too; declare it NC in the
registry or waive it with the reason.
