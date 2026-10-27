# Stage 2 - SPICE simulation of the real analog subcircuits

Run 2026-09-17 with LTspice 26.0.2 (installed via `winget install AnalogDevices.LTspice`), driven by
the workspace's `spice` skill against the analyzer output of the real `reflex-machine.kicad_sch`.

## Bugs found and fixed in the vendored `spice` skill (`.claude/skills/spice/scripts/`)
The skill was written against ngspice and had never been run with LTspice on this machine. Three real
bugs were fixed so LTspice results parse correctly (see `docs/LESSONS_LEARNED.md` for the durable
write-up):
1. **Log file collision** (`simulate_subcircuits.py`) - the orchestrator wrote its own stdout/stderr
   capture to `<label>.log`, the exact filename LTspice uses for its own `.meas` results, clobbering
   them before they were read. Renamed the orchestrator's file to `<label>.run.log`.
2. **ngspice/LTspice function name mismatch** (`spice_simulator.py`) - testbenches are generated with
   ngspice syntax (`vdb()`, `vp()`, `vm()`); LTspice has no such functions, only `db(v(...))`,
   `ph(v(...))`, `mag(v(...))`. Added a translation step in `LtspiceBackend.format_measurement_block`.
3. **`.meas` result parsing** (`spice_simulator.py`) - LTspice 26's single-line `.meas` log format
   (`name: expr=target AT value`) wasn't recognized (the parser expected an older multi-line format).
   Rewrote the parser to prefer the `AT` value for threshold-crossing measurements and the `=` value
   for MIN/MAX measurements.

## Results: 9/9 RC filters confirmed (the debounce/noise-filter fix)
These are exactly the button-debounce and coin-optocoupler filters called out in `PROJECT_LOG.md` as
the fix for "false coin when a button is pressed":

| Components | Circuit | Calculated fc | Simulated fc | Error |
|---|---|---|---|---|
| R42/C8 (10k/1nF) | Coin optocoupler output filter | 15915 Hz | 15878 Hz | 0.24% |
| R43-R46 / C9-C12 (1k/100nF, series leg) | Button debounce (S1,S2,S3,RST) | 1592 Hz | 1588 Hz | 0.24% |
| R47-R50 / C9-C12 (10k pull-up/100nF) | Button debounce (S1,S2,S3,RST) | 159 Hz | 159 Hz | 0.23% |

**Verdict: pass.** Real SPICE confirms the filter math, not just the analyzer's calculation.

## Real finding: TX/RX level-shifter divider (R62/R63) margin is tighter than it looks
The automated testbench assumed a 3.3V source and reported "pass" trivially - **that assumption is
wrong**. R62/R63 actually divide the Mega's **5V** UART TX line down for the ESP32's 3.3V RX pin
(`gen/netlist.py:122-123`, matches the level-shift problem noted in `PROJECT_LOG.md` part 2). Hand
recalculation with the real source voltage:

| Mega TX voltage | Vout at ESP_RX2 | ESP32 RX abs. max (~3.6V) | Margin |
|---|---|---|---|
| 5.0V (nominal) | 3.33V | 3.6V | 270 mV |
| 5.25V (USB-high) | 3.50V | 3.6V | 100 mV |

Not a defect - the divider works and stays under the ESP32's absolute maximum - but the margin is
tighter than the ratio alone suggests. No action needed unless the user's Mega runs from a supply
above spec.

## Not usefully validated this pass
- **Voltage divider (R62/R63) automated check** - skipped: the LTspice-generated testbench for this
  detector never emits a `.meas`/output statement (a `spice_templates.py` generator gap, not an
  LTspice issue). Verified by hand instead (above).
- **Decoupling/PDN impedance (C1, C2/C3, C6/C7/C13)** - skipped: the testbench references an undefined
  vector name (`z_mag`) in its `.meas` statements, a pre-existing template bug independent of the
  simulator. Bulk cap presence per rail was already confirmed in Stage 1's power-integrity check.
- **Protection diode D1** - reported "present" only; generic diode model, no real clamping-voltage data
  (expected - `datasheets` skill would be needed for a manufacturer TVS model).
- **Inrush transient** - ran but returned an implausible settled-voltage reading (0.003V); the parser
  fix above targets `.meas` lines, not `.step`/transient trace values, so treat this result as
  unverified rather than a real finding.

## How to re-run
```
python <kicad-skill>/scripts/analyze_schematic.py reflex-machine.kicad_sch --analysis-dir analysis/
LTSPICE_PATH="/c/Users/nouir/AppData/Local/Programs/ADI/LTspice/LTspice.exe" \
  python <spice-skill>/scripts/simulate_subcircuits.py --analysis-dir analysis/ --simulator ltspice --timeout 15
```
