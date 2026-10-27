# P1 design spike: the parts registry

Status: proposal for supervisor decision, 2026-10-27. Scope: PLATFORM_PLAN section 5 P1 (risks R1 wrong pinout,
R2 hallucinated part, R3 wrong footprint geometry, R14 stock drift, R18 stale fab numbers).
"(verified)" = run or fetched during this spike. Numbers marked "illustrative" were NOT read from a PDF.

## 0. Decisions in one screen
1. **JSON, one file per record**, `parts/records/<id>.json`, committed. Stdlib-only, so `lint` (system Python, <1 s) can read it.
2. **Machine data is cached, not committed** (`parts/.cache/`, gitignored). A record holds what a human signed plus a small
   sourcing snapshot. A hash over the signed fields makes silent edits visible.
3. **Key = our `id`** (slug of MPN + package), tied to an LCSC id. Never resolve a part by free-text MPN search (section 5).
4. `netlist.py` keeps its exact `PARTS` dict shape. `part()` takes a registry id and derives `lib_id/footprint/lcsc` from it,
   so `make_sch`, `make_pcb`, `make_outputs` are untouched.
5. Four record kinds: `part` (orderable, datasheet-signed), `generic` (R/C/LED families), `connector`, `mechanical`.
6. Everything needing the network lives in a new `parts` stage. `lint` stays offline.

## 1. Schema
Provenance is a property of the section; `evidence[]` records who checked what.

| Section | Fields | Filled by |
|---|---|---|
| identity | `id`, `kind`, `mpn`, `manufacturer`, `status` (`draft`/`verified`/`obsolete`) | MPN, maker: machine (EasyEDA JSON `Manufacturer Part`; maker string comes back mojibake, normalise). `id`, `status`: tool |
| sourcing | `lcsc.id`, `lcsc.class` (`basic`/`preferred`/`extended`), `stock`, `price_1`, `snapshot_date`, `lifecycle` | machine (jlcsearch). `lifecycle` (active/NRND/EOL): human or distributor skill |
| package | `name`, `mount` (tht/smd), `lcsc_package`, `body_mm` | name: human. `lcsc_package`, `body_mm`: machine |
| kicad | `symbol`, `footprint`, `model3d`, `fp_pad_copies` | human picks, tool suggests; STEP from easyeda2kicad optional |
| pins | per pad number: `name`, `alias`, `class`, `abs_max` {`v_min`,`v_max`,`i_ma`} | names: machine draft, human-verified. **class and abs_max: human/datasheet only** (EasyEDA exports every pin as `unspecified`, verified) |
| ratings | `v_op`, `i_max`, `p_max_mw`, `t_op_c` | machine draft from LCSC description, human confirms |
| tht | `lead_d_mm` (round) or `lead_mm` [w,t] (rect) | **human/datasheet only** (no machine source exists) |
| polarity | `polarised`, `pin1` text, `pin1_footprint_marker` | human; checked against footprint pad-1 shape |
| evidence | `[{section, doc_url, page, rev, method, verified_by, date, notes}]`, `signed_hash` | human via `parts sign`; hash tool-written |

`v_max` may be relative, e.g. `"pin:8+0.3"` (input limit VCC + 0.3 V). `fp_pad_copies` records duplicated pad names:
KiCad `SOT-223-3_TabPin2` has TWO pads named "2" (2.0x1.5 mm and the 2.0x3.8 mm tab; verified) and `lint_netlist.footprint_pads()`
returns a set, so it collapses them today. Registry checks must use a multiset. `signed_hash` = sha256 over
mpn, package, kicad, pins, tht, polarity. Editing those without re-signing is `PR-HASH` (error); sourcing drift never breaks a signature.

