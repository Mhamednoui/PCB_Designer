# EL-DROPOUT

**What.** For every LDO (`regulator.topology == "ldo"`): `headroom = Vin_min - (series fuse/PTC drop at peak current) - (Vout_max +
dropout)`. ERROR below 0, WARN below 0.1 V.

**Why.** A linear regulator whose input falls under Vout + dropout stops regulating: the rail sags with the supply. The
AMS1117-3.3 needs ~1.1-1.3 V, the LDL1117 ~0.35 V typ / 0.6 V max, so on a 4.40 V USB low corner the first brown-outs and the
second does not.

**Where it runs.** Pipeline stage `electrical`; severity ERROR; waivable.

**Inputs / basis.** Vin_min from the model interval of the input net; fuse drop = record `fuse.r_max_ohm` x the peak current
(budget); Vout_max = record `regulator.vout.max`; dropout = the record's `regulator.dropout` row: the smallest tabulated current
at or above the load (dropout only rises with current, so one high-current row is an upper bound; the finding says which row
and whether the load is above every row), its `max` else `typ`.

**NOT_JUDGED.** Input voltage not derivable, `vout.max` or a `dropout` row missing (the field is named), or a series fuse with no
`r_max_ohm` when the headroom is otherwise positive (when it is already negative the missing resistance can only make it worse:
ERROR).

**Example fix.** `ERROR EL-DROPOUT U2: U2 headroom 4.4 - 0.127 (F1 drop) - 3.399 (Vout max) = -0.426 V; dropout needed 1.3 V @ 466
mA (ams1117-3.3 rec)` -> use a low-dropout part (LDL1117), or raise the minimum input. Mutation: M-ldo.
