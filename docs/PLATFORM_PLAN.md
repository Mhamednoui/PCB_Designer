# PCB Platform - master plan

Written for: the owner (decisions, priorities) and every agent working on this repo (what to build, how
to know it is right). `ROADMAP.md` is the *execution tracker*; this file is the *plan* it executes.
Evidence behind every claim: `AGENT_NOTES.md`. Status date: 2026-10-27.

---

## 1. Mission and scope

**Mission:** from a written brief, produce a board design and a manufacturing package that an expert
reviewer would sign off - and *prove* it, so nobody has to trust it on faith.

**"Fab-ready" means, concretely** - every board the platform releases has:
1. A design that meets its brief (functions, interfaces, power budget) - verified, not asserted.
2. Every part real, orderable, and pinout-verified against its datasheet with recorded evidence.
3. A layout that passes the target fab's real limits, carries its declared currents, and keeps
   critical circuits (decoupling, regulators, USB, crystals, antennas) laid out per datasheet guidance.
4. Fab files whose connectivity is re-derived from the gerbers themselves and matches the design.
5. For assembled boards: a BOM/CPL the assembler places correctly (stock, package, rotation).
6. One sign-off report listing every check, its result, every waiver with its reason, and the git hash.

**In scope (defaults - owner may change):**
- 2 and 4 layers, FR-4 1.6 mm, 1 oz (2 oz option), JLCPCB first, PCBWay second.
- Assembly per board: `pcba` (JLCPCB assembles SMD, LCSC parts) or `hand` (through-hole, owner solders).
- Digital/mixed boards: MCUs (ESP32 modules, AVR, RP2040, STM32), USB 2.0 FS/HS, I2C/SPI/UART sensors,
  linear + module/buck regulators, motor/solenoid drivers, LEDs, buttons, connectors. Up to ~300 parts.
**Out of scope (explicitly, so nobody assumes it works):** mains voltage / creepage-critical designs,
RF design beyond pre-certified modules, controlled impedance beyond USB 2.0, high-speed (>100 MHz
edges, DDR, PCIe), flex/rigid-flex, BGA. A brief requiring these must be refused or escalated.

---

## 2. Architecture (the lifecycle every board goes through)

```
brief ──► architecture ──► parts ──► circuit ──► verify design ──► layout ──► verify layout ──► fab package ──► sign-off
 (A)         (B)            (C)        (D)           (E)             (F)          (G)              (H)            (I)
```

| Stage | Input → output | Owner today | Gap |
|---|---|---|---|
| A Brief | conversation → `DESIGN_BRIEF.md` | prompt | no structured schema (power budget, interfaces, mechanics, assembly mode) |
| B Architecture | brief → block diagram, power tree, interface/level map | prompt | not written down as data → nothing can check it |
| C Parts | blocks → real parts (MPN/LCSC, symbol, footprint, 3D) | prompt + `sym_pins.py` | **no part registry, no pinout evidence, no package/geometry check, no stock check** |
| D Circuit | parts → `netlist.py` (single source of truth) | prompt | flat netlist; no reusable verified sub-circuits; no hierarchy |
| E Verify design | netlist → pass/fail | `lint`, `sch-check` (ERC + netlist compare), `spice`, `pinmap` | no ratings/level check, no power budget, no strap-pin/open-drain/ESD rules |
| F Layout | netlist → placed + routed board | `pcb.py` + hand `placements()` + Freerouting | **hand coordinates don't scale**; no layout templates for critical circuits; no diff pairs; no keepouts |
| G Verify layout | board → pass/fail | `check` (DRC + JLCPCB + current rules), `review`, `lvs` | no 3D/mechanical collision, no antenna keepout check, no CPL visual check |
| H Fab package | board → gerbers/drill/BOM/CPL/STEP/docs | `outputs`, `fabreport`, `connections` | BOM/CPL not PCBA-grade (rotation DB, LCSC validation); no assembly drawing; no release versioning |
| I Sign-off | all results → release | none | **no single report, no frozen release folder, no rev/hash on silkscreen** |