**Example 1: NE555P (THT).** `//` notes are not valid JSON, shown for the reader.
```json
{"id":"ne555p-dip8","kind":"part","mpn":"NE555P","manufacturer":"Texas Instruments","status":"verified",
 "lcsc":{"id":"C46749","class":"extended"},
 "sourcing":{"stock":34636,"price_1":0.3039,"snapshot_date":"2026-10-27"},
 "package":{"name":"DIP-8","mount":"tht","lcsc_package":"DIP-8","body_mm":[9.8,6.6,3.5]},
 "kicad":{"symbol":"Timer:NE555P","footprint":"Package_DIP:DIP-8_W7.62mm"},
 "tht":{"lead_mm":[0.5,0.25]},                     // illustrative; diagonal 0.56 + 0.2 <= drill 0.8
 "polarity":{"polarised":true,"pin1":"notch on top, pin 1 left of notch","pin1_footprint_marker":"square pad"},
 "ratings":{"v_op":[4.5,16],"t_op_c":[0,70]},      // machine: LCSC text "4.5V~16V, 0~70C"
 "pins":{"1":{"name":"GND","class":"power_in"},
   "2":{"name":"TRIG","class":"input","abs_max":{"v_min":-0.3,"v_max":"pin:8+0.3"}},     // illustrative
   "3":{"name":"OUT","class":"output","abs_max":{"i_ma":225}},                           // illustrative
   "4":{"name":"RESET","alias":"~RST","class":"input"},"5":{"name":"CONT","class":"analog"},
   "6":{"name":"THRES","class":"input"},"7":{"name":"DISCH","class":"open_collector"},
   "8":{"name":"VCC","class":"power_in","abs_max":{"v_max":18}}},                        // illustrative
 "evidence":[{"section":"pins,ratings,tht","doc_url":"<TI NE555 datasheet>","page":"<n>","rev":"<letter>",
   "method":"pin table + abs-max table + package drawing","verified_by":"<name>","date":"<date>"}],
 "signed_hash":"<tool>"}
```
Name comparison strips `~{}` and honours `alias` (KiCad `~{RST}` vs datasheet RESET).

**Example 2: AMS1117-3.3 (SOT-223, tab = VOUT).** Sourcing/package/EasyEDA facts are real (2026-10-27); the record is still `draft`.
```json
{"id":"ams1117-3v3-sot223","kind":"part","mpn":"AMS1117-3.3","status":"draft",
 "lcsc":{"id":"C6186","class":"basic"},"sourcing":{"stock":1465063,"price_1":0.2003,"snapshot_date":"2026-10-27"},
 "package":{"name":"SOT-223","mount":"smd","lcsc_package":"SOT-223","body_mm":[6.5,3.5,1.6]},
 "kicad":{"symbol":"Regulator_Linear:AMS1117-3.3","footprint":"Package_TO_SOT_SMD:SOT-223-3_TabPin2","fp_pad_copies":{"2":2}},
 "ratings":{"v_op":[null,15],"i_max":1.0,"t_op_c":[-40,125]},   // from LCSC text "15V 1A", unsigned
 "pins":{"1":{"name":"GND","class":"power_in"},
   "2":{"name":"VOUT","class":"power_out","also":"TAB: two pads '2' in KiCad, pad '4' in EasyEDA"},
   "3":{"name":"VIN","class":"power_in","abs_max":{"v_max":null}}},
 "evidence":[],"signed_hash":null}
```
The trap: the tab is VOUT, not GND, so a GND pour under the tab shorts the regulator output. Only the signed pin table plus
PR-SYM/PR-PAD can see it; ERC and LVS trust the pad numbers. Variants (LM1117, AP1117, SOT-23 LDOs) differ per MPN, so records are per MPN, never per package.
A `draft` record is legal in a design but is flagged NEW in the release (section 4).

## 2. How `netlist.py` references parts
```python
part("U1", "ne555p-dip8", "NE555P", {1:"GND", ...}, G)     # value stays: BOM comment + silkscreen
R("R1", "10k", "VCC", "DISCH", G)                           # helper uses generic "res-axial-0207"
```
- New loader `tools/boardgen/parts.py` (`get`, `generic`, validate). `part()` fills `lib_id=rec.kicad.symbol`, `footprint=rec.kicad.footprint`,
  `lcsc=rec.lcsc.id or ""`. The `LCSC = {value: id}` dicts go away: keyed by value they are ambiguous ("100nF" fits dozens of parts).
