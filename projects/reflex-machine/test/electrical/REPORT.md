# Stage 1 - Electrical check on the real PCB file

Run 2026-09-17 via the `kicad` MCP server directly on `reflex-machine.kicad_pcb` (not a recreation -
the actual copper). Re-run these same calls after any layout change.

## DRC
0 errors, 213 warnings - all `silk_overlap`/`silk_over_copper` (values printed over pads, expected
and documented, fab trims automatically).

## Power integrity
- GND: 2 filled copper zones, 202 stitching vias - solid.
- `+5V`: 279mm total, 0.8mm min width.
- `+3V3` / `+3V3_ESP`: 0.3mm, fine for logic-level current.

## Per-magnet current path (the number that matters before fab)
- `+12V` bus: 1.5mm traces + a filled copper pour.
- `MAG1_OUT` (representative of all 10 magnet output nets, coil -> MOSFET drain): 1.5mm trace,
  single layer (B.Cu), **no vias in the current path**.
- 1.5mm trace at 1oz copper comfortably exceeds the 1.5A/magnet design target with margin -
  no widening needed unless the user reports a higher real magnet current.

## Signal integrity
Longest nets and via counts reviewed (`+12V`, `MAG*_PWM`, `I2C`, `SEG_*`, `ESP_RX2`, `COIN_IN`) -
nothing flagged; these are low-speed digital/PWM signals, not high-speed/RF, so trace length is
not a functional concern here.

## How to re-run
```
mcp__kicad__run_drc(pcb_path=".../reflex-machine.kicad_pcb")
mcp__kicad__analyze_pcb_power_integrity(file_path=".../reflex-machine.kicad_pcb")
mcp__kicad__analyze_pcb_signal_integrity(file_path=".../reflex-machine.kicad_pcb")
mcp__kicad__find_tracks_by_net(file_path="...", net_name="/MAG<n>_OUT")   # per magnet if checking a specific one
```

**Verdict: pass. No electrical red flags on the real board.**