**Principles (apply to every task):**
1. **Single source of truth.** `netlist.py` (+ registry + blocks) defines intent; everything else is generated.
2. **Defence in depth.** Every error class that can reach fabrication is caught by ≥2 *independent*
   mechanisms where possible (e.g. connectivity: netlist compare AND gerber LVS).
3. **Derive, never restate.** Layers, nets, parts, limits are read from the design or the registry.
4. **Fail loudly.** A check that cannot judge something says WARN with the reason - never a silent pass.
5. **Every check ships with:** a rule id, a doc line, a fixture where it passes, a mutation where it
   fails, waiver support, and a runtime budget.
6. **Waivers, not silence.** Accepted exceptions live in `projects/<id>/waivers.json` with a reason;
   unused waivers are reported.
7. **Blocks are the scaling unit.** Complex boards are composed from verified sub-circuits that carry
   their own rules and layout templates - not written from scratch each time.

---

## 3. Hidden and unpredicted failure modes (risk register)

Ranked by (likelihood × cost if it reaches a manufactured board). "Gate" = what catches it today / planned.

| # | Failure mode | Why it hides | Gate today | Planned gate |
|---|---|---|---|---|
| R1 | **Library pinout ≠ the real part** (SOT-23 BCE vs EBC, LDO tab variants AMS1117/LM1117, USB-C pad numbering, module footprints) | every check compares design to *itself*; LVS trusts pad numbers | none | part registry with datasheet-verified pin map + evidence (P1) |
| R2 | **AI-written netlist uses a hallucinated part, pin name or value** | looks plausible, may even pass ERC | `sch-check` for non-existent pins only | registry is the only allowed part source; values range-checked by rules (P1, P2) |
| R3 | **Footprint geometry ≠ real package** (pitch, body, THT hole vs lead diameter) | DRC checks against the footprint, not the part | none | compare with LCSC/EasyEDA geometry; hole ≥ lead + 0.2 mm (P1) |
| R4 | **CPL rotation/origin offsets** - JLCPCB places parts rotated or shifted | file is "valid"; error only visible at assembly | none | rotation/offset DB per package + rendered CPL overlay check (P5) |
| R5 | **Voltage on a pin above its rating / level mismatch** (5 V into 3.3 V GPIO) | ERC has no voltages | none (lint knows net voltages, not pin ratings) | ratings check: NET_SPEC × registry pin abs-max (P2) |
| R6 | **Undersized copper for current** | DRC defaults only | `check` current rules (MD-T2, refining) | + pour-neck measurement, via current (P4) |
| R7 | **Critical layout wrong**: decap far from pin, regulator hot loop, crystal traces long, USB pair unmatched, antenna over copper | autorouter + placement don't know datasheet layout guides | `review` DC-001/002 (distance only) | layout templates per block + keepout/length checks (P3, P4) |
| R8 | **Strapping / boot / reset pins wrong** (ESP32 GPIO0/45/46, EN RC, AVR RESET pull-up) | electrically "fine", board doesn't boot | none | per-MCU block rules (P3) |
| R9 | **Open-drain bus without pull-ups, floating CMOS inputs, unused pins** | ERC can't know | partial (review "partial") | P2 rules using registry pin types |
| R10 | **Missing protection on external connectors** (ESD, reverse polarity, fuse, inrush) | the board works on the bench | none | P2 rule: every external connector net classified + protection required or waived |
| R11 | **Thermal**: LDO dissipation (Vin−Vout)·I, resistor power, MOSFET Rds·I² | parts survive short tests | none | power budget + per-part dissipation vs rating (P2) |
| R12 | **Mechanical**: connector not at edge, part heights, mounting holes vs enclosure, 3D collisions | 2D DRC passes | courtyards only | STEP collision + edge/height rules from brief (P4) |
| R13 | **Stale artifacts**: fab zip older than board; schematic older than netlist | files look normal | `fabreport` drill cross-check; `lvs` | release step refuses unless every artifact hash chains to one git commit (P5) |
| R14 | **Stock/cost drift** between design and order; extended-part fees | BOM valid on day 1 | none | BOM freeze snapshot + re-check at order time (P5) |
| R15 | **Autorouter nondeterminism / failure on complex boards** | works on small fixtures | DRC unconnected=0 | routing strategy with pre-routes, layer escalation, recorded router version/seed (P4) |
| R16 | **KiCad upgrade breaks scripts** (SWIG `pcbnew` API is being replaced by the IPC API in newer KiCad) | silent behaviour changes | `kicad_paths.py` picks newest install | pin KiCad version; isolate pcbnew calls in `pcb.py`; regression suite before any upgrade (P7) |
| R17 | **A check silently checks nothing** (rule disabled in `.kicad_pro`, filter matches nothing, wrong file) | "0 violations" looks like success | partly (M1 honest exits) | mutation suite proves each check fires; report counts of items *examined* (P6) |
| R18 | **Fab-specific rules wrong or outdated** (JLCPCB changes capabilities) | numbers copied once | `fab_rules.py` constants | fab profile files with source URL + date; reviewed quarterly (P5) |
| R19 | **Third-party library licences in a public repo** (e.g. arduino-kicad-library footprints in `projects/*/lib`) | nobody checks | none | licence inventory of every vendored file (P7) |
| R20 | **Secrets in the public repo** (Wokwi token, future distributor API keys) | one careless commit | `.gitignore`, manual scan | pre-commit secret scan in CI (P7) |
| R21 | **Windows-specific traps** (heredoc backslash corruption, CRLF, PowerShell BOM) | invisible corruption | lessons file | CI on Windows + control-char scan in tests (P6) |
| R22 | **Silkscreen/assembly ambiguity** (polarity marks missing, refs hidden) for hand assembly | DRC doesn't care | silk warnings only | polarity-mark rule + assembly drawing (P5) |

