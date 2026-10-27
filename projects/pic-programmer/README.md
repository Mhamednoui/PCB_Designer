# pic-programmer — NOT a real project of ours

This is **KiCad's own bundled demo board**, copied in unchanged from
`C:\Program Files\KiCad\10.0\share\kicad\demos\pic_programmer\`.

It exists for exactly one reason: to **prove the webview platform is genuinely project-agnostic**.
It is a third-party board with no relationship to this workspace — no `gen/netlist.py`, no scripted
pipeline, no firmware of ours. It was onboarded with:

```
python webview/tools/onboard.py pic-programmer
```

and appeared in the platform with **zero changes to `webview/server/` or `webview/app/`** — which is the
genericity promise in `webview/ROADMAP.md` Phase 3, verified rather than assumed.

## Don't
- Don't design, route, or fabricate this. It isn't ours and isn't meant to be built.
- Don't delete it casually either — it's the regression test for "does the platform still work for a
  project that isn't reflex-machine?" Re-onboarding it after a platform change is a cheap sanity check.

## What it demonstrates
- The design is read straight from `pic_programmer.kicad_pcb` (63 components, 34 nets) by
  `webview/tools/kicad_pcb.py` — no `gen/netlist.py` needed.
- Icons fall back to generic per-reference-prefix symbols, and reuse whatever is already in the shared
  icon cache (3 of its 6 symbols were already cached from reflex-machine).
- `live_sim` is correctly `false`: it has no `wokwi_map.json`, so the platform disables Start Simulation
  for it instead of offering something that can't work.
