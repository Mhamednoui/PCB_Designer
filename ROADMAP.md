# Workspace improvement roadmap (branch `improve/roadmap-v1`)

Execution tracker for **`docs/PLATFORM_PLAN.md`** (the master plan: scope, architecture, risk register, verification matrix, phases P0-P7).
Milestone mapping: MD = P0, MP-T1/T2 = P1, MS-T3 = P3, MS-T1/T2 = P4, MP-T3 = P5, MV = P6, M2-M4 backlog = P7.
Not to be confused with `webview/ROADMAP.md` (the 3D platform's own feature history).
Evidence for every task: `AGENT_NOTES.md` §0/§A/§B/§C. Status: ⬜ todo · 🔄 in progress · ✅ done · ⛔ blocked.

## 1. Vision
A green pipeline must mean a good board. Today stages print violations and still report "ok", the
board generator is copy-pasted three times and already drifting, and nothing is tested automatically.
"Better" = **honest gates, one copy of every generator, a regression suite that proves both, a fresh
clone that tells you exactly what's missing, and docs lean enough to load every session.**
**Primary goal (user, 2026-10-27): a platform that produces valid, expert-level designs and PCBs ready for
manufacturing.** The existing boards are regression fixtures only - they may be rebuilt freely and reproduced later.
Each board declares `ASSEMBLY = "pcba"` (JLCPCB assembles SMD from LCSC) or `"hand"` (through-hole, hand-soldered);
every check enforces that mode's rules.

**Top priority (user, 2026-10-27): design + PCB correctness on complex boards.** Today's gates prove the
board is *consistent* (netlist = schematic = copper), not that the *design is right*: the catch matrix
(`AGENT_NOTES.md` §D-X) shows only 5/12 common mistakes caught. Milestone MD closes that gap and comes first.

## 2. Goals (measurable)
| ID | Goal | Measure |
|---|---|---|
| G0 | **Mistakes are caught, not just consistency** | every mistake class in §D-X + PCB_CREATION_GUIDE §6 (16 total) makes `pipeline.py` exit non-zero, proven by an automated mutation suite (MD-T7); catch rate 16/16 |
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
| M1-T1 | Shared stages exit non-zero on failure (netlist mismatch / ERC error, failed export, drill cross-check mismatch); audit `make_sch.py` | `tools/boardgen/{check_sch,make_outputs,make_fab_report,make_sch}.py` | medium | - | a broken input → exit 1; blinky `sch-check,outputs,fabreport` still exit 0 | ✅ |
| M1-T2 | `pipeline.py`: `sys.executable` not bare `python`; end-of-run per-stage summary; check stages stop dirtying tracked files (see D2) | `pipeline.py`, `.gitignore` | medium | - | `--list` unchanged for all 4 projects; `git status` clean after `--only sch-check,check` | ✅ |
| M1-T3 | Extract `make_pcb.py` into `tools/boardgen/pcb.py` per §A plan (blinky version wins; 5 hooks); `stage_check`/`stage_finish` exit 1 on violations | `tools/boardgen/pcb.py` (new), `projects/*/gen/make_pcb.py` | high | - | blinky `--force` rebuild = 0/0/0 + 3 silk; uno/reflex: `check` results unchanged + `place` into a scratch copy diffs only in expected silk text (see D1) | ✅ |
**DoD:** G1 + G2 met; blinky full rebuild green; uno/reflex boards untouched in git.

### MD Design & PCB correctness (top priority) - ✅ P0 EXIT 2026-10-28: full mutation suite 39/39, all 3 fixtures green on every stage
Evidence: `AGENT_NOTES.md` §D-R (best practice), §D-K (kicad-happy analyzers), §D-X (catch matrix).
**Shared data contract** (all MD tasks use it; MD-T1 adds it to the 3 projects' `netlist.py`; others default sensibly when absent):
```python
NET_SPEC = {                                   # optional, per net
    "VCC": {"v": (9.0, 12.0), "i_max": 0.05},  # volts: number or (min, max); i_max: continuous amps
    "GND": {"v": 0.0},
}   # undeclared nets: v inferred from name (GND=0, +5V=5, +3V3=3.3, +12V=12), i_max default 0.3 A
```
**Waivers** (one file per project, shared by every MD checker): `projects/<id>/waivers.json` =
`[{"check": "<stage>", "rule": "<id>", "refs": [...] | "nets": [...], "why": "<required>"}]`; unused waivers are reported.
New stages are registered in `pipeline.py` by the supervisor at merge time - agents do not edit `pipeline.py`.

| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| MD-T1 | `lint` stage (pure Python, <1 s, runs before `sch`): decoupling cap on every IC supply pin; polarised cap + on the higher-voltage net; LED anode toward higher potential, series resistor present, estimated current in 1-25 mA; footprint pad count/numbers ⊇ symbol pins used; no part shorted (all pins one net); single-pin nets. Add `NET_SPEC` to the 3 projects | `tools/boardgen/lint_netlist.py` (new), `projects/*/gen/netlist.py` | high | - | §D-X b,c,d,f,g,h caught on blinky copies; 3 real projects pass (or waive with reason) | ✅ |
| MD-T2 | (+ MD-T2b: COPPER_OZ, TEMP_RISE_C, pour-aware severities) Fab + current rules: JLCPCB 2-layer limits (§D-R) + per-net min track width from `NET_SPEC.i_max` (IPC-2221 external, 10 °C rise, 1 oz) emitted as the project's `.kicad_dru` at `place`, so DRC enforces them; `fabreport` exits 1 on any `**CHECK**` | `tools/boardgen/fab_rules.py` (new), `tools/boardgen/pcb.py`, `tools/boardgen/make_fab_report.py` | high | - | §D-X i,j caught; blinky rebuild passes; uno/reflex `check` result reported (not rebuilt) | 🔄 |
| MD-T3 | SPICE assertions: signed forward current window (1-25 mA) + reverse-current cap auto-applied to every LED; clear error for 0 Ω / unsupported values instead of "not a binary raw file" | `tools/boardgen/make_spice.py` | medium | - | §D-X b,f,h caught by `spice` on blinky; blinky still passes | ✅ |
| MD-T4 | ERC strictness + generic firmware pin check: promote `ground_pin_not_ground`, `isolated_pin_label`, `power_pin_not_driven` to failing; move `pinmap` into shared `tools/boardgen/check_pinmap.py` reading `FIRMWARE = {...}` from `netlist.py` (+ optional Wokwi `diagram.json` diff). NOTE: when mutating netlist.py in tests run python with `-B` (stale .pyc trap, MD-T1) | `tools/boardgen/check_sch.py`, `tools/boardgen/check_pinmap.py` (new), `projects/{uno-toggle,reflex-machine}/gen/netlist.py` (FIRMWARE only), `projects/reflex-machine/test/pinmap.py` (delete after port) | medium | MD-T1 merged (netlist.py) | §D-X l caught on uno; reflex 26/0 unchanged | ✅ |
| MD-T5 | `review` stage: kicad-happy schematic+PCB+EMC analyzers → `test/review/review.json`; fail on unwaived deterministic errors + DC-001/DC-002 (decoupling distance); waivers per contract | `tools/boardgen/make_review.py` (new), `projects/*/waivers.json` | medium | MD-T1 (waiver format) | reflex flags U3/C13; blinky/uno pass with documented waivers | ✅ |
| MD-T6 | `lvs` stage: independent connectivity from the **gerbers + drill actually sent to the fab** (gerbonara/shapely), diffed against `netlist.py` | `tools/boardgen/gerber_lvs.py` (new) | high | - | 0 diffs on all 3 boards; a cut track injected into a gerber copy → exit 1 | ✅ |
| MD-T8 | Fix the 2 real decoupling-placement defects `review` found: blinky C3 (15.2 mm from U1 pin 8), reflex C13 (36.5 mm from U3); full rebuild of both | `projects/{blinky-555,reflex-machine}/gen/make_pcb.py` + regenerated outputs | medium | MD-T5 | `review` green on both; full pipeline 0/0/0 | 🔄 |
| MD-T9 | Native pad-to-pin decap check in `check` (≤5 mm THT / ≤3 mm SMD; modules reported as SKIP); route retries Freerouting ≤3× until 0 unconnected; `finish` re-run once on native crash | `tools/boardgen/{pcb,decap_check}.py` | medium | MD-T8 | M-decap-far caught by `check`; fixtures green | ✅ |
| MD-T10 | reflex fixture: +12V_IN (J1→F1→pour) sized for 10 A per IPC-2221 | `projects/reflex-machine/gen/{make_pcb,netlist}.py` + outputs | medium | MD-T2b | reflex `check` green | ✅ |
| MD-T11 | Derive every via/stitch/fan-out spacing in `pcb.py` from `fab_rules.py` (hole_to_hole, annular, clearance) instead of local constants (`_stitch_and_fill` used d/2+0.55, rule needs ~d/2+0.65 → flaky hole_to_hole) | `tools/boardgen/{pcb,fab_rules}.py` | medium | MD-T10 | 5 consecutive reflex place→check runs: 0 hole_to_hole errors | ✅ (0 hole_to_hole in 14 runs) |
| MD-T12 | reflex routability regression: after MD-T10 the 7.5 mm +12V_IN pre-route blocks channels → Freerouting fails ~3/8 runs (SPARE_D33, SEG_CLOCK, SPARE_TX3). Fix so 5/5 consecutive full rebuilds route | `projects/reflex-machine/gen/make_pcb.py` (+ `pcb.py` route strategy only if needed) | medium | MD-T11 | 5/5 reflex rebuilds 0/0/0 | ✅ (5/5; stable UUIDs; shorts fail route) |
| MD-T13 | Regression: M-fp-family MISSED after P1-T9b (wrong-family footprint on a registry part now only WARNs in lint). Root-cause + restore an ERROR gate | `tools/boardgen/lint_netlist.py`, `tests/mutations/mutations.json` | medium | P1-T9b | M-fp-family CAUGHT; suite 35/35 | ✅ |
| MD-T7 | Mutation suite (data-driven `tests/mutations/mutations.json`, P1-T4 extends it): each of the 16 mistake classes injected into a temp copy, asserts the pipeline exits non-zero at the expected stage; reports catch rate | `tests/mutations/` (new) | high | MD-T1..T6 | 16/16 caught; runtime reported | ✅ (22/23; M-hole → MD-T11) |
**DoD:** G0 met; all 3 fixtures pass every new stage (or carry written waivers).

### P1 Parts registry - tasks P1-T1..T9 are specified in `docs/design/P1_PARTS_REGISTRY.md` §7 (decisions §9); status tracked here
| ID | St |
|---|---|
| P1-T1 schema + loader | ✅ |
| P1-T2 cache + `parts new/refresh` | ✅ |
| P1-T3 bind/assist/sign | ✅ |
| P1-T4 test records + mutations | ✅ |
| P1-T5 lint PR- rules | ✅ |
| P1-T6 `parts` stage | ✅ |
| P1-T7 generic/connector/mechanical records | ✅ |
| P1-T8 crosschecked records for real parts | ✅ (PC817 → owner) |
| P1-T9a API: pins-by-function, PARTS_RECORDS_DIR, registered-refs API, PR-HOLE severities, `parts new` MPN field | ✅ |
| P1-T9b migrate fixtures to registry (pins by function, `nc=`), `PARTS_STRICT`, C_Polarized, PR-BYNAME | ✅ (M-libpin-swap now CAUGHT) |
| P1-T10 stock source fix: JLCPCB assembly stock (smtGood) for `pcba`, LCSC detail endpoint fallback, jlcsearch last; covers modules + passives (from MV-T0) | ✅ |

### MP Production-ready outputs (both assembly modes) - MP-T1/T2 superseded by P1 above; MP-T3 remains (P5)
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| MP-T1 | `ASSEMBLY` mode in `netlist.py` + mode rules in `lint`: `hand` forbids SMD footprints / fine pitch; `pcba` requires an LCSC number per part, footprint package == LCSC package | `tools/boardgen/lint_netlist.py`, `tools/boardgen/parts.py` (new) | medium | MD-T1 | a 0603 part on a `hand` board fails; a `pcba` part without LCSC fails | ⬜ |
| MP-T2 | Part pipeline: LCSC lookup (stock, basic/extended, package, price) cached per project; `easyeda2kicad` import for non-stock parts with pad-count/pinout cross-check vs symbol | `tools/boardgen/parts.py`, `projects/<id>/lib/` | high | MP-T1 | out-of-stock or package-mismatch part fails `lint`; cache works offline | ⬜ |
| MP-T3 | JLCPCB PCBA outputs: BOM (Comment/Designator/Footprint/LCSC) + CPL with per-package rotation/offset corrections (JLC rotation DB); assembly-side check; `outputs` verifies every placed part has an LCSC row | `tools/boardgen/make_outputs.py`, `tools/boardgen/jlc_rotations.json` (new) | medium | MP-T1 | CPL rotations correct for SOT-23/SOIC/QFN/USB-C fixtures (checked against JLC preview rules) | ⬜ |

### MS Scales to complex boards
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| MS-T0 | Antenna keep-out rule: module records carry the keep-out polygon (from the vendor guide); `check` fails on copper/parts inside it and on antenna not at the board edge (from MV-T0) | `parts/records`, `tools/boardgen/pcb.py` | medium | P1 | ESP32-S3 fixture with copper under antenna fails | ⬜ |
| MS-T1 | Automatic placement: group-based placer from `netlist.py` groups (connectors on edges, decoupling caps within 3 mm of their IC pin, courtyard-aware packing); `placements()` becomes optional overrides | `tools/boardgen/autoplace.py` (new), `tools/boardgen/pcb.py` | high | MD | a 60+ part board places with 0 courtyard errors and every decoupling cap ≤3 mm from its pin | ⬜ |
| MS-T2 | SMD routing support: fan-out vias for SMD pads, netclasses from `NET_SPEC` (power/signal widths), 4-layer stackup option (In1=GND, In2=power) | `tools/boardgen/pcb.py` | high | MD-T2 | SMD fixture routes 0/0/0 on 2 and 4 layers | ⬜ |
| MS-T3 | Multi-sheet (hierarchical) schematic generation from `netlist.py` groups, so a complex schematic stays readable | `tools/boardgen/make_sch.py` | high | - | 1 sheet per group; netlist compare 0 mismatches | ⬜ |

### MV Proof
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| MV-T0 | Reference board brief + architecture (`projects/ref-esp32/`): ESP32-S3-WROOM-1-N8, LDL1117 (not AMS1117: dropout), USB-C FS, 2-layer, ~0.9 W LDO peak → ≥2 cm² tab copper; Q1-Q13 defaults accepted | `projects/ref-esp32/*.md` | high | - | docs reviewed | ✅ |
| MV-T1 | Reference complex board built through the platform only: PCBA, e.g. ESP32-S3 module + USB-C (power + data) + 3V3 LDO + ESD + I2C sensor + status LEDs + buttons | `projects/ref-esp32/` (new) | high | MP, MS | every stage green; fab zip + BOM + CPL pass JLCPCB upload checks | ⬜ |
| MV-T2 | Rebuild the 3 fixtures from their `netlist.py` with all new gates | `projects/*` | medium | MD, MP | all green or written waivers | ⬜ |

### PA Architecture for scale (PLATFORM_PLAN §10) - between P1 and P2
| ID | Task | St |
|---|---|---|
| PA-1 design IR + `ir` stage | ✅ (`tools/boardgen/ir/`, stage `ir` after `check`; stages still read netlist.py until PA-3) |
| PA-2 stage registry + incremental runner | ✅ (`tools/boardgen/stages.json`; `--describe`; `--no-cache`) |
| PA-3 port checks to the IR | ⬜ |
| PA-4 layer-agnostic pcb.py + blinky-4L fixture | ⬜ |
| PA-5 parallel + tiered mutation runner | ✅ (fast tier 28 s, full 129 s @4 jobs) |
| PA-6 run report + tool versions + determinism | ✅ (`out/run/<ts>/report.html`; 2 runs → git clean) |
| PA-7 finding taxonomy, `--explain`, board markers | → folded into P2-T1 |
| PA-8 scaffolds + templates + CONTRIBUTING.md | ⬜ |
| PA-9 pre-commit + CI | ✅ (GitHub Actions green; found+fixed a 0x08-corrupted regex in check_sch.py) |
| PA-10 ADRs + CHANGELOG + platform version | ✅ (docs/adr 0001-0012, VERSION 0.2.0) |
| PA-11 KiCad-schematic input adapter (hand-drawn schematic → PCB) | ⬜ |

### P2 Electrical analyzer + requirements - tasks P2-T1..T10 in `docs/design/P2_ELECTRICAL_ANALYZER.md` §6 (decisions §8)
| ID | St |
|---|---|
| P2-T1 rule engine + Finding + waivers v2 + `--explain` (incl. PA-7) | ✅ |
| P2-T2 record `electrical` block + IR abs_max/EXTERNAL + fixture data | ✅ (IR v2; coverage golden) |
| P2-T3 electrical model v1 | ✅ (`elec/model.py`, `ctx.model`, tests/elec) |
| P2-T4 EL-ABSMAX, EL-CONTENTION, EL-OD-PULLUP | ⬜ |
| P2-T5 EL-FLOAT, EL-LEVEL, EL-NETSPEC | ⬜ |
| P2-T6 budget, dropout, thermal | ⬜ |
| P2-T7 EL-CONN-PROT + EXTERNAL | ⬜ |
| P2-T8 strap evaluator (ESP32-S3) | ⬜ |
| P2-T9 requirements engine (IV-2) | ⬜ |
| P2-T10 release coverage gate, RULES.md, lint migration | ⬜ |

### Independent verification (PLATFORM_PLAN §9) - queued
| ID | Task | Phase | St |
|---|---|---|---|
| IV-1 | Electrical static analyzer (voltage/current propagation, abs-max per pin, contention, floating inputs, pull-ups, rail budget, dissipation) | P2 | ⬜ |
| IV-2 | Executable `REQUIREMENTS` in netlist.py (graph paths, part-class-in-path, voltage/current, simulated behaviour) | P2 | ⬜ |
| IV-3 | Gerber-level DRC `fabcheck` (own geometry, reuses lvs) | P5 | ⬜ |
| IV-4 | IPC-D-356 export for fab electrical test | P5 | ⬜ |
| IV-5 | Property-based generator fuzzing (Hypothesis) | P6 | ⬜ |
| IV-6 | AI design-review agent (advisory; confirmed findings → rule + mutation) | P6 | ⬜ |

## Backlog (after MV)
### M2 Test
| ID | Task | Files | Effort | Deps | Acceptance | St |
|---|---|---|---|---|---|---|
| M2-T1 | Smoke suite (fast subset; mutations live in MD-T7) per §B (compile, `--list`, blinky 0/0/0/0 on a temp copy, pinmap, negative pin test, `kicad_pcb.py`/`vcd.py` units); KiCad tests skip cleanly if KiCad absent | `tests/` (new) | medium | M1 | green <90 s; negative test fails on pre-M1 code | ⬜ |
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
- **MD first.** Wave MD-a: MD-T1 ‖ MD-T2 ‖ MD-T3 (disjoint files). Wave MD-b: MD-T4 ‖ MD-T5 ‖ MD-T6. Then MD-T7.
- Worktrees branch from a stale base: every brief starts with `git reset --hard improve/roadmap-v1`.
  Agents in worktrees cannot edit the main `AGENT_NOTES.md`; they write notes to the scratchpad and the supervisor merges.
- Wave 1: M1-T1 ‖ M1-T2 ‖ M1-T3 (disjoint files). T3's worktree needs a junction to the git-ignored `tools/freerouting`.
- Wave 2: M2-T1 ‖ M3-T1 ‖ M4-T1
- Wave 3: M2-T2 ‖ M3-T2 ‖ M3-T3
- Wave 4: M4-T2 → M4-T3 (sequential; both touch docs)

## 5. Risks & decisions needing the user
- **D6 (open)** reflex-machine: 74HC595 U3's only decoupling cap C13 is 36.5 mm away (§D-K, emc DC-002) - a real design defect. Fixing it means moving C13 and rebuilding a signed-off board with `--force`. Asked the user whether the board has already been ordered.
- **D1** M1-T3 changes what uno-toggle/reflex-machine *would* produce on their next rebuild (silk text 0.7→0.9 mm, reflex GND-seed fix). Not rebuilt now - verified only by scratch-copy diff + `check`. OK?
- **D2** Untrack the volatile check outputs `projects/*/out/{drc.json,erc.json,netlist.net}` (git index only; files stay on disk). OK?
- **D3** M4-T3 deletes/moves files (duplicate renders, `CODES/` move, `skidl_REPL.*`) and drops `konnect` from `.mcp.json` unless you plan to install it.
- **D4** M3-T1 makes the server refuse actions pointing outside the repo - any custom action you rely on elsewhere?
- **D5** Public repo → GitHub Actions minutes are free. Add CI?
- Deferred, needs your call later: three.js r160 → current (major upgrade); reflex-machine pre-fab items (magnet current, ESP32 pitch, 0.489 mm hole gap) need physical measurement or a sanctioned rebuild.
- Risk: worktree builds need KiCad + Freerouting outside git; agents link them in rather than copy.