- Transition: legacy `part(ref, lib_id, value, fp, ...)` still works with `PR-REF` WARN. `PARTS_STRICT = True` (default for new boards, forced after
  fixture migration) makes free-form parts an ERROR, waivable only for `connector`/`mechanical`.
- `generic` records (`res-axial-0207`, `cap-disc-5mm`, `cap-elec-6.3mm`, `led-3mm`, `led-5mm`, DO-41/DO-201/DO-15 diodes) carry pin map, footprint, lead
  size and a value range. Their `orderable_as` map (value to registry `part` id) may be empty on `hand` boards; an unbound generic in a `pcba` release is an ERROR.
- `connector`: pins `1..N`; signed content is pad count, pitch, pin-1 position, mating family, V/A per pin. Evidence method "datasheet drawing vs footprint" (or a 1:1
  print, as still needed for the ESP32 DevKit row pitch). `unverified_dims: ["row_pitch_mm"]` on a record is printed in every release until closed.
- `mechanical` (mounting hole, fiducial, logo) and test points: no pins, `bom:false`, footprint binding + hole check only, no datasheet.
- Module boards (Mega shield, ESP32 DevKit, K7805 module) are `kind:part` with `source:"project-lib"` where the pin map lives in vendored libs: the highest-risk records.

**Migration** (counted from the three `netlist.py`): blinky-555 9 parts / 6 distinct (symbol, footprint) pairs; uno-toggle 9 / 5; reflex-machine 123 / 22.
After dedupe about 25 records: ~10 `part` needing a signature (NE555P, IRLZ44N, 74HC595N, PC817, 1N4007, 1N5822, P6KE15A, K7805-2000R3, Mega shield,
ESP32 DevKit), ~6 `generic`, ~9 `connector`/`mechanical`. Acceptance: a rebuild gives a byte-identical `.kicad_sch` (UUIDs derive from refs).

## 3. Checks the registry enables
Prefix `PR-`. Each gets a doc line, `waivers.json` support, a fixture, the mutation below. Stages: `lint` = offline <1 s; `parts` = new, cache/network, runs right after `lint`; `check` = after layout.

| Rule | Stage | Inputs | Failure message | Mutation |
|---|---|---|---|---|
| PR-REF | lint | PARTS vs registry | `U1: part id "ne555" not in registry (nearest: ne555p-dip8)` | rename an id in netlist.py |
| PR-HASH | lint | record vs `signed_hash` | `ne555p-dip8: signed fields changed since sign-off` | edit a pin name in the JSON |
| PR-SYM | lint | KiCad symbol pins vs `pins` (number, name/alias, class) | `Q1: symbol pin 1 is E, registry (BC547) says C` | M-libpin: swap pin 1/3 names in the BC547 record |
| PR-PAD | lint | footprint pad multiset vs `pins` + `fp_pad_copies`; netlist pins subset | `U2: footprint pads 1,2,3 but registry expects 1,2,2,3` | M-fp: bind U2 to `SOT-223-5` or a TO-92 |
| PR-HOLE | lint | footprint drill vs `tht` lead | `U1: drill 0.80 < lead 0.56 + 0.20` | set lead_mm to [0.9,0.3] |
| PR-PKG-NAME | lint | `package.name` token in footprint name | `footprint name has no "DIP-8"` | set record package to SOT-23 |
| PR-V | lint (P2 engine) | NET_SPEC volts of each net on a pin vs pin `abs_max` (error) and `v_op` (warn) | `A2 pin 25 (ESP32 RX2, abs-max 3.6 V) on net ESP_RX2 up to 5.0 V` | M-volt: remove divider R62/R63 in reflex |
| PR-MPN | parts | cached jlcsearch `mfr` and EasyEDA `Manufacturer Part` vs `mpn` | `C46749 is "NE555P" on LCSC, record says "NE556"` | change `lcsc.id` |
| PR-GEO | parts | KiCad vs EasyEDA footprint: pad count, pitch, row spacing, drill (error >0.15 mm); sizes warn | `U1: pitch 2.54 vs LCSC 2.00` | bind a 2.0 mm pitch record to a 2.54 mm footprint |
| PR-PKG | parts | `lcsc_package` vs jlcsearch `package` (THT strings are Chinese, e.g. `插件,D=3mm`: normalise table; unknown = WARN "not judged") | `LCSC lists SOT-23-3, record says SOT-223` | edit `lcsc_package` |
| PR-STOCK | parts | cached stock and class vs boards x qty x 1.2 | `C6186 stock 12 < need 60`; `class basic to extended` WARN | write cache stock 0 |
| PR-FRESH | parts | `status`, `snapshot_date`, cache ages | `ams1117: draft`; `snapshot 41 days old` | backdate snapshot |
| PR-INST | check | footprints in the finished `.kicad_pcb` vs registry footprint and pads | `U1 on board is DIP-14, registry says DIP-8` | swap a footprint in the PCB |

