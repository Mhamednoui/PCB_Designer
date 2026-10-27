# Workspace improvement roadmap (branch `improve/roadmap-v1`)

Not to be confused with `webview/ROADMAP.md` (the 3D platform's own feature history).
Evidence for every task: `AGENT_NOTES.md` §0/§A/§B/§C. Status: ⬜ todo · 🔄 in progress · ✅ done · ⛔ blocked.

## 1. Vision
A green pipeline must mean a good board. Today stages print violations and still report "ok", the
board generator is copy-pasted three times and already drifting, and nothing is tested automatically.
"Better" = **honest gates, one copy of every generator, a regression suite that proves both, a fresh
clone that tells you exactly what's missing, and docs lean enough to load every session.**
Signed-off boards (reflex-machine, uno-toggle) are never rebuilt in place by this roadmap.

## 2. Goals (measurable)
| ID | Goal | Measure |
|---|---|---|
| G1 | Honest pipeline | every stage exits non-zero when the "done" criteria (PCB_CREATION_GUIDE §2 step 6) fail; a negative test proves it |
| G2 | No duplicated generator code | `make_pcb.py` shared core in `tools/boardgen/pcb.py`; per-project file ≤100 lines (blinky/uno), ≤200 (reflex); 0 diverged shared functions |
| G3 | Automated regression suite | `python -m unittest discover tests` green in <90 s locally; non-KiCad subset green in GitHub CI; tracked tree clean after a run |
| G4 | Fresh clone → first board | `python tools/doctor.py` names every missing dependency with its fix; documented setup in README |
| G5 | Lean, correct docs | CLAUDE.md ≤120 lines; 0 open stale/contradictory items from AGENT_NOTES |
| G6 | No medium+ security findings | POSTs reject foreign Origin/Host; actions confined to the repo |

## 3. Milestones

### M1 Stabilize - honest gates + one generator
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| M1-T1 | Shared stages exit non-zero on failure (netlist mismatch / ERC error, failed export, drill cross-check mismatch); audit `make_sch.py` | `tools/boardgen/{check_sch,make_outputs,make_fab_report,make_sch}.py` | medium | - | a broken input → exit 1; blinky `sch-check,outputs,fabreport` still exit 0 | ⬜ |
| M1-T2 | `pipeline.py`: `sys.executable` not bare `python`; end-of-run per-stage summary; check stages stop dirtying tracked files (see D2) | `pipeline.py`, `.gitignore` | medium | - | `--list` unchanged for all 4 projects; `git status` clean after `--only sch-check,check` | ⬜ |
| M1-T3 | Extract `make_pcb.py` into `tools/boardgen/pcb.py` per §A plan (blinky version wins; 5 hooks); `stage_check`/`stage_finish` exit 1 on violations | `tools/boardgen/pcb.py` (new), `projects/*/gen/make_pcb.py` | high | - | blinky `--force` rebuild = 0/0/0 + 3 silk; uno/reflex: `check` results unchanged + `place` into a scratch copy diffs only in expected silk text (see D1) | ⬜ |
**DoD:** G1 + G2 met; blinky full rebuild green; uno/reflex boards untouched in git.

### M2 Test
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| M2-T1 | Smoke suite per §B (compile, `--list`, blinky 0/0/0/0 on a temp copy, pinmap, negative pin test, `kicad_pcb.py`/`vcd.py` units); KiCad tests skip cleanly if KiCad absent | `tests/` (new) | medium | M1 | green <90 s; negative test fails on pre-M1 code | ⬜ |
| M2-T2 | GitHub Actions running the non-KiCad subset on push/PR (see D5) | `.github/workflows/test.yml` | low | M2-T1 | CI green on the branch | ⬜ |
**DoD:** G3 met.

### M3 Harden
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| M3-T1 | Reject POSTs with foreign Origin / non-localhost Host; confine `actions.json` scripts to paths inside the repo (see D4) | `webview/server/{server,actions}.py` | medium | - | curl with `Origin: http://evil` → 403; UI still works (Start/Run SPICE/actions) | ⬜ |
| M3-T2 | `tools/doctor.py`: KiCad, Freerouting, LTspice, PlatformIO, wokwi-cli, token present (never printed), node; resolve Freerouting path in `kicad_paths.py` with a clear error + fetch instructions | `tools/doctor.py` (new), `tools/boardgen/kicad_paths.py` | medium | M1-T3 | all green here; renaming a tool dir gives an actionable message | ⬜ |
| M3-T3 | `pipeline.py` `firmware` stage (`pio run`, so Wokwi works from a fresh clone) + `--new <id>` scaffold (brief template + netlist/make_pcb stubs) | `pipeline.py`, `tools/boardgen/templates/` (new) | medium | M1-T2, M1-T3 | `--new demo` → `--list` works; firmware stage builds uno-toggle | ⬜ |
**DoD:** G4 + G6 met.

### M4 Polish - docs + housekeeping
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| M4-T1 | Slim CLAUDE.md: session log → `docs/SESSION_LOG.md`, keep rules/env/status/pointers | `CLAUDE.md`, `docs/SESSION_LOG.md` (new) | low | - | ≤120 lines, nothing lost | ⬜ |
| M4-T2 | Fix stale/contradictory docs (§0, §C): webview README/ROADMAP, HANDOVER, LESSONS 21, LESSONS 11-12 vs guide dedupe, README setup + doctor + new stages | `README.md`, `docs/*.md`, `webview/*.md`, `projects/*/README.md`, `HANDOVER.md` | low | M1-M3 | every path/command in docs exists; 0 open doc items | ⬜ |
| M4-T3 | Housekeeping (see D3): `CODES/` → `projects/reflex-machine/firmware/` + pinmap path; duplicate `reflex-machine/out/render_*.png`; `.mcp.json` konnect; stray `tools/skidl_REPL.*`; MANUFACTURING.md timestamp churn | as listed | low | M2-T1 | pinmap still 0 mismatches; tests green | ⬜ |
**DoD:** G5 met; AGENT_NOTES has no open item without an owner or a "won't fix".

## 4. Parallelization (max 3 agents; worktrees when parallel)
- Wave 1: M1-T1 ‖ M1-T2 ‖ M1-T3 (disjoint files). T3's worktree needs a junction to the git-ignored `tools/freerouting`.
- Wave 2: M2-T1 ‖ M3-T1 ‖ M4-T1
- Wave 3: M2-T2 ‖ M3-T2 ‖ M3-T3
- Wave 4: M4-T2 → M4-T3 (sequential; both touch docs)

## 5. Risks & decisions needing the user
- **D1** M1-T3 changes what uno-toggle/reflex-machine *would* produce on their next rebuild (silk text 0.7→0.9 mm, reflex GND-seed fix). Not rebuilt now - verified only by scratch-copy diff + `check`. OK?
- **D2** Untrack the volatile check outputs `projects/*/out/{drc.json,erc.json,netlist.net}` (git index only; files stay on disk). OK?
- **D3** M4-T3 deletes/moves files (duplicate renders, `CODES/` move, `skidl_REPL.*`) and drops `konnect` from `.mcp.json` unless you plan to install it.
- **D4** M3-T1 makes the server refuse actions pointing outside the repo - any custom action you rely on elsewhere?
- **D5** Public repo → GitHub Actions minutes are free. Add CI?
- Deferred, needs your call later: three.js r160 → current (major upgrade); reflex-machine pre-fab items (magnet current, ESP32 pitch, 0.489 mm hole gap) need physical measurement or a sanctioned rebuild.
- Risk: worktree builds need KiCad + Freerouting outside git; agents link them in rather than copy.
