# Wokwi simulation-minute usage log — uno-toggle

Free tier: **50 minutes (3000 seconds) per calendar month, shared across all projects on this account.**
`wokwi-cli lint` is free and NOT logged here. Only real timed runs count — including every
Start/Stop cycle through the webview platform, which the backend appends here automatically
(see `webview/server/wokwi_mcp.py`).

| Date | Run | Duration (s) | Running total this month (s) | Remaining (s / min) |
|---|---|---|---|---|
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 17 | 17 | 2983 / ~49.7 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 10 | 27 | 2973 / ~49.5 |
| 2026-09-17 | webview platform - live sim session (auto-stopped at time limit) | 13 | 40 | 2960 / ~49.3 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 11 | 51 | 2949 / ~49.1 |
| 2026-09-17 | webview platform - live sim session (webview Start/Stop) | 6 | 57 | 2943 / ~49.0 |
| 2026-09-18 | webview platform - live sim session (auto-stopped at time limit) | 12 | 69 | 2931 / ~48.9 |

**Month: September 2026. Total used: 69s. Remaining: ~48.9 min.**
**Note**: the reflex-machine project keeps its own log at `projects/reflex-machine/test/wokwi/USAGE_LOG.md`.
The 3000s budget is per **account**, not per project — add both logs together for the real remaining figure.
