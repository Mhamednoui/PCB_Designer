# EL-OD-PULLUP

**What.** A net with an open-collector / open-drain pin (or an I2C-named net: SDA/SCL) that has no pull-up resistor to a
rail, or whose pull-up is too small for the weakest sink: `R_min (-5 %) < Vrail_max / Iol_max`.

**Why.** An open-drain output can only pull low. Without the pull-up the line never goes high (I2C bus stuck, optocoupler
output never rises); with too small a one it overloads the driver.

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`. Severity ERROR; waivable with
`"check": "electrical"` and a `why`.

**Inputs / basis.** The net's drivers and resistors, the rail intervals from the model, and the sink pin's
`i_out_max_ma` (`needs=("parts","nets","electrical")`). A pull-up is a resistor to a rail (net class `power`, or fed by an
EXTERNAL supply / regulator) at >= 1 V.

**NOT_JUDGED.** The pull-up's rail voltage is unknown; the net has no pull-up on the board but leaves it through a
connector (the peripheral may carry the pull-up); or no sink pin states `i_out_max_ma` (the value is then not
checked). Shown per net, never failing a `hand` board, never waivable.

**Example fix.** `net DISCH: open-drain driver U1.7, no pull-up resistor to a rail` -> add a resistor from the net to
the supply the receiver uses (4.7 k for I2C, 10 k for a slow line).

**Known limits.** The rise-time upper bound (needs bus capacitance and speed mode) is not computed. Pull-downs are
ignored. Internal MCU pull-ups are not modelled, so an MCU input relying on one is reported.