---

## 4. Verification matrix (target state)

Every error class, its primary and secondary independent gate, and the mutation test that proves it.

| Class | Primary | Secondary | Mutation |
|---|---|---|---|
| non-existent pin | `sch-check` netlist compare | `lint` pads | M-pin |
| valid pins swapped | `spice` (analog) / registry pin roles | `review` | M-swap |
| wrong pinout in library | registry pin-map evidence | LVS can't - human sign-off line in report | M-libpin |
| wrong footprint / package | `lint` pads + registry package | footprint geometry check | M-fp |
| net split (typo) | `lint` single-pin | ERC promoted | M-split |
| nets merged / short | `lint` led/short | `spice`, `lvs` | M-merge |
| missing decoupling | `lint` decoupling | `review` DC-002 | M-decap |
| decap too far | `review` DC-001/002 | placement constraint check | M-decap-far |
| polarity reversed | `lint` polarity / led | `spice` reverse current | M-pol |
| over-voltage on pin | ratings check (P2) | - | M-volt |
| over-current track | `check` current rules | `fabreport` pour report | M-width |
| fab limit violated | `check` JLCPCB rules | `fabreport` | M-hole |
| board/part off outline | `check` | `fabreport` outline | M-edge |
| copper open / short in gerbers | `lvs` | `check` unconnected | M-cut, M-bridge |
| firmware ≠ board pins | `pinmap` | Wokwi diagram diff | M-fw |
| strap/boot pin wrong | block rule (P3) | - | M-strap |
| missing pull-up on open-drain | rule (P2) | `review` | M-pullup |
| CPL rotated | rotation DB (P5) | rendered overlay | M-cpl |
| stale fab files | release hash chain (P5) | `fabreport` drill count | M-stale |
| check disabled/suppressed | mutation suite itself | report "items examined" | M-disabled |

**Metric:** catch rate = mutations caught ÷ mutations defined. Target 100%; a new error class is not
"supported" until it has a row here and a mutation.

---

## 5. Phases (each with entry + exit criteria)

### P0 Foundations - honest, independent gates  *(in progress, ~80%)*
Done: honest exits (M1), shared generator (M1-T3), `lint` (MD-T1), JLCPCB + current DRC (MD-T2),
SPICE LED asserts (MD-T3), `review` (MD-T5), gerber `lvs` (MD-T6).
In flight: MD-T2b current rules vs pours/copper weight, MD-T4 ERC promotion + generic `pinmap`,
MD-T8 decap placement on fixtures.
Remaining: **MD-T7 mutation suite** (all §4 rows that P0 covers) + a `release` stage stub that runs every gate.
**Exit:** all 3 fixtures green end-to-end; mutation catch rate 100% for P0 classes; runtime budget
small board <60 s, reflex <3 min.

