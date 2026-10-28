# EL-CONTENTION

**What.** Two push-pull outputs on one net, or a push-pull output on a ground net or on a net that has a `power_out`
pin (a regulator output).

**Why.** Outputs that disagree fight: both are damaged and the net sits at an undefined level. Usually a net-name typo
(two outputs given the same name) or an output wired to the wrong header pin.

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`. Severity ERROR; waivable with
`"check": "electrical"` and a `why`.

**Inputs / basis.** The model's per-net drivers (pin class `output`, not `tristate`): `needs=("parts","nets","electrical")`.
Open-collector pins are sink-only and never contend with each other; tristate outputs are skipped (enable logic is not
modelled).

**NOT_JUDGED.** A net with a bidirectional pin plus another driver, or two bidirectional pins (an MCU GPIO's direction is
not in the records): shown per net, never failing a `hand` board, never waivable.

**Example fix.** `net OUT driven by U1.3 and U2.3` -> give each output its own net, or join them through a gate or a
diode-OR; if one is meant to be a bus, make the drivers open-drain or tristate.

**Known limits.** An output on the same net as an EXTERNAL (connector) driver is not flagged: the outside world's
drive strength is unknown. Two `power_out` pins on one net (paralleled regulators) are not checked here.
