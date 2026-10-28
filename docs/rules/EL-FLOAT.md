# EL-FLOAT

**What.** An `input`-class pin (CMOS/TTL input) on a net that nothing drives or pulls: no ground/power net, no supply
output, no driver (push-pull, tristate, open-collector, bidirectional, EXTERNAL in/bidir/supply) on the net or on any net
reachable from it through a 2-pin resistor / inductor / fuse / diode / LED. An `analog` pin in the same situation is an INFO
(the 555 CONTROL pin with only a bypass capacitor is the datasheet-recommended wiring).

**Why.** A floating CMOS input picks up noise, sits in the linear region, draws shoot-through current and makes the
circuit behave randomly (a floating reset/enable pin is the classic cause of "works on the bench, not on the board").

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`. Severity ERROR; waivable with
`"check": "electrical"` and a `why`.

**Inputs / basis.** `ctx.model` net drivers / supply sources / source, the part list for the DC path, and `external`
(`needs=("parts","nets","external","electrical")`). Unconnected pads cannot reach the rule: `registry_part()` refuses a pad
that is neither connected nor declared NC, and an NC-declared pad is absent from the IR.

**NOT_JUDGED.** The DC path reaches a connector pin that is not declared in `EXTERNAL` (the other side of the cable may
drive it) or a pin of a part with no class in its record. Shown per pin, never failing a `hand` board, never waivable.

**Example fix.** `floating input RCLK: net LAT has no driver, pull-up/pull-down or supply` -> add a 10 k
resistor from LAT to 3V3 or GND, or drive it.

**Known limits.** A path through a transistor channel or an analog switch is not followed (the net then reads as floating
or NOT_JUDGED, never as driven). A bidirectional MCU pin counts as a driver even if the firmware configures it as an
input. Input-class pins with a weak internal pull (MCU) are not credited.
