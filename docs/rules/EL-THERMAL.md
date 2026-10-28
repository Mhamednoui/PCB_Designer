# EL-THERMAL

**What.** Junction temperature `Tj = Ta + P x theta_JA` against the record's `tj_max` at the peak current, for LDOs
(P = Vin_max x (Iout + Iq) - Vout x Iout, Vin_max after the fuse drop), switcher modules (P = Pout x (1/eff_min - 1)), MOSFETs
(P = Id^2 x Rds(on), Id = EXTERNAL `out` current on the drain net, Rds(on) of the record row at the largest tested Vgs the gate
drive reaches) and resistors with a derived current (P = I^2 R vs `p_max_mw`). Ta = 40 C unless `meta.ambient_c` is set.

**Why.** A 5 V -> 3.3 V LDO at 465 mA dissipates 0.85 W: 142 C on the datasheet's own test board. Nothing else in the flow looks.

**Where it runs.** Pipeline stage `electrical`; ERROR when Tj > tj_max (resistor: P > rating), WARN within 10 C of it (resistor:
over 50 % of the rating); waivable.

**Basis and its limit.** theta_JA is the datasheet test-board value and is **copper-dependent**: the achieved value of the real
layout (tab copper, vias, airflow) is not modelled, so every finding says "theta_JA from datasheet test board: copper-dependent".
When a record lists several theta_JA rows the largest is used (pessimistic). peak = design point (continuous, 100 % duty): the
thermal time constant of a SOT-223 is tens of seconds, so a real duty-cycled workload can sit far below; waive with that reason,
as ref-esp32 ARCHITECTURE section 2.3 does. Rds(on) is the 25 C maximum; its rise with temperature is not modelled.

**NOT_JUDGED.** `electrical.theta_ja` / `tj_max` / `p_max_mw` / `rds_on` missing (named), no declared drain current, a gate net with
no derived voltage. Never a pass.

**Example fix.** `ERROR EL-THERMAL U2: U2 Tj 142 C > 125 C (P 0.853 W ...)` -> add a buck stage, lower the peak, or
add copper and re-derive theta_JA. Mutation: M-heat (a 10R LED resistor on blinky-555).
