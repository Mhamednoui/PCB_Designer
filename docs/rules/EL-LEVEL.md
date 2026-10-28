# EL-LEVEL

**What.** The driver's worst-case logic levels must reach the receiver's thresholds: `VOH min >= VIH min` and
`VOL max <= VIL max`. ERROR when the margin is negative, WARN when it is below 0.1 V (spec P2 section 8 Q1).

**Why.** A 3.3 V output into a 5 V CMOS input (VIH 0.7 x VCC = 3.5 V) works on the bench and fails over temperature or
supply tolerance; a 5 V logic output into a 12 V CMOS input never switches it.

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`. Severity ERROR; waivable with
`"check": "electrical"` and a `why`.

**Inputs / basis.** Examined: every non-rail net (not ground/power, no supply output or EXTERNAL supply) with an `input`-class receiver and at least one direct driver. Driver levels are
`net.levels` from the model (output / tristate pin with a VOH/VOL datum measured within 10 % of its actual supply).
Receiver `vih.min` / `vil.max` come from the pin record (numbers, or `ratio:k*vdd` evaluated on the receiver's supply
net; on another rail than the driver the worst corner of that rail, on the same rail the same corner).

**NOT_JUDGED.** The driver is bidirectional (MCU GPIO), external, open-collector, or has no usable VOH/VOL; the receiver's
record states no VIH/VIL; or its supply voltage is unknown. Shown per pin, never failing a `hand` board, never waivable.

**Example fix.** `driver U1.1 VOH min 3.84 V < VIH min 9.24 V, receiver on 12V` -> put a level shifter between the
two, or run both on the same rail.

**Known limits.** A level that reaches the pin through a resistor network or divider is not judged here (EL-ABSMAX and the
`static_logic` requirements cover those). Input hysteresis, load current on VOH/VOL and bus-keeper effects are not modelled.
