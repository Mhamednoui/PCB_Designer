# EL-ABSMAX

**What.** A pin whose net can go above its absolute-maximum voltage (`abs_max.v_max`) or below its minimum (`v_min`).
The net's voltage is the worst-case interval from the electrical model (`tools/boardgen/elec/model.py`); the rating comes
from the part record through the IR (`parts[*].pins[*].abs_max`). A rating written `pin:N+off` ("VCC + 0.5 V") is
resolved from pin N of the same part, at that net's high corner.

**Why.** Absolute-maximum violations destroy parts quietly: a 5 V signal on a 3.3 V-only GPIO works on the bench for a
while. This is the check that catches a 5 V net wired to a 3.3 V pin.

**Where it runs.** Pipeline stage `electrical` (right after `ir`; `python pipeline.py <id> --only ir,electrical`), over
`out/design.json`. Not part of `lint`: it needs the derived model. Severity ERROR; a waiver (`"check": "electrical"`) may
demote it, a `why` is required.

**Inputs / basis.** IR `parts`, `nets`, and the model (`needs=("parts","nets","electrical")`). Intervals count when their
status is derived, claimed-only (a NET_SPEC claim, used as an assumption) or conflict.

**NOT_JUDGED (shown, never failing a `hand` board, never waivable).** One finding per part: pins of an active part with
no `abs_max` in the record; pins whose net voltage is not known; a `pin:N` rating whose supply net is not known; a part
with no record at all.

**Example fix.** `U1.EN: 5.25 V max > 3.6 V limit` -> put a divider or level shifter between the 5 V net and the pin,
or power the part from a rail inside its rating; if the net really is 3.3 V, correct the wrong `NET_SPEC` entry.

**Known limits.** Current ratings (`i_ma`) are not judged (the model carries no per-pin current yet). A signal and its
`pin:N` supply are assumed to track (limit taken at the supply's high corner); independent rails with an uncorrelated
tolerance are not modelled. Transients and ESD are out of scope (SPICE / `emc`).