### P1 Part & library integrity  *(the biggest hidden risk, R1-R3)*
- **Part registry** `parts/` (repo-level, shared by all projects): one record per MPN:
  LCSC id, manufacturer, package, KiCad symbol + footprint + 3D, **pin map verified against the
  datasheet** (pin number → function, with datasheet URL, page, date, verifier), pin electrical
  ratings (abs-max V per pin class, I max), power rating, temperature range, THT lead diameter,
  polarity/pin-1 convention, lifecycle.
- `netlist.py` parts reference registry ids; free-form parts become a lint ERROR (waivable for
  connectors/mechanical).
- Checks: symbol pins == registry pins; footprint pads == registry pads; pad geometry vs LCSC/EasyEDA
  footprint (pitch, pad size, hole vs lead); stock + basic/extended + price cached with date.
- Tooling: `easyeda2kicad` import, `datasheets` skill extraction as *assist*, never as sole evidence.
**Exit:** every part on the 3 fixtures + the reference board has a verified registry record; M-libpin,
M-fp, M-volt mutations caught.

### P2 Electrical rules engine
Generalise `lint` into a rule engine (rule id, severity, doc, waiver, fixture, mutation):
ratings (NET_SPEC × pin abs-max), level mismatch, open-drain pull-ups, floating/unused inputs,
external-connector protection (ESD, reverse polarity, fuse), power budget (sum of loads per rail vs
regulator rating, fuse), thermal dissipation per part (LDO, resistors, MOSFETs).
**Exit:** rules documented in `docs/RULES.md`; each has fixture + mutation; 0 false positives on fixtures without waiver.

### P3 Verified design blocks  *(the scaling unit)*
`blocks/<name>.py`: parameterised sub-circuit → netlist fragment + block rules + **layout template**
(relative placement, pre-routes, keepouts, length/width constraints) + SPICE test where analog + doc.
First set (driven by the reference board): power input (connector + fuse + reverse protection + TVS),
LDO 3V3, buck module, USB-C power-only and USB-C 2.0 data (CC resistors, ESD, 90 Ω pair), ESP32-S3
module minimal system (EN RC, boot strap, antenna keepout), AVR minimal, low-side MOSFET + flyback,
button + debounce, LED indicator, I2C header + pull-ups, crystal.
Hierarchical `netlist.py`: blocks instantiated with ref/net prefixes; multi-sheet schematic per block.
**Exit:** reference board composed ≥80% from blocks; each block has its own mini fixture passing all gates.

### P4 Layout engine for complex boards
Constraint-based placement (block templates placed as units; connectors on declared edges; courtyard-
aware packing; proximity constraints e.g. decap ≤3 mm, crystal ≤5 mm); routing strategy (templates
pre-route critical nets → pours for power/GND → Freerouting for the rest → layer escalation 2→4 on
failure); USB diff pair from template with impedance calc; antenna/keepout zones checked; via current;
fiducials + tooling for PCBA; mechanical rules from the brief (outline, mounting, edge connectors,
max height) + STEP collision check; rev + git hash on silkscreen.
**Exit:** a 100-150-part SMD board places+routes with 0/0/0 and all P0-P2 gates green, untouched by hand.

### P5 Manufacturing package & sign-off
PCBA-grade BOM + CPL (JLCPCB columns, rotation/offset DB, assembly side, basic/extended); rendered
CPL overlay (pin-1 marker vs footprint) for review; assembly drawing PDF (polarity marks) for hand
boards; fab profiles (`fab_profiles/jlcpcb.json`, `pcbway.json`) with source + date; **`release` stage**:
refuses unless every gate is green and every artifact hash chains to one commit, writes
`releases/<id>/rev-X/` + `SIGNOFF.html` (all results, waivers, open human-check items).
**Exit:** reference board release package passes JLCPCB upload preview with no warnings (manual
one-time verification by the owner) and the sign-off report is complete.

