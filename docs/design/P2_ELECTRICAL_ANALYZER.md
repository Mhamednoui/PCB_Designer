# P2 design spike: rule engine, electrical static analyzer (IV-1), executable requirements (IV-2)

Status: proposal, 2026-10-28. Inputs: PLATFORM_PLAN §3 (R5, R8-R11), §4, §5 P2, §9, §10-11; IR schema v1;
`parts/schema.json`; `lint_netlist.py`. No code in this task. Terms: "record" = parts/records/*.json.

## 0. What exists today (the constraints)
- IR v1 gives per part `pins{pad:{name,net,class}}` + `registry` id; per net `v:[min,max]|null`, `i_max`, `class`.
  It does **not** carry `abs_max`, thresholds, regulator data, resistor values, or "external" flags.
- Records carry `pins.*.class` and `pins.*.abs_max{v_min,v_max("pin:16+0.5"),i_ma}` (74HC595 has them, AMS1117 has
  **none**: its notes say "TODO class and abs_max"). `ratings` has `v_op,i_max,p_max_mw,t_op_c` only: no VIH/VIL/VOH/VOL,
  dropout, θJA, Vf, Rds(on). So P2 needs a schema extension (§4.3) as well as code.
- `lint` has hand-rolled `Finding(sev, rule, target, msg, refs, nets)`, rules as plain functions, waivers in
  `waivers.json` matched on (rule, refs, nets), unused waivers WARN. P2 generalises exactly that.

## 1. Rule-engine contract
### 1.1 Registration
`tools/boardgen/rules/<id>.py` (one rule per file; PLATFORM_PLAN §11.3), imported by a registry that scans the package.
```python
@rule(id="EL-ABSMAX", severity="ERROR", needs=("parts","nets","electrical"),   # IR sections; electrical = derived model
      doc="rules/EL-ABSMAX.md", fixture="fixtures/rules/EL-ABSMAX", mutation="M-volt",
      applies=lambda ir: True, tiers={"hand","pcba"})
def check(ctx): ...  # yields Finding; ctx.ir (read-only), ctx.model (§2), ctx.examined(n) , ctx.not_judged(...)
```
- `needs` is enforced: ctx only exposes declared sections (a rule cannot silently read the board). Rules are pure functions
  of the IR (+ model). No file I/O, no KiCad.
- Registry validates at load: id unique and `^[A-Z]{2,4}-[A-Z0-9-]+$`, doc file exists, fixture dir exists, mutation id exists in
  `mutations.json`. A rule missing any of them fails the platform's own self-check (a rule without a mutation is "not supported").
- Rule docs are `docs/rules/<ID>.md` (what, why, datasheet basis, example fix, known limits); `docs/RULES.md` is generated.

### 1.2 Finding object (replaces lint's; PA-7 owns the shared class, so P2-T1 defines it and lint re-exports it)
```
Finding { rule, severity(ERROR|WARN|INFO|NOT_JUDGED), where{ref?,pin?,net?,xy?,layer?},
          measured{value,unit,corner}, limit{value,unit,source}, why, fix, doc, waived{why,by,date}|null }
```
- `measured`/`limit` are numeric and typed so the report can sort and graph them; `corner` = "min|typ|max" (we always report the worst corner).
- `NOT_JUDGED` is a first-class severity (not a WARN string): counted in the run report, never hidden (§4).
- Stable fingerprint = sha1(rule, where, limit.source): used by waivers and by regression diffs between runs.
- Output keeps the legacy one-line format (`ERROR EL-ABSMAX U1.EN: 5.0 V > 3.6 V`) so existing parsers keep working.

### 1.3 Waivers
Same `waivers.json` file and matching as lint; schema-validated. Entry: `{rule, refs|nets|pins, why, by, date, expires?}`.
New: `why` mandatory and >= 20 chars; `expires` optional (expired waiver = ERROR); unused waiver = WARN (as today); a waiver
may demote **only** ERROR->WAIVED, never NOT_JUDGED (missing data is fixed in the record, not waived). `pcba` release lists all waivers in the report.

### 1.4 `--explain`
`python pipeline.py --explain EL-ABSMAX` prints: doc.md, severity/tiers, `needs`, the fixture name, the mutation id and
what it changes, and the registry's example Finding (rendered from the fixture's golden JSON). `--explain <fingerprint>` against a run
report prints that one finding with the full propagation path that produced `measured` (§2.5). The doc, the example and the mutation are one source (the rule's metadata), so they cannot drift.

### 1.5 Migrating lint (strangler, one rule at a time)
1. P2-T1 builds the engine; `lint_netlist.py` stays the entry point and loads both: legacy functions run exactly as now.
2. Each legacy rule (`spec, decoupling, polarity, led, short, pads, single-pin, PR-*`) is wrapped by a 10-line adapter that
   emits the new Finding; moved onto the IR, then to `rules/<id>.py`, **one per PR**, with a golden test that old and new output
   are identical on all 4 projects + the mutation suite (PA-3 rule: byte-identical). Order: `short`, `single-pin`, `polarity`
   (pure graph), then `spec`, `decoupling`, `led`, `pads`, `PR-*` (need records).
3. Legacy IDs are kept as aliases (waivers keep working). `lint` is deleted only when the last rule has moved; until then both paths report "items examined".

## 2. Electrical model (the "derived" IR section, `electrical.json`, built by `tools/boardgen/elec/model.py`)
A directed graph of **net nodes** and **elements**. Every net gets an interval `[vmin, vmax]` and a `source_path` (list of how we got there, for `--explain`).
Interval arithmetic throughout (min/typ/max corners), never single numbers: the answer is "worst case within stated tolerances".

### 2.1 Sources (seeded in this order; first definite source wins, conflicts are findings)
1. `NET_SPEC` `v` on a net = a **declared** range (what the designer says it is). It is the *claim* to be verified, not an axiom.
2. Regulator outputs from the record: new `electrical.regulator{vout:[min,typ,max] or adj_ref, dropout_v, i_max, iq_ma, theta_ja, tj_max}`.
   Net on the `power_out` pin gets `vout` **iff** input net >= vout+dropout at the load current (else the model sets it to `vin-dropout` and the
   dropout rule fires). Adjustable regulators/feedback dividers: out of scope v1 -> NOT_JUDGED unless NET_SPEC fixes vout.
3. Connector supplies: a connector pin with `supply{v:[..],i_max}` in the record or in `netlist.py` (`EXTERNAL = {"J1.VBUS": {"v":[4.4,5.25],"i":0.5}}`).
4. Ground nets (`class: ground`) = 0 V.
Check of the claim: declared NET_SPEC range must contain the derived range; derived outside declared -> `EL-NETSPEC` ERROR. No derivation possible -> NET_SPEC taken as the assumption and flagged INFO "assumed, not derived".

### 2.2 Propagation through passives
- **Series resistor** (2 pins, value parsed from `value`, tolerance from the record/`generic` default 5 %): no DC current assumed unless the far side is a load
  of known current -> voltage passes unchanged (static, no-load) and the drop `I*R` is applied only where a load current is declared in the record (`electrical.load_ma`, §2.5). Otherwise the net on the far side inherits the range widened by 0.
- **Divider** is computable iff: exactly two resistors in series between two nets with known intervals (Vtop, Vbot), the middle net has **no other
  DC element except pins whose class is `input` or `analog` with declared input leakage <= 1 % of divider current**. Then
  `Vmid = Vbot + (Vtop-Vbot)*R2/(R1+R2)` evaluated at the 4 tolerance corners. Anything else on the middle net (output pin, LED, second divider) -> not computed, NOT_JUDGED "divider midpoint not computable: <reason>" (leave to SPICE).
- **Pull-up/pull-down**: resistor from a net to a known rail with the other end on `input`/`open_collector`/`bidirectional` pins only = the net's *default state* (HIGH/LOW) used by floating/strap/open-drain rules; it does not produce a voltage interval on its own.
- **Capacitors**: open circuit at DC. **Inductors/ferrite/0R links**: short (same node). Fuses/PTC: short + `drop = I*Rmax` if the record has it.
- **Diodes / ESD**: forward Vf from the record (`electrical.vf [min,max]`). Series diode: `Vout = Vin - Vf` (interval). Clamp diode/TVS (`class` of both pins `passive`+record `role: clamp`): limits the net to `[-Vf, Vclamp]` *only as protection credit* for EL-CONN-PROT, not as a voltage source. LEDs are diodes with a Vf; their current is `(Vsrc - Vf)/R` when the series path is a single resistor (lint's `led` rule already finds this path).
- **Switches / MOSFETs / BJTs**: modelled as two-state elements. State determined statically only when the control node's interval is entirely above (ON) or below (OFF) the record threshold `electrical.vth`; ON -> channel is a resistor `Rds_on` (union of both nets), OFF -> open. Straddling or unknown -> **both states are propagated** and any rule reports the worse; the model flags it "state-dependent". Mechanical switches/jumpers: both states.
- Op-amps, comparators, gate logic, oscillators, anything with feedback or memory: **the model stops there.** Nets driven by an `output` pin get `[VOL, VOH]` derived from the driving part's supply net (`VOH>=Vcc-0.1` default only if the record says CMOS push-pull; otherwise the record's VOH/VOL or NOT_JUDGED).

### 2.3 Driver / receiver classification (from record pin `class`)
| class | on a net it is a | notes |
|---|---|---|
| `output` | **driver** (push-pull, may be tri-state per record `tristate`) | contention if >=2 drivers can be active |
| `open_collector` | **sink-only driver** | needs pull-up; several are fine (wired-AND) |
| `bidirectional` | driver *and* receiver | treated as driver for contention unless record `direction_by_config` says otherwise -> NOT_JUDGED |
| `input` | **receiver** (CMOS unless `electrical.input_type: ttl`) | floating = ERROR |
| `analog` | receiver, no logic thresholds | abs_max only |
| `power_in` / `power_out` | supply sink / supply source | feeds budget + abs_max on its own rail |
| `passive` | none | R/C/L/D/connector pins of unknown role |
| `nc` / `unspecified` | none | `unspecified` is NOT_JUDGED data gap if on a non-passive part |
Connectors default to `passive` per pin unless `netlist.py` declares direction (`EXTERNAL`), so external nets are classed as "driven by outside world" (worst-case range from `EXTERNAL`, default `[-0.3, rail+0.3]` is **not** assumed: unknown external = NOT_JUDGED).

### 2.4 Currents (budget model)
Loads on a rail = sum over (a) `electrical.load_ma{typ,peak}` of each part from its `power_in` pins, (b) resistor `V/R` to ground/rail, (c) LED current (§2.2), (d) declared `EXTERNAL` loads, (e) downstream regulators: `Iout + Iq` back-propagated (LDO) or `Pout/eff` (switcher, eff from record, else NOT_JUDGED). Tree is a DAG from source to leaf; cycles = ERROR. Peak and typical reported separately; ref-esp32's 465 mA table is the acceptance fixture.

### 2.5 Out of scope (explicit; each emits an INFO "not modelled", never silence)
Time-domain (RC settling, startup sequencing, EN timing, inrush), AC/impedance/EMC, noise, feedback loops, oscillators, USB/high-speed signal integrity, transient/ESD pulse energy, battery chemistry. These go to SPICE (`make_spice`) or `emc`. Every `measured` carries `path` (net->element->net chain) so `--explain` can show how a number arose.

## 3. First rule set
Severity ERROR unless noted. "Mut" = mutation id (new ones are added to `mutations.json`; each flips ONE thing in a copy of the fixture and must turn the rule red).
| Rule id | Inputs | Fires when / message | Mut |
|---|---|---|---|
| EL-ABSMAX | net interval, pin abs_max (resolve `pin:16+0.5` against that part's supply net interval) | `U1.EN: 5.25 V max > limit 3.6 V (abs_max v_max, rec esp32-s3-wroom-1)`; also `< v_min` and `i_ma` when a current is known | M-volt (NET_SPEC 3V3->5V on a GPIO net) |
| EL-LEVEL | driver `VOH/VOL` interval vs receiver `VIH/VIL` from records, both corners | `U3.SER: driver VOH min 3.0 V < VIH min 3.5 V (5 V CMOS receiver driven by 3.3 V)`; margin < 0.1 V = WARN | M-level (swap rail of receiver 3V3->5V) |
| EL-CONTENTION | >=2 `output` (non-tristate) pins on one net, or output vs `power_out`/GND short | `net X driven by U1.IO4 and U3.QA` | M-contend (join two output nets) |
| EL-FLOAT | `input` pin whose net has no driver/pull/`power` and no connector | `U2.SER floating CMOS input`; unused inputs with no `nc` declaration -> ERROR, `nc`-declared -> OK; analog -> INFO | M-float (delete a pull-down) |
| EL-OD-PULLUP | `open_collector` (or I2C-named bus) net lacks a pull to a rail, or pull value outside `[Vrail/Iol_max, tr-limit]` | `net SDA: open-drain driver U3.SDA, no pull-up` | M-pullup |
| EL-BUDGET | §2.4 sum vs `regulator.i_max`, connector `i_max`, fuse/PTC hold current, net `i_max` | `3V3 peak 465 mA > U2 limit 1200 mA` is fine; `VBUS_F 465 mA > connector source 450 mA` fires; margin <20 % = WARN | M-load (add 2 A load) |
| EL-DROPOUT | min Vin (incl. PTC/cable drop) - max Vout vs `dropout_v @ I` | `U2 headroom 4.40-0.116-3.3=0.98 V; dropout needed 1.2 V @ 465 mA (AMS1117-3.3 rec)`; the LDL1117 passes where AMS1117 (~1.1-1.3 V typ) fails | M-ldo (swap record AMS1117 into the ref-esp32 fixture) |
| EL-THERMAL | P=(Vin-Vout)*I (LDO), I²R (R, vs `p_max_mw`+derate 50 %), I²Rds(on) (FET), θJA from record (board-copper dependence not modelled: states "datasheet test-board θJA") -> `Tj = Ta + P*θJA` at `Ta` from the brief (default 40 C) vs `tj_max` | `U2 Tj 142 C > 125 C at 5.25 V, 465 mA` (matches ARCHITECTURE §2.3); WARN within 10 C | M-heat (raise load / lower θ margin) |
| EL-CONN-PROT | each connector net classified `external` (declared in `EXTERNAL`) must show: ESD/TVS clamp in path; reverse-polarity protection if `supply`; fuse/PTC if supply with `i_max`; else ERROR "unprotected external net" unless a `why` waiver | `J2.pin1: external signal, no clamp (GPIO via 470 R only)`; class reported per net: protected / series-R-only / bare | M-prot (delete TVS) |
| EL-STRAP | per-MCU **block data** `blocks/<mcu>.strap.json`: pin, required state per boot mode, allowed externals, forbidden (C on GPIO0, driven GPIO45/46); evaluates the net default state (§2.2 pull) and drivers | `GPIO0: expected pull-up (10 k to 3V3) found pull-up + 100 nF`; owned by P3 content, but the **evaluator** is built in P2 | M-strap |
| EL-NETSPEC | declared vs derived range (§2.1) | `3V3 declared 3.3±1 % but derived 3.0-3.6 V` | M-spec |
Common to all: each rule reports **items examined** (e.g. "37 pins, 28 judged, 9 NOT_JUDGED"); 0 examined on a design with such pins = ERROR (fail closed, §11.1).

## 4. Data gaps and fail-closed policy
### 4.1 Rule: never pass silently
Every pin/part a rule would judge but cannot yields `NOT_JUDGED`: `not judged: U2.VOUT has no abs_max (record ams1117-3.3, tier crosschecked)`. One finding per (rule, part, missing field), pins grouped in the message. The run report totals them per rule and per part, and the "items examined" line is `examined = judged + not_judged`, so a pass can never hide a skipped item. Parts with `kind: unregistered` -> NOT_JUDGED for every rule (single finding "part has no record").
### 4.2 Release requirements (field coverage gate, run by `release`, not by the rules)
| Field (record) | `hand` release | `pcba` release |
|---|---|---|
| `pins.*.class` on every pin of every active part | WARN if missing | **required** (ERROR) |
| `pins.*.abs_max` v_max/v_min on supply and signal pins | WARN | **required** on all pins except `nc`/`passive`/mechanical |
| `electrical.regulator` (vout, dropout, θJA, tj_max) for each regulator | required if a rail is derived | required |
| VIH/VIL/VOH/VOL for each logic IC pin that meets another supply domain | optional | required |
| `electrical.load_ma` for each powered IC (typ+peak) | optional (budget NOT_JUDGED) | required |
| `EXTERNAL` declaration for every connector (even "none") | required | required |
| record `verification` tier >= `crosschecked`, and `abs_max` listed in an evidence entry with `verified_by` | not required | required that class/abs_max sections appear in evidence (today they are **"agent-read, owner sign-off needed"**, so P2 must define the sign-off, see Q2) |
Pass condition for `pcba`: `NOT_JUDGED` count == 0 for the required fields (others INFO). `hand`: NOT_JUDGED allowed but printed.
### 4.3 Record schema additions (task P2-T2; all optional keys so existing records stay valid)
`electrical:{input_type, vih/vil/voh/vol (V or "ratio:0.7*vcc"), tristate, load_ma:{typ,peak}, regulator{...}, vf, vth, rds_on, theta_ja, tj_max, role}`, per-pin `abs_max.i_ma` already exists. Each value gets an evidence pointer; a number without evidence is typed `"illustrative"` and counts as NOT_JUDGED for `pcba`. Existing records that say illustrative (e.g. 74HC595 `lead_d_mm`) follow the same marker.
### 4.4 Run report
Section `rules`: per rule {examined, judged, ok, errors, warns, waived, not_judged}; `coverage`: table "part x field" (green/amber/red) fed to the webview; top banner "N items not judged" if > 0. Exit code: ERROR>0 or (`pcba` and not_judged>0) = fail.

## 5. Executable requirements (IV-2)
`REQUIREMENTS` (already a list in IR `requirements`) in `netlist.py`; each item is a dict with a `kind`, a human `text` (shown in reports) and kind-specific keys. Evaluated by `tools/boardgen/req/eval.py` over the IR+model; results `PASS|FAIL|NOT_EVALUATED` + evidence in the run report (a requirement the engine can't evaluate is NOT_EVALUATED = release block for `pcba`, never PASS).
```python
REQUIREMENTS = [
  {"id":"R1","kind":"path","from":"J1.VBUS","to":"U2.VIN","through":{"class":"fuse"},"text":"USB power passes a PTC"},
  {"id":"R2","kind":"path_absent","from":"3V3","to":"J1.VBUS","text":"3V3 never back-feeds the connector"},
  {"id":"R3","kind":"net_v","net":"3V3","min":3.0,"max":3.6},                    # on derived interval (worst corner)
  {"id":"R4","kind":"rail_peak","net":"3V3","max_mA":500,"basis":"peak"},         # on §2.4 sum
  {"id":"R5","kind":"static_logic","when":{"U1.IO48":"high"},"expect":{"LED1":"on"}, # static: LED path conducts, Vf met, I in range
   "text":"LED1 lights when GPIO48 is high"},
  {"id":"R6","kind":"spice","scenario":"boot_en","expect":{"V(EN) rise_time_ms":[5,20]},"text":"EN RC delay"},
]
```
Grammar: `kind` in {`path`, `path_absent`, `net_v`, `net_i`, `rail_peak`, `static_logic`, `spice`}. `through` matches by `class` (part-class from record kind/ref prefix: `fuse|diode|resistor|connector|ic:<registry id>`) or explicit ref; endpoints are `ref.pin|net`. All referenced refs/nets must exist (typo = ERROR, M-split-style).
- `path*`: BFS on the net-element graph, honouring switch/FET state only when `with:{"Q1":"on"}`; `through` means *every* path from..to crosses a matching element (cut-vertex test, not just one path).
- `net_v`, `net_i`, `rail_peak`: read the model interval; FAIL if any corner violates; report the interval.
- `static_logic`: set the named pins' nets to the stated logic level from the driver's VOH/VOL, run the same propagation, evaluate the target element: LED -> conducts iff `(V-Vf)/R` between 1 and the pin i_ma; FET -> state per §2.2. This is *not* simulation; it only answers "can the static path lead to that state".
- `spice`: delegates to `make_spice` with a scenario in the project's `SPICE` block; result mapped to PASS/FAIL; skipped (NOT_EVALUATED, reason "no LTspice") if the simulator is missing. Anything time-dependent must be of kind `spice`.
- Reporting: `req.json` in the run report: per requirement result, measured, path/evidence, and which rule/mutation it relates to. Every requirement needs a `text` and appears in the generated `REQUIREMENTS.md` (traceability: brief line -> requirement -> result). A project with 0 requirements is WARN (hand) / ERROR (pcba): "the board has nothing to be checked against".
- Mutation proof: M-req flips one connection; the requirement that covers it must turn FAIL.

## 6. Implementation tasks
Ordering delivers value first: engine+IR electrical data -> abs-max/contention/pull-up -> the rest. Parallel limit 3, disjoint files.
| ID | Task | Files | Effort | Deps | Acceptance |
|---|---|---|---|---|---|
| P2-T1 | Rule engine: registry, `@rule`, Finding, waivers v2, `--explain`, items-examined, run-report hook; adapters for 2 lint rules (`short`, `single-pin`) | `tools/boardgen/rules/__init__.py`, `engine.py`, `finding.py`, `lint_netlist.py` (adapter only) | medium | PA-1 (IR), PA-7 | lint output byte-identical on 4 projects; a dummy rule fixture+mutation passes; `--explain` renders |
| P2-T2 | Record schema `electrical` block + IR carries `abs_max`/`electrical`/`EXTERNAL`; fill records for the 4 fixture projects (ESP32 module, AMS1117, LDL1117, 74HC595, USB-C, SHT30, LEDs) with evidence | `parts/schema.json`, `tools/boardgen/ir/schema.json`, `ir/build.py`, `parts/records/*.json` | medium-high (data work dominates) | P1 | IR validates; coverage table generated; NOT_JUDGED list for fixtures captured as golden |
| P2-T3 | Electrical model v1: sources, resistors, divider rule, pull defaults, interval propagation, driver/receiver classes, `--explain` paths | `tools/boardgen/elec/model.py`, `elec/divider.py` | high | T1, T2 | divider fixtures (computable/not); blinky-555 and ref-esp32 nets derived = hand calc |
| P2-T4 | **EL-ABSMAX**, **EL-CONTENTION**, **EL-OD-PULLUP** (first value) + doc + fixtures + mutations M-volt/M-contend/M-pullup | `rules/el_absmax.py`, `el_contention.py`, `el_od_pullup.py`, `docs/rules/*.md`, `fixtures/rules/*` | medium | T3 | each: green fixture 0 findings, mutation red, ref-esp32 + reflex produce documented result |
| P2-T5 | EL-FLOAT, EL-LEVEL, EL-NETSPEC | `rules/el_float.py`, `el_level.py`, `el_netspec.py` | medium | T4 | same acceptance; M-float/M-level/M-spec |
| P2-T6 | Currents + diodes/Vf + FET states; EL-BUDGET, EL-DROPOUT, EL-THERMAL (ref-esp32 LDL1117 vs AMS1117 case) | `elec/budget.py`, `elec/devices.py`, `rules/el_budget.py`, `el_dropout.py`, `el_thermal.py` | high | T3, T2 | LDL1117 passes, AMS1117 swap fails EL-DROPOUT (M-ldo); the 465 mA table and the 0.74/0.85/0.91 W cases reproduced within 2 % |
| P2-T7 | EL-CONN-PROT + `EXTERNAL` grammar in netlist.py | `rules/el_conn_prot.py`, `boardgen/netlist_ext.py` | medium | T3 | M-prot; 4 projects classified; waivers needed only where a `why` exists |
| P2-T8 | Strap evaluator + `blocks/esp32s3.strap.json` (data from ARCHITECTURE §4); EL-STRAP | `rules/el_strap.py`, `blocks/esp32s3.strap.json` | medium | T3 | M-strap (cap on GPIO0 / pull-up on GPIO45); ref-esp32 green |
| P2-T9 | Requirements engine (`path`, `path_absent`, `net_v`, `rail_peak`, `static_logic`; `spice` stub) + `REQUIREMENTS.md` generator | `tools/boardgen/req/eval.py`, `req/schema.json`, `make_requirements.py` | high | T3 | M-req; ref-esp32 requirements R1-R5 PASS; typo'd ref = ERROR |
| P2-T10 | Release coverage gate (§4.2), run-report sections, `docs/RULES.md` generator, migrate remaining lint rules (one per PR), webview coverage table | `make_release_gate.py`, `docs/RULES.md`, `lint_netlist.py` | medium | T4-T9 | `pcba` blocks on any NOT_JUDGED required field; 0 false positives on all fixtures without waiver (P2 exit) |
Parallel waves: W1 = T1 + T2 (disjoint) ; W2 = T3 alone (core) ; W3 = T4 + T7 + T8 (rules, disjoint files) ; W4 = T5 + T6 + T9 ; W5 = T10. T4 is the first user-visible value.

## 7. Open questions (recommended default)
1. Should EL-LEVEL be ERROR or WARN when VOH-min is between VIH-min and VIH-typ? Default: ERROR below VIH-min, WARN for <100 mV margin.
2. Who signs off `abs_max`/`class` (records today say "agent-read, owner sign-off needed")? Default: tier `verified` requires a person's evidence entry; the `pcba` gate accepts `crosschecked + abs_max section in evidence` with a loud report line, `verified` removes the line.
3. Ambient temperature and θJA board-copper dependence? Default: Ta = 40 C from brief, datasheet test-board θJA, flagged "pessimistic/optimistic unknown"; refine in P4 with copper area.
4. Is NET_SPEC a claim (checked, §2.1) or an assumption? Default: claim, with INFO "assumed" when underivable.
5. Waiver expiry: mandatory? Default: optional, `pcba` requires `expires` for any ERROR waiver.
6. Unused-input policy: forced `nc` declaration or automatic internal-pull assumption? Default: declare in netlist `NC`; undeclared = ERROR.
7. Where do `EXTERNAL` declarations live? Default: in `netlist.py` next to `NET_SPEC`; records hold only the connector's pin class.
8. Typical vs worst corner for budget? Default: peak = design point (as ref-esp32), typical reported alongside; limit applies to peak.

## 8. Supervisor decisions (2026-10-28)
All 8 open-question defaults accepted as written. PA-7 (finding taxonomy, `--explain`, board markers) is **folded into
P2-T1** - the Finding object and `--explain` are the same work; board markers follow in P2-T10 / webview.
