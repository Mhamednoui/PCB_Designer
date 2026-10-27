# Wokwi simulation-minute usage log

Free tier: **50 minutes (3000 seconds) per calendar month**. `wokwi-cli lint` is free and NOT logged here
(no simulation runs). Only real timed runs (`wokwi-cli --elf ... --timeout ...` or interactive play at
wokwi.com) count. I update this immediately after every run I make - ask me for the running total any
time, or check the bottom row.

| Date | Run | Duration (s) | Running total this month (s) | Remaining (s / min) |
|---|---|---|---|---|
| 2026-09-17 | 5s headless run, real firmware.elf, wiring/crash check only | 5 | 5 | 2995 / ~49.9 |
| 2026-09-17 | `scenario_inputs.yaml` - pressed S1/S2/S3/RST/coin, asserted each pulls the correct Mega pin LOW (all 5 passed) | 8 | 13 | 2987 / ~49.8 |
| 2026-09-17 | MCP probe (`wokwi-cli mcp .`) - validated live start/press/read/stop cycle for the webview platform's real-time backend integration | 5 | 18 | 2982 / ~49.7 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 5 | 23 | 2977 / ~49.6 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 7 | 30 | 2970 / ~49.5 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 5 | 35 | 2965 / ~49.4 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 14 | 49 | 2951 / ~49.2 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 14 | 63 | 2937 / ~49.0 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 17 | 80 | 2920 / ~48.7 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 14 | 94 | 2906 / ~48.4 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 12 | 106 | 2894 / ~48.2 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 23 | 129 | 2871 / ~47.9 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 22 | 151 | 2849 / ~47.5 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 27 | 178 | 2822 / ~47.0 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 24 | 202 | 2798 / ~46.6 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 42 | 244 | 2756 / ~45.9 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 72 | 316 | 2684 / ~44.7 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 53 | 369 | 2631 / ~43.9 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 23 | 392 | 2608 / ~43.5 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 30 | 422 | 2578 / ~43.0 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 11 | 433 | 2567 / ~42.8 |

**Month: September 2026. Total used: 433s. Remaining: ~42.8 min.**
**Note**: from now on, every `POST /api/projects/reflex-machine/sim/start` .. `/sim/stop` cycle through the
webview platform also consumes real quota for as long as it's running - the backend logs each cycle's
duration here too (see `webview/server/wokwi_mcp.py`).