PR-GEO tolerances come from measured data. NE555P: KiCad DIP-8 drill 0.80 / pad 1.6 vs EasyEDA drill 0.90 / pad 1.5; pitch 2.54 and rows 7.62 identical (pass).
SOT-223: KiCad pads at x=3.15, 2.0x1.5 mm, tab 2.0x3.8 vs EasyEDA x=2.97, 2.5x1.1, tab 2.34x3.6; pitch 2.30 identical (pass). So compare
**pitch, row spacing, pad count, drill**; pad size and offset only warn. Align by pad 1 / centroid first; map the tab through the record's `also` note.
`PR-HOLE` stays in `lint` (no network): KiCad footprint drill vs the signed lead size.

## 4. Verification workflow for a NEW part (`tools/parts.py`)
1. `parts new --lcsc C46749` (automated). Fetch jlcsearch by LCSC id, EasyEDA JSON, run `easyeda2kicad --full` into cache; write a `draft` record
   (identity, sourcing, package, EasyEDA pin names, ratings from LCSC text). Refuse if jlcsearch `mfr` != EasyEDA `Manufacturer Part`.
2. `parts bind --symbol Timer:NE555P --footprint Package_DIP:DIP-8_W7.62mm` (tool suggests candidates by pin count and name). It diffs KiCad pin names vs EasyEDA
   pin names: an independent second source, recorded as method `lib-vs-easyeda`. Not sufficient alone (both can inherit one vendor error).
3. Assist, never sole evidence: `lcsc` skill `fetch_datasheet_lcsc.py` gets the PDF; `datasheets` skill extracts pins, abs-max and package drawing with page numbers;
   `parts assist` diffs that extraction against the draft and prints each disagreement with its page for the human to open.
4. **Human sign-off**: `parts sign <id> --by NAME --doc URL --page N --rev R`, after an interactive tick list: pin table matches page N; abs-max values match; lead size read
   from the drawing; pin-1 marker matches the footprint. Writes `evidence`, `signed_hash`, `status: verified`.
5. Any later edit to a signed field flips the record back to NEW (PR-HASH).

**Release report (plan A4).** The `release` stage lists every registry id used as `VERIFIED` (by, date, datasheet rev), `NEW` (draft or broken hash), or `STALE`, plus all
`unverified_dims`. Any NEW makes the release **"NOT FULLY VERIFIED"** (neither red nor green) and prints the unticked box
`[ ] pinouts of the NEW parts (U1 NE555P, ...) checked against their datasheets by a person`. Automation never ticks it; it is ticked in `SIGNOFF` by the owner.