### P6 Proof & regression
Fixture ladder: small THT (blinky), shield (uno-toggle), dense THT (reflex), **reference PCBA board
`ref-esp32`** (ESP32-S3 module, USB-C power+data, LDO, ESD, I2C sensor, LEDs, buttons, 4-layer or
2-layer per routing result). Mutation suite covering all §4 rows; CI (non-KiCad subset on GitHub,
full suite locally); performance budgets tracked.
**Exit:** catch rate 100%; ref-esp32 released; old projects rebuilt green.

### P7 Platform hygiene  *(continuous, low effort, never blocks P0-P6)*
`doctor.py` + bootstrap (Freerouting, pinned KiCad, requirements), docs refresh, CLAUDE.md slimming,
KiCad version pin + upgrade procedure, licence inventory (R19), secret scan (R20), webview security
backlog (CSRF/actions), workspace cleanup.

---

## 6. Order and dependencies
P0 → P1 → P2 → P3 → P4 → P5 → P6, with P7 trickling alongside.
Why this order: P1 removes the risk no other check can see (wrong library pinout) and gives P2 its
data (pin ratings); P3 needs P1 parts and P2 rules; P4 needs P3 templates; P5 needs a real layout; P6
proves everything. The reference board's brief (P6) is written at the start of P1 so every phase is
driven by a concrete complex target, not by the fixtures alone.

## 7. Assumptions (defaults chosen; owner may override any)
- A1 Fab: JLCPCB primary; numbers from their capabilities page, re-verified each P5 release.
- A2 KiCad pinned at 10.0.x until P6 passes on a newer version.
- A3 Reference board: ESP32-S3 *module* (pre-certified RF), not a bare chip.
- A4 One human sign-off line remains in every release: "pinouts of parts marked NEW in the registry
  checked against datasheet by a person" - automation reduces, never removes, this step for new parts.
  Reconciled with registry §9.1 (2026-10-28): a release *package* may be generated while parts are only
  `crosschecked`; they are listed as OPEN human-check items and the release is **not signed off** until the
  owner has raised each to `verified`.
- A5 Fixtures may be rebuilt freely; they are tests, not products.

## 8. How progress is measured
- Catch rate (§4) and number of error classes covered.
- Fraction of reference-board parts with verified registry records.
- Fraction of reference board built from blocks; hand-placed coordinates remaining (target 0).
- End-to-end runtime per fixture.
- Open risk-register rows without a gate.

---

## 9. Independent verification strategy (decided 2026-10-27)

**Principle: no single tool's opinion is trusted.** Every property that can reach fabrication is checked by
engines that share no code. KiCad ERC/DRC remain, but as one voice among several.

| Layer | What it proves | Engine (independent of KiCad?) | Phase |
|---|---|---|---|
| `lint` | structural design rules on `netlist.py` | own Python - yes | P0 ✅ |
| **Electrical static analyzer** | every pin within its registry abs-max; no output-vs-output contention; no floating CMOS input; open-drain nets pulled up; per-rail current budget; regulator/resistor/MOSFET dissipation; level mismatches | own Python graph engine (networkx-style voltage/current propagation over nets, regulators, dividers, pin classes from the registry) - yes | **P2 core** |
| **Executable requirements** | the board does what the brief asked: `REQUIREMENTS` in `netlist.py` (graph-path, "through part class", voltage, current, simulated behaviour) | own Python + LTspice - yes | **P2** |
| SPICE | analog behaviour, LED currents, timing | LTspice - yes | P0 ✅ |
| `sch-check` | schematic == netlist.py | KiCad netlist export + own diff - partial | P0 ✅ |
| `check` DRC | fab limits, current widths, decap distance | KiCad DRC + own decap check - partial | P0 ✅ |
| **Gerber DRC (`fabcheck`)** | clearance, annular ring, hole-to-hole, copper-to-edge, min width - measured on the fab files | own shapely geometry (reuses `lvs`) - yes | **P5** |
| `lvs` | fab-file connectivity == netlist.py | own gerbonara/shapely - yes | P0 ✅ |
| **IPC-D-356 for fab e-test** | the *physical* bare board matches our netlist (flying probe at the fab) | the fab's tester - yes | **P5** |
| `parts` + registry | parts real, pinouts crosschecked vs datasheet, geometry vs LCSC | LCSC/EasyEDA/datasheet - yes | P1 |
| **Generator fuzzing** | random valid netlists → pipeline fails correctly or yields DRC+LVS-clean boards | Hypothesis (property-based) - yes | **P6** |
| Mutation suite | each gate actually fires | own harness | P0 ✅ |
| **AI design review** | "second engineer" read of datasheets vs netlist | LLM agent - advisory only | P6 |

