# Changelog

All notable changes to the PCB platform. Format follows Keep a Changelog. The version is in `VERSION`.

## [Unreleased]

### Added
- EL-CONN-PROT refinements (P2-T7b): RC-filtered inputs pass (INFO); board outputs behind a series R = WARN, inputs/bare = ERROR; `EXTERNAL["J16"] = {"class": "expansion", "why": ...}` makes unprotected nets WARN; waivers accept `"match"` (message substring). blinky-555 rebuilt with a series reverse-polarity diode D2 (1N4007); reflex-machine README records the missing P-MOSFET stage.
- EXTERNAL declarations + EL-CONN-PROT (P2-T7): `EXTERNAL` blocks in blinky-555, uno-toggle and reflex-machine `netlist.py` (helpers `tools/boardgen/netlist_ext.py`); rule `rules/el_conn_prot.py` (supply input: surge clamp + reverse-polarity + fuse when a source current is declared; signal: clamp / isolated / series-R-only / bare; module sockets exempt; undeclared connectors NOT_JUDGED); CLI `tools/boardgen/elec/conn_prot.py <id> [--table]`; `docs/rules/EL-CONN-PROT.md`, fixtures, `tests/rules/test_el_conn_prot.py`; mutation `M-prot` (planned until an `electrical` stage exists). Engine: `external` is now a readable IR section. reflex-machine NET_SPEC for the 12 V nets is now the +-10 % range instead of the point 12 V.
- Rule engine (P2-T1, folds PA-7): `tools/boardgen/rules/` (`@rule(id, severity, needs, doc, fixture, mutation)`, load-time registry check, typed `Finding` with measured/limit and a NOT_JUDGED severity, items-examined stats, `--explain`), waivers v2 in `waivers.py` (`why` >= 20 chars, `expires`, ERROR->WAIVED only), run-report hook (`$PCB_FINDINGS_FILE` -> `findings` + `counts.rules`). Lint `short` / `single-pin` run through it as `LINT-SHORT` / `LINT-SINGLE-PIN` (output unchanged). New `ci_checks.py rules`, `tests/rules/`, `docs/rules/`.
- Electrical model v1 (P2-T3): `tools/boardgen/elec/model.py` + `divider.py` - per-net voltage intervals with provenance and status (derived / claimed-only / conflict / NOT_JUDGED), driver/receiver classes, pull defaults, worst-case divider (16 tolerance corners, computable only when nothing loads the midpoint); `ctx.model` in the rule engine; `python tools/boardgen/elec/model.py <project> --net <NET>` prints the derivation; tests in `tests/elec/`, `ci_checks.py elec`.
- Electrical data (P2-T2): optional `electrical` block in `parts/schema.json` (per-pin abs_max / VIH VIL VOH VOL / I_out, regulator dropout-vs-current, theta_JA, Tj max, Vf, Rds(on)@Vgs, load_ma, clamp; every number carries `src` = URL + PDF page, or `illustrative: true`, enforced by `parts.validate`; UNSIGNED so no crosschecked record changed tier). 16 records filled, 4 new unverified drafts (LDL1117S33R, SHT30, hand-written ESP32-S3-WROOM-1-N8 and USBLC6-2SC6). Design IR is now ir_version 2: per-part `electrical`/`electrical_status`, per-pin `abs_max`/`io`, top-level `external` (`EXTERNAL` in netlist.py). `python tools/boardgen/ir/build.py --coverage` prints the required-fields-present vs NOT_JUDGED table; golden `tests/ir/elec_coverage.golden.txt` is compared by the ir selftest. `parts._check` now resolves `$ref`/`$defs`.
- Design IR (PA-1): `tools/boardgen/ir/` (`schema.json` ir_version 1, `from_netlist.py`, `from_kicad_pcb.py`, `build.py`), pipeline stage `ir` -> `projects/<id>/out/design.json` (git-ignored, deterministic, schema-validated) with a netlist-vs-board net cross-check; `build.py --selftest` runs in `ci_checks.py`.
- `tools/ci_checks.py` (compile, schemas, selftests, secrets, ctrlchars, ruff), `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `docs/CONTRIBUTING.md` (PA-9).
- `tests/mutations/run_mutations.py`: `--jobs N` (threads; `route` entries serialised by a lock) and `--tier fast|full` (PA-5). Fast tier ~28 s, full ~129 s at 4 jobs (179 s serial).

### Fixed
- `tools/boardgen/check_sch.py` line 92: a heredoc-corrupted `BS-b` (raw 0x08) in the ERC-ref regex meant it never matched; found by the new ctrlchars check.

## [0.2.0] - 2026-10-28

Commits since the baseline `1ec4127` ("chore: baseline before roadmap") on `improve/roadmap-v1`.

### Added
- Architecture Decision Records in `docs/adr/` (0001-0012) and an index.
- Shared `make_pcb` core in `tools/boardgen/pcb.py` (M1-T3, `1f61e4e`).
- Netlist lint stage with `NET_SPEC` (MD-T1, `9c43cee`).
- Review stage with waivers, using the kicad-happy analyzers (MD-T5, `eb77ef9`).
- JLCPCB and per-net current DRC rules (MD-T2, `8270ccd`).
- SPICE assertions for LED forward and reverse current (MD-T3, `455f79e`).
- Native pad-to-pin decoupling check, with route and finish retries (MD-T9, `da8dd77`).
- Gerber LVS stage: connectivity of fab output compared with the netlist (MD-T6, `2ecb2c2`).
- Data-driven mutation suite as the catch-rate gate (MD-T7, `388ab50`).
- Parts registry: schema and loader, cache, `parts new/refresh` (P1-T1, P1-T2).
- Registry verification tiers with assist, crosscheck and sign workflow (P1-T3, `071294f`).
- Registry rules in lint: REF, HASH, SYM, PAD, HOLE, PKG-NAME (P1-T5, `1cc870e`).
- Parts stage: MPN, GEO, PKG, STOCK, FRESH checks (P1-T6, `7c6afe1`).
- Pins-by-function registry API and strict mode (P1-T9a, P1-T9b).
- Declarative stage registry and incremental, input-hash runner (PA-2, `83e54c2`).
- Run report (JSON and HTML), tool-version capture, deterministic generated reports (PA-6, `158c129`).

### Changed
- Shared stages exit non-zero on failure (M1-T1, `6eb6235`).
- Pipeline uses `sys.executable` and prints a summary; volatile check outputs are no longer tracked (M1-T2).
- Current rules honour copper weight, temperature rise and pours (MD-T2b, `8cc43da`).
- Via and stitch spacing is derived from fab rules, not a fixed hole-to-hole check (MD-T11, `383a9ef`).
- Pinmap stage uses the shared `check_pinmap.py` with a FIRMWARE block; risky ERC warnings promoted (MD-T4).
- Decoupling capacitors are placed at their IC supply pins (MD-T8, `f8baef9`).
- Generated `.kicad_dru` files use LF line endings (`04a49b1`).
- Fixture ICs have crosschecked registry records: IRLZ44N, 74HC595, K7805 pinout (P1-T8).
- Generic and connector parts keep their per-instance LCSC id; package family matching (P1-T9b, `3f9a8c1`).
- JLCPCB assembly stock source chain for the parts stage (P1-T10, `cdf1242`).

### Fixed
- Shared stages reported success after a failure (M1-T1).
- `fabreport` fails when a check reports CHECK (MD-T2).
- Reports skipped excluded module parts silently; they now list them (MD-T9, `0c0429b`).
- Blinky C3 and reflex C13 decoupling placement (MD-T8).
- Reflex 12 V input path resized for 10 A (MD-T10, `3c92a6f`).
- PR-HOLE severities: drill below lead diagonal is ERROR, below the recommended margin is WARN (P1-T9a, P1-T8).
- Registry ids: LCSC ids are kept, package family is matched, and PR-BYNAME closes the pad-number escape (`3f9a8c1`).

## [0.1.0] - baseline

Baseline before the improvement roadmap: `1ec4127` ("chore: baseline before roadmap"). Shared stages
were copied per board, stages exited 0 on failure, and there was no mutation suite, parts registry, stage
registry or run report.
