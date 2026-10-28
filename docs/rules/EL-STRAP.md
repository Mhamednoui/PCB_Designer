# EL-STRAP

**What.** For every MCU covered by a strap profile (`blocks/<mcu>.strap.json`), derive each strapping pin's level at reset
from the design and compare it with the boot state the datasheet requires; also check the reset pin (EN) has an RC delay.
Checked for the ESP32-S3: GPIO0 (must be high for SPI boot, no high-value capacitor, a BOOT button to GND to enter download
mode), GPIO45 (must be low = 3.3 V VDD_SPI), GPIO46 (no pull-up, or download mode breaks), GPIO3 (JTAG source, ignored
at eFuse defaults), EN (pull-up 4.7-47 k plus 0.1-10 uF to GND; recommended 10 k + 1 uF).

**Why.** A wrong level on a strapping pin does not fail ERC or DRC: the board is wired, powered and simply boots into the
wrong mode (download mode, 1.8 V flash supply on a 3.3 V flash, no reset delay).

**Where it runs.** Pipeline stage `electrical` (after `ir`), over `out/design.json`; severity ERROR, WARN for a missing
BOOT button. Waivable with `"check": "electrical"` and a `why`. On a design with no covered MCU the rule is skipped
("not applicable", examined 0): that is not an error.

**Inputs / basis.** The part's registry record id (`applies_to.registry` in the profile), the record's pin names (unconnected
strap pins are not in the IR's `pins`), resistors/capacitors/switches on the pin's net, and the model's rail voltages.
A pull resistor decides the level when it is at most `policy.ext_pull_max_ohm` (100 k, a policy value: the datasheet gives
no internal resistance). Sources and section numbers are inside the profile, per pin: ESP32-S3-WROOM-1 datasheet v1.8
(Table 4-1 defaults, 4-3 boot mode, 4-4 VDD_SPI, 4-5 JTAG, section 9 EN RC) and the Espressif Hardware Design Guidelines
schematic checklist ("Strapping Pins", "Chip Power-up and Reset").
The numeric limits Espressif does not give are marked POLICY in the profile: GPIO0 capacitor limit 1 nF, EN R and C windows.

**NOT_JUDGED.** The strap net also goes to another device (its level at reset is that device's), a resistor goes to a net of
unknown voltage, pulls in both directions, a pull weaker than the policy limit, or a pin that must be a given level is
floating. Shown, never failing a `hand` board.

**Example fix.**
`ERROR EL-STRAP C9: IO0: expected pull-up without a high-value capacitor [HWC 'Strapping Pins'], found R4 pull-up 10 k to
3V3 + capacitor C9 100 nF to GND ... (> 1 nF)` -> remove C9; debounce the BOOT button in firmware instead.
`IO45: boot level must be LOW [DS Table 4-4] but found R8 pull-up 10 k to 3V3 -> HIGH` -> remove R8; the internal pull-down
already gives 3.3 V VDD_SPI. `EN: no pull-up ... no capacitor` -> 10 k from EN to 3V3 and 1 uF from EN to GND.

**Adding another MCU.** Copy `blocks/esp32s3.strap.json` to `blocks/<mcu>.strap.json`; set `applies_to.registry` to the
registry record ids, and per pin `pin` (the record's pin name), `internal_pull` (up/down/none), `normal` (list of allowed
levels, or `["any"]`), optional `cap_max_f`, `download` and `reset`, each with its `*_src` citation. No code change.

**Known limits.** Internal pull strength, eFuse state and boot-time sequencing are not modelled (no EN timing check against
tSTBL/tH). A strap pin used as a GPIO to another device is NOT_JUDGED, not analysed. Only the WROOM-1-N8 record is mapped.
Fixtures: `tests/rules/fixtures/EL-STRAP` (green = ref-esp32 strap wiring; red = 100 nF on GPIO0, pull-up on GPIO45, no EN
RC), mutations `M-strap` and `M-strap-pu45` on the netlist-only fixture project `projects/synth-esp32s3`.