## 5. Facts confirmed on the web and locally (2026-10-27)
- **jlcsearch** (https://jlcsearch.tscircuit.com, repo https://github.com/tscircuit/jlcsearch; live calls). Endpoints: `/api/search?q=`, `/components/list.json?search=`,
  category lists (`/voltage_regulators/list.json`), `/api/footprinter_strings/{C}`, `/api/easyeda_components/{C}`. Fields: `lcsc` (int, no "C"), `mfr`, `package`, `description`,
  `stock`, `price` (list.json: tiered string `"1-49:0.3039,50-149:0.2371,..."`; /api/search: one float), `category`, `subcategory`, `is_basic`, `is_preferred`.
  **Surprises:** (a) free-text search is unreliable: `q=NE555P`, `q=NE555`, `q=AMS1117-3.3` returned a MOSFET, an FFC connector, fuses. Exact LCSC id works:
  `C46749` = NE555P DIP-8 extended, stock 34636; `C6186` = AMS1117-3.3 SOT-223 basic, stock 1,465,063. So resolve by id and verify `mfr` (PR-MPN).
  (b) The vendored lcsc SKILL.md documents `basic`, `extra.*` and a datasheet PDF URL; the live API returns `is_basic`/`is_preferred`, no datasheet, no `extra`, and `full=true` adds nothing.
  (c) THT package strings are Chinese. (d) No rate limit or SLA is documented; stock syncs nightly 05:00 UTC, EasyEDA cache refreshes after 90 days (repo README).
- **easyeda2kicad geometry is diffable** (`.venv\Scripts\easyeda2kicad.exe --full --lcsc_id=C46749`, verified). The `.kicad_mod` has one line per pad:
  `(pad 1 thru_hole rect (at -3.81 3.81) (size 1.5 1.5) (drill 0.900024))`, plus `.kicad_sym` and STEP/WRL. Caveats: all symbol pins are `unspecified`; footprint `MPN` and
  `Manufacturer` properties are the string `"null"`; `Datasheet` is the LCSC product page, not a PDF; the SOT-223 tab is pad 4 (KiCad: second pad "2").
  `/api/footprinter_strings/C46749` gives a parametric string with copper IoU 0.99999 (a cheap second geometry source). `/api/easyeda_components/C46749` JSON has
  `"JLCPCB Part Class": "Extended Part"`, an authoritative basic/extended flag.
- **JLCPCB fee** (https://jlcpcb.com/help/article/40-pcb-assembly-price, page dated "last updated Oct 22, 2026", read through a fetch summary, re-verify at P5): feeder loading
  Economic PCBA $3.07 for extended, none for basic; **Standard PCBA $1.53 for basic and extended**. TechOverflow
  (https://techoverflow.net/2024/04/09/jlcpcb-pcba-assembly-price-overview/) logs the extended fee dropping from $3 to $1.5 on 2025-12-19. "Preferred extended" is a third class
  (`is_preferred`). Consequence: the registry stores only `class`; the fee belongs in the P5 fab profile with source and date (R18) because it depends on assembly tier.
- **KiCad pinout variants** (KiCad 10.0.6 libs via `tools/sym_pins.py`): one symbol **per MPN**, not generic orderings. `Transistor_BJT:2N3904` is 1=E 2=B 3=C and `BC547` is 1=C 2=B 3=E,
  both on TO-92 pads 1-2-3; SMD `BC847`, `MMBT3904`, `BC807` are 1=B 2=E 3=C on `Package_TO_SOT_SMD:SOT-23`. Installed `Device.kicad_sym` has only `Q_NPN`, `Q_NPN_BRT`...,
  no `Q_NPN_BCE`-style family (older libs had it; flipped SOT-23 pinout report: https://forum.kicad.info/t/sot-23-pin-out-base-and-emitter-are-inverted/41831).
  The footprint cannot reveal the pinout; only a per-MPN record can. That is R1.

## 6. Offline behaviour and staleness (R14)
- Layout: `parts/records/*.json` (committed, authoritative); `parts/.cache/{lcsc,easyeda,datasheets}/<LCSC>/` (gitignored; each entry stores `fetched_at`, source URL, status). Add to `.gitignore`.
- **Offline OK**: `lint` (REF, HASH, SYM, PAD, HOLE, PKG-NAME, V), `check` PR-INST, sch/pcb stages, `parts sign`.
- **Needs cache or network**: the `parts` stage. Cache hit: judged normally. Miss while offline: `WARN not judged (offline, no cache)`, never a pass (principle 4); `release` turns it into a block for `pcba` boards.
- Defaults: geometry/MPN cache older than 90 days = WARN; stock snapshot older than 7 days = release ERROR (`pcba` only); 24 h at order time (P5 re-check). Signatures never expire by age,
  only by hash change or lifecycle `obsolete`. Refresh is explicit (`parts refresh`), so git history shows when sourcing changed. Etiquette: exact-id lookups, 0.5 s between calls.

## 7. Implementation tasks
Parallel groups (disjoint files, max 3): T1 first; then T2, T3, T4; then T5, T6, T7; then T8, T9.

| ID | Task | Files | Effort | Deps | Acceptance |
|---|---|---|---|---|---|
| P1-T1 | Schema + loader (`get`, `generic`, hash, relative `v_max` parser, validation); `part()` registry path | `parts/schema.json`, `tools/boardgen/parts.py` | medium | - | hand-written NE555P loads; bad field error names its path; hash stable across key order |
| P1-T2 | `parts new`/`refresh` + cache layer (jlcsearch, EasyEDA JSON, easyeda2kicad; ages) | `tools/parts.py`, `tools/boardgen/parts_cache.py`, `.gitignore` | medium | T1 | `parts new` for C46749 and C6186 reproduces the section 1 drafts; offline rerun uses cache |
| P1-T3 | `bind`, `assist`, `sign` (KiCad vs EasyEDA symbol diff, datasheets-skill diff, tick-list) | `tools/parts_sign.py` | medium | T1 | sign writes evidence and hash; later edit trips PR-HASH; `assist` flags a deliberately wrong pin |
| P1-T4 | Test fixtures: ~12 curated records (NE555P, AMS1117, 2N3904, BC547, BC847, 2.0 and 2.54 headers, DO-41) + `mutations.json` naming rule and expected message per mutation | `tests/parts/**` | low | T1 | loads; each mutation lists rule id and message; plugs into MD-T7 suite |
| P1-T5 | `lint` rules REF, HASH, SYM, PAD (multiset), HOLE, PKG-NAME; `PARTS_STRICT`; keep FAMILY map as fallback for generics | `tools/boardgen/lint_netlist.py` | medium | T1 | lint output unchanged on fixtures; mutations for those 5 caught; runtime <1 s |
| P1-T6 | `parts` stage: MPN, GEO, PKG, STOCK, FRESH; report `projects/<id>/test/parts/parts.json`; register in `pipeline.py` after `lint` | `tools/boardgen/check_parts.py`, `pipeline.py` | high | T1, T2 | NE555P and AMS1117 pass GEO at the stated tolerances; offline run WARNs "not judged"; MPN/GEO/STOCK mutations caught |
| P1-T7 | Records without datasheet signing: generics, connectors, mechanical (`res-axial-0207`, caps, LEDs, diodes, terminal blocks, headers, mounting hole) | `parts/records/*.json` | medium | T1 | all load; PR-PAD green against their KiCad footprints |
| P1-T8 | Datasheet-signed records for the ~10 real parts incl. modules; agent prepares drafts and `assist` output, **owner signs** | `parts/records/*.json` | high | T2, T3, T7 | all `verified`; ESP32 row pitch left as `unverified_dims`, listed not hidden |
| P1-T9 | Migrate the 3 `netlist.py` to ids with strict mode; PR-INST in `check`; PR-V hook for P2 | `projects/*/gen/netlist.py`, `tools/boardgen/pcb.py` | medium | T5, T6, T7 | `pipeline.py <id> --only lint,sch-check,check` green on all 3 without rebuilding fab outputs; M-libpin, M-fp, M-volt caught (P1 exit) |

## 8. Open questions for the supervisor
1. **Who signs?** Default: the owner signs the ~10 real parts (about 15 min each with `assist`); agents never set `verified` (plan A4).
2. **Generic passives in `pcba` boards**: bind by value at release (`orderable_as`) or demand a real MPN per resistor/cap in netlist.py? Default: bind at release; value-range checks go to P2; the three fixtures are `hand` boards, unaffected.
3. **JSON or YAML?** Default JSON (stdlib for `lint`; PyYAML exists in the venv and system Python but is not guaranteed in KiCad Python). Cost: no comments, notes go in `evidence.notes`.
4. Stock policy: INFO for `hand`, ERROR for `pcba`, margin 20 percent, release snapshot limit 7 days. Confirm.
5. Fix the vendored lcsc SKILL.md (`basic` vs `is_basic`, absent `extra`/datasheet) now or in P7? Default: P7, note it in `docs/LESSONS_LEARNED.md` meanwhile.
6. Vendored project libs (`arduino-library`, `reflex`): keep in `projects/*/lib` with `source:"project-lib"` (default) or move into repo-level `parts/lib`?

## 9. Supervisor decisions (2026-10-27)
1. **Verification tiers** (replaces "owner signs before anything works"):
   `unverified` → `crosschecked` (agent may set ONLY when >=2 independent machine sources agree on every
   pin - KiCad symbol, EasyEDA/LCSC pin names, datasheet page cited by the agent - and `assist` reports 0
   diffs) → `verified` (owner signs). `crosschecked` parts may be released; the sign-off report lists
   every non-`verified` part as an open human-check item (plan A4). Agents never set `verified`.
2. Generic passives on `pcba` boards: bind value → MPN at release (`orderable_as`). Value-range checks → P2.
3. JSON records (stdlib, readable from KiCad Python).
4. Stock policy as proposed: INFO for `hand`, ERROR for `pcba`, 20 % margin, release snapshot <= 7 days old.
5. lcsc SKILL.md correction → P7; the API facts (`is_basic`/`is_preferred`, exact-id lookup only) are recorded in AGENT_NOTES §E now.
6. Project-vendored libs stay in `projects/*/lib`, records carry `source: "project-lib"`.
7. **PR-HOLE margin (decided 2026-10-27, from P1-T7):** round lead: drill ≥ lead_d + 0.20 mm; square lead: drill ≥ diagonal + 0.10 mm
   (IPC practice sizes square leads by diagonal; keeps KiCad's 1.0 mm drill for 0.64 mm header pins legal). Implement in P1-T9.
8. **Fixture fixes folded into P1-T9:** electrolytics (blinky C1, reflex C2/C6) move from `Device:C` to `Device:C_Polarized` so the
   schematic shows +; consumers skip `kind=mechanical` records for BOM/symbols. **P1-T8 must datasheet-crosscheck the K7805-2000R3
   pin order** (1 IN, 2 GND, 3 OUT is only KiCad-RECOM-derived; a swap destroys the module and the Mega) and reconcile its record id.
9. **Pins by FUNCTION, not number (decided 2026-10-27, from P1-T4's M-libpin-swap known-gap):** for registry parts, `netlist.py`
   connects pins by the record's pin NAME/function (`pins={"B": "BASE", "E": "GND", "C": "LED_K"}`); `registry_part` derives the
   pad numbers from the (crosschecked) record. Swapping a part for one with a different pinout then renumbers correctly by
   construction - the wrong-library-pinout class (R1) becomes structurally impossible for registry parts. Numbers stay accepted
   for generics (2-pin passives) and connectors. Ambiguous names (two pins both "GND", NC) resolve by name+index or explicit number.
   Also in P1-T9: `PARTS_RECORDS_DIR` env override in `parts.py` (replaces the test sitecustomize hook) and an explicit
   registered-refs API (replaces lint's monkeypatch). When done, flip M-libpin-swap from `known-gap` to an expected catch/no-op.