**Why not a machine-learning classifier as a gate:** it outputs probabilities, there is no labelled corpus of
PCB wiring defects to train on, and its errors are unexplainable. A 98 %-accurate gate ships 1 bad board in
50 with a green light. ML/LLM is used where it is strong - *finding* candidate problems (design review,
datasheet extraction) - and **every confirmed finding is converted into a deterministic rule + mutation**,
so the platform's guarantees only ever come from checks that are exact, explainable and tested.

---

## 10. Architecture for scale (decided 2026-10-27) - phase **PA**, runs between P1 and P2

Scaling axes and the change each needs:
- **More checks/features** → stages declare themselves (name, order, applies-when, interpreter, inputs, outputs)
  in a stage registry; `pipeline.py` becomes a generic runner. A new feature = a new file, no core edit.
- **Every stage re-parses netlist.py / KiCad files on its own** → one **design IR** (`out/design.json`): parts
  (registry id, pins by function → pad), nets (NET_SPEC v/i, class), board (layers, stackup, outline, zones,
  pads, holes), requirements, assembly mode, fab profile. Built once by an `ir` stage; every checker reads the
  IR. KiCad API calls are confined to adapters (`ir_from_kicad.py`) - the R16 (KiCad API change) firewall.
- **Bigger boards / more checks = slower runs** → incremental execution: each stage's inputs are hashed;
  unchanged inputs skip the stage (`--no-cache` forces). Mutation suite runs in parallel workers, with a
  fast tier (<60 s, every change) and a full tier (before release).
- **More layers** → audit `pcb.py` for any hard-coded F_Cu/B_Cu (pours, stitching, fan-out, keepouts) and
  make them layer-list driven from the stackup; 4-layer plane assignment from NET_SPEC (MS-T2).
- **More rules** → P2 rule engine: each rule a registered function with id, severity, doc, fixture, mutation;
  `docs/RULES.md` generated from the registry of rules.
- **More fabs** → fab profiles as data (`fab_profiles/*.json`, P5).

| ID | Task | Effort | Deps |
|---|---|---|---|
| PA-1 | Design IR schema + `ir` stage (`ir_from_netlist` + `ir_from_kicad` adapters); IR validated against a JSON Schema | high | P1-T9 |
| PA-2 | Stage registry + generic runner; incremental (input-hash) caching; existing stages declared, behaviour identical | high | - |
| PA-3 | Port `lint`, `parts`, `decap_check`, `lvs` to read the IR (one at a time; outputs must be byte-identical) | medium | PA-1 |
| PA-4 | Layer-agnostic audit of `pcb.py` + 4-layer fixture (blinky-4L) through the full pipeline | high | MD-T11 |
| PA-5 | Parallel + tiered mutation runner | medium | - |
**Exit:** adding a new check touches only its own file + its mutation entries; blinky-4L green; fast-tier suite <60 s.

---

## 11. Engineering standards - error-proof, debuggable, extensible (decided 2026-10-27)

### 11.1 Error-proof (defects can't get in, or can't get out)
- **Every guarantee has a test that breaks it** (mutation suite). A check without a mutation is not "supported".
- **Fail closed:** unknown input, missing data, offline source, zero items examined → WARN with reason or FAIL; never PASS.
- **Two independent engines** for anything that reaches the fab (§9).
- **Single source of truth + generated everything else**; hand edits of generated files are detected (hash in IR) and refused.
- **Schemas everywhere:** netlist IR, parts records, waivers, mutations, stage registry, fab profiles - all JSON-Schema validated on load.
- **Pre-commit + CI gate:** Python syntax/lint (ruff), JSON schema validation, fast-tier mutation suite, secret scan, control-char scan (LESSONS 14).

