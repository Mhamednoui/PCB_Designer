# EL-BUDGET

**What.** The peak current each power rail has to carry, against every limit on the path to it: the EXTERNAL supply pins that
feed it (`i`), the regulator that drives it (`regulator.i_max_ma`), a series fuse / PTC (`fuse.i_hold_ma`) and the net's own
`i_max` (NET_SPEC, the copper design figure). ERROR above a limit, WARN above 80 % of it (margin < 20 %).

**Why.** A rail that is wired, fused and routed can still be asked for more than its regulator, fuse or connector gives.
Nothing in ERC or DRC knows a 2 A load was added to a 1.2 A LDO.

**Where it runs.** Pipeline stage `electrical`, over `out/design.json`; severity ERROR. Waivable with `"check": "electrical"`.

**Inputs / basis.** `boardgen.elec.budget`: record `electrical.load_ma` of each IC on its power_in pins, resistors from a rail
(V/R; pull-ups counted as if the line were pulled low), LED branches (V - Vf)/R, EXTERNAL `out` pins with `i`, regulators
back-propagated (LDO: + Iq, switcher module: Pout/(efficiency min x Vin min)), fuses/diodes passed through. V = high corner of
the rail's model interval, R -5 %. **peak = design point** (everything on at once, continuous); typical is computed alongside and
judged by nothing. Duty cycle, inrush and temperature are not modelled.

**NOT_JUDGED.** A load with no derivable current is listed with the missing field (`electrical.load_ma of U3`, `EXTERNAL i of
J12.1`, `electrical.vf of D21`); the total is then a lower bound. A lower bound already over a limit is still an ERROR (the real
number is higher); under the limit it is NOT_JUDGED. A limit whose record field is missing (`regulator.i_max_ma`,
`electrical.fuse.i_hold_ma`) is NOT_JUDGED too. Never a pass.

**Example fix.** `ERROR EL-BUDGET 3V3: 3V3 peak 2366 mA > regulator U2 output rating 1200 mA; biggest: J2.1 2000 mA` -> cut the
load, use a stronger regulator, or declare the real current. Mutation: M-load.