### 11.2 Easy to debug
- **One run report per pipeline run** (`out/run/<timestamp>/report.json` + `report.html`): every stage's inputs (with hashes),
  command, exit code, duration, counts examined/passed/failed/waived, findings with rule id + location, tool versions
  (KiCad, Freerouting, LTspice, Python, git commit). Any failure is reproducible from the report alone.
- **Error taxonomy:** every finding = `RULE-ID | severity | where (ref/pin/net/x,y/layer) | what was measured vs limit |
  why it matters | how to fix | doc link`. No bare stack traces for expected failures; real exceptions keep full traces.
- **`--explain <RULE-ID>`** prints the rule's doc, its mutation, and an example fix.
- **Visual debugging:** findings with coordinates are rendered as markers on the board image (and in the webview).
- **Determinism:** same inputs → same outputs (sorted output, fixed timestamps in generated files, Freerouting version
  logged); nondeterministic tools are retried and their attempt log kept.

### 11.3 Easy to add features
- **Extension points, each with a template + scaffold command + doc page:**
  stage (`stages/<name>.py` + registry entry), rule (`rules/<id>.py`), part (`parts new`), design block (`blocks/<name>.py`),
  fab profile (`fab_profiles/<fab>.json`), mutation (`mutations.json` entry).
  `python pipeline.py --scaffold rule MY-RULE` creates the file, the doc stub and a failing mutation to fill in.
- **`docs/CONTRIBUTING.md`:** "how to add X" for every extension point, with the definition of done:
  code + schema + doc + fixture pass + mutation fail + run-report fields + CHANGELOG line.
- **Architecture Decision Records** (`docs/adr/NNNN-title.md`): every decision made in this plan (registry tiers, pins-by-function,
  no ML gate, IR, strangler re-architecture, ...) recorded with context, decision, consequences - so a new contributor (human
  or agent) knows *why*, not just *what*.
- **Versioning:** the platform has a version (semver) and a CHANGELOG; every board release records the platform version and
  the git commit that produced it.

### 11.4 Tasks (phase PA, alongside §10)
| ID | Task | Effort |
|---|---|---|
| PA-6 | Run report (json+html) + tool-version capture + determinism pass on generated files | high |
| PA-7 | Finding/error taxonomy object used by every checker; `--explain`; findings → board markers | medium |
| PA-8 | Scaffold commands + templates for stage/rule/part/block/fab-profile/mutation; `docs/CONTRIBUTING.md` | medium |
| PA-9 | Pre-commit + GitHub CI (ruff, schema validation, fast-tier mutations, secret + control-char scan) | medium |
| PA-10 | `docs/adr/` with the decisions taken so far; CHANGELOG + platform version | low |
**PA exit (with §10):** a new check is added by scaffold → fill → its mutation flips to CAUGHT, touching no core file;
every failing run can be diagnosed from its run report alone.

### 10.1 Design entry points (decided 2026-10-27)
The design IR has **input adapters**; everything downstream is source-agnostic.
- `netlist.py` (scripted/AI-written) - today's path.
- **KiCad schematic drawn by a person** (`SOURCE = "schematic"`): `kicad-cli sch export netlist` → `ir_from_kicad_sch`.
  Electrical intent and identity come from symbol fields: `Registry` (registry id) or `LCSC`, `Net voltage`/`Net current`
  on a net-label or power symbol (or a sidecar `projects/<id>/intent.json`). Missing intent **fails closed**
  ("VBUS: no current declared") - the checks never assume.
- Any other EDA tool via a KiCad-importable netlist (same adapter).
- **One source of truth per project:** a project declares exactly one `SOURCE`; the generator never overwrites a
  hand-drawn schematic, and a hand-edited generated schematic is detected (IR hash) and refused.
- Placement for drawn schematics comes from the P4 auto-placer (no coordinates needed).

| ID | Task | Effort | Deps |
|---|---|---|---|
| PA-11 | `ir_from_kicad_sch` adapter + symbol-field/intent conventions + a hand-drawn fixture (redraw blinky by hand in KiCad, must produce an IR equivalent to blinky's `netlist.py` IR) | high | PA-1 |
