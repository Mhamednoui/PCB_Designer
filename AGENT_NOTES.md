# AGENT_NOTES.md - shared findings for agents

Kept short on purpose. Replace stale lines; never append history here (history -> CLAUDE.md session log).
Severity: critical / high / medium / low. Always cite `file:line`.

## 0. Supervisor pre-audit (unverified seeds - Phase 1 agents confirm or refute)
- high: `projects/*/gen/make_pcb.py` (~700 lines x3) are 84-90% identical; 18 of 23 functions byte-identical.
  Already diverged: `reflex-machine/gen/make_pcb.py:507` still hardcodes `"J1"` GND seed (fixed in the other two);
  `stage_finish`, `stage_place`, `sync_routed_project` have 3 versions, `connect_orphans` 2. Same failure as LESSONS §13.
- high: no automated regression tests anywhere; every "verified" claim was a manual run.
- medium: `uno-toggle` + `reflex-machine` `.kicad_pro:92` set `footprint_symbol_field_mismatch: ignore` -> their "0 parity" is suppressed.
- medium: CLAUDE.md is 556 lines, auto-loaded every session; ~85% is session log.
- medium: stale docs: `webview/README.md` (7-step manual onboarding, "not verified in browser", "next: onboard 2nd project");
  `webview/ROADMAP.md` Phase 5 lists `--force` guard as TODO (done); `projects/reflex-machine/HANDOVER.md` §1 names per-project make_sch/check_sch (now shared).
- medium: `docs/LESSONS_LEARNED.md` lesson 21 recommends heredocs; lessons 14/17/30 say heredocs corrupted files. Contradiction.
- low: LESSONS §11-12 duplicate `docs/PCB_CREATION_GUIDE.md` §3/§6.
- low: `CODES/` (reflex firmware) at repo root; `projects/reflex-machine/test/pinmap.py:15-16` hardcodes it.
- low: `.mcp.json` `konnect` server fails to connect every session (plugin never installed).
- low: fresh clone can't route: all `make_pcb.py` need `tools/freerouting/freerouting/freerouting.exe` (git-ignored).
- open (reflex-machine, pre-fab): magnet current unknown; ESP32 row pitch assumed 25.4 mm; two holes 0.489 mm apart (< JLCPCB ~0.5).

## A. Architecture & structure
- MODULE MAP. `pipeline.py:75-101` builds stages; KiCad Python (`kicad_paths.PYTHON`) runs sch/sch-check/place/route/finish/check/outputs/fabreport/connections (all import pcbnew or sexp); system `python` runs pinmap + webview onboard (`:96,:100` bare "python" = PATH lookup, medium); `sys.executable` runs spice (`:98`). Shared stages = `tools/boardgen/*`; per project only `gen/netlist.py` + `gen/make_pcb.py` (+ fp fixers). Webview: `server/server.py` (stdlib HTTP :8787) -> `actions.py`, `services.py` (proxy to `services/{drc,echo,spice}/service.py`), `wokwi_mcp.py`, `vcd.py`; `tools/onboard.py` -> build_icon_cache/build_manifest/kicad_pcb. `make_pcb.py` imports `boardgen.make_sch.lib_symbol`, `sexp`, `kicad_paths`.
- make_pcb DIVERGENCE: PARTLY CONFIRMED, overstated. By per-function md5: 19 of 25 functions byte-identical across all 3 (V,mm,local,pcb_net_name,load_fp,set_field,add_text/line/track/zone,_free,_free_on,fanout_gnd,_stitch_and_fill,stage_route,stage_check,stage_render,strip_unused_dummy_nets, sync_routed_project - its "3 versions" was my slicing artefact: body is identical, only the trailing BW/BH line differs). Real divergence is 3 functions + placements():
  1. `connect_orphans` (reflex:502 vs blinky:487/uno:447): reflex hardcodes `fp.GetReference()=="J1"` GND seed (reflex:507, HIGH: StopIteration on any board without J1). Blinky/uno version (seed = footprint with most GND pads, early `return 0` if none) is correct; adopt it. reflex's own J1 is the 12V jack so result for reflex should be equal-or-better - verify by DRC only, do NOT rerun finish on signed-off board without --force.
  2. `stage_place` (blinky:232, uno:203, reflex:230): ~100 lines shared. Newest = blinky: silk offset derived from courtyard bbox, 0.9mm text (DRC min 0.8; uno/reflex still 0.7 -> latent text_height warnings), ref text moved below part, `SKIP_VALUE_SILK` tuple (blinky `()`, uno `("A1",)`, reflex `("A1","A2")`), outline from module-level `BOARD_OUTLINE` list (blinky:114, uno:85; reflex inlines a plain rectangle). Tail of stage_place per board = board-specific extras: reflex (:~315-345) MAG/HEADER_LABELS/PIN_LABELS silk text + 4 pre-route tracks incl. U3 pin13->8, J16->D4, ESP32 GND bus, J1->fuse 2.5mm; uno/blinky have none (blinky comment says none needed); reflex also prints A2 pad debug in stage_check-like loop (~:358, low, delete).
  3. `stage_finish` (blinky:553, uno:513, reflex:560): identical except reflex adds a second `add_zone(p12, F_Cu, L-shaped +12V poly, priority=1)`. uno/blinky differ from each other only in a comment.
  4. `placements()` differs by design (blinky:61 77L, uno:61 48L, reflex:61 75L) + module constants BW,BH,OX,OY, extra tables (reflex HEADER_LABELS:119, PIN_LABELS...).
- EXTRACTION PLAN -> new `tools/boardgen/pcb.py` (~560 lines moved out of each file, ~1700 total deleted from 3 files; ~600 net removed). Move AS-IS: all 19 identical functions + `stage_route`, plus `connect_orphans` (blinky version), `stage_place`/`stage_finish` bodies (blinky version) parameterised. Module must `import pcbnew` and `netlist` lazily; give it `class Board:` or a `configure(NL, OX, OY, BW, BH)` that sets module globals (PCB, ROUTED, OUT, FREEROUTING, V/local depend on OX,OY - simplest: `pcb.configure(...)` once, keep global style). Entry: `pcb.main(placements, **hooks)` dispatching place|route|finish|check|render (replaces the argv block at each file's end).
  Parameters (constants): OX,OY,BW,BH,BOARD_OUTLINE (default = rectangle from BW,BH), SKIP_VALUE_SILK, GLOBAL_NETS.
  Hooks (5): `placements() -> (P, pads...)` required; `extra_silk(board)` (reflex labels); `extra_routes(board, P, net)` (reflex pre-routes; default none); `extra_pours(board, nets, inset)` (reflex +12V zone; default none); `post_place_report(board)` (reflex A2 debug; or drop). Outline hook only if outline is not BOARD_OUTLINE.
  Leftover per project: constants + `placements()` (~50-80 L) + hooks (reflex ~60 L) -> ~70 L (blinky/uno), ~170 L (reflex). Estimated effort: 4-6 h incl. rebuilding blinky end-to-end; for uno/reflex verify with `check` stage ONLY and byte-diff `place` output into a scratch copy (per user decision they must not be rebuilt in place).
  Order: port blinky first (it is the reference version, `pipeline.py blinky-555 --force`, expect 0/0/0/3 silk), then uno (expect the 0.7->0.9 text change and reflowed silk; re-run DRC), then reflex (GND seed + silk change alter output; needs a scratch copy compare).
- REPRODUCIBILITY (fresh clone). Freerouting: `make_pcb.py:34` -> `tools/freerouting/freerouting/freerouting.exe` (git-ignored, installed only from `downloads/*.msi`, also ignored; no installer step/error hint, HIGH: route fails at `:381` with FileNotFoundError; move path + message to `kicad_paths.py`). KiCad: `kicad_paths.py:18-26` honours $KICAD_HOME, else newest `C:\Program Files\KiCad\*`, fallback 10.0 (OK; Windows-only, medium). LTspice: `make_spice.py:118-125` 3 hardcoded paths, clear error (OK). Wokwi CLI: `wokwi_mcp.py:21` `~/.wokwi/bin/wokwi-cli.exe` + token from HKCU registry `:33` (medium: Windows-only, no PATH lookup). PlatformIO: no code resolves it; `wokwi.toml` points at `sim/*/.pio/build/*/firmware.hex` (git-ignored `.pio/`, none committed) so live sim fails on a fresh clone until `pio run` is done by hand (HIGH for DX; add `pipeline.py` `firmware` stage or README step). Third-party clones under tools/ are ignored, and arduino-kicad-library (Mega/Uno footprints, used by `fix_*_fp.py`) is NOT recoverable from the repo (medium: pin a commit in a bootstrap script). No `requirements`/bootstrap script exists (medium).
- GENERATED vs SOURCE (git ls-files). Routed intermediates `*-routed.*`, route.dsn/ses, model.glb, run_log, .raw/.log are correctly ignored. Committed generated: `projects/*/out/` 79 files (gerbers zip, drl, STEP, PNG renders, erc.json, netlist.net), CONNECTIONS.md, MANUFACTURING.md, `webview/projects/*/manifest.json`. Fab zip + gerbers are defensible (sign-off artifacts) - keep; STEP/PNG (~MB, binary, churn on every run) -> low, consider git-ignoring `out/docs`. `out/erc.json` + `out/netlist.net` show modified in `git status` after a run = non-deterministic (timestamps/paths) -> medium churn noise; strip volatile fields or ignore. `reflex-machine/out/render_*.png` duplicates `out/docs/render_*.png` (low, stale duplicate to delete). MANUFACTURING.md embeds a timestamp (`make_fab_report.py:341`) so it diffs on every refresh (low). Ignored but needed: `webview/projects/*/model.glb` is regenerated by `onboard`, fine; `pycache` dirs exist on disk but are ignored (OK).

## B. Quality & correctness
Verified by running (baseline was clean except untracked AGENT_NOTES.md):
- py_compile: 35 first-party .py, 0 errors. `node --check webview/app/main.js`: ok.
- `pipeline.py <id> --list`: all 4 projects OK (pic-programmer = webview only; spice only blinky-555; pinmap only reflex).
- `pipeline.py blinky-555 --only sch-check,check`: both "ok" in 26 s; 0 netlist mismatches (7 nets), ERC {}, DRC 3 silk warnings, 0 unconnected, 0 parity.
- `reflex-machine/test/pinmap.py`: 26 signals, 0 mismatches, exit 0. Only stage that is already a correct gate.
- Side effect: that run rewrote tracked `blinky-555/out/{drc.json,erc.json,netlist.net}`; restored with git restore.
  Read-only stages are not read-only: `check`/`sch-check` dirty tracked files (medium, see fix list).
Findings:
- high `tools/boardgen/check_sch.py:50,64` (whole file, 64 lines): prints "N mismatches" and the ERC summary but never exits non-zero;
  `pipeline.py:109` only checks returncode, so a netlist mismatch or ERC error shows "sch-check ok". Gate: `sys.exit(1 if bad or erc_errors else 0)` (ignore warnings).
- high `projects/*/gen/make_pcb.py:703 (blinky) / :711 (reflex) / :663 (uno)` `stage_check`: prints DRC counts, unconnected, parity, returns None -> exit 0 even with DRC errors.
  Gate: count severity=="error", unconnected_items>0, schematic_parity>0 -> exit 1 (PCB_CREATION_GUIDE §2 step 6 definition; silk warnings allowed).
  Same for `stage_finish` DRC print, and `check_sch.py:24` / `make_outputs.py:33` which print CMD FAILED / "FAILED (n)" but carry on and exit 0
  (a failed gerber/drill export still ends in "outputs ok"). Gate: collect failures, exit 1 at end.
- Stages that already gate correctly: `pinmap.py:72` (return 1 if bad), `make_connections.py:190` (return 1 on pin diffs), `make_spice.py:290` (exit 1 on expect fail).
  `make_fab_report.py` exits 0 even when the cross-check vs .drl disagrees (medium; no returncode/exit logic found). `make_sch.py` not audited for exits.
- medium `pipeline.py:85-92`: pinmap and webview stages run bare `["python", ...]` (PATH python, not sys.executable) while others use KICAD_PYTHON/sys.executable
  - works only if PATH python is 3.11 with deps; line 183 is the only hard exit. No `--strict`/summary table of per-stage violation counts.
- medium: `out/drc.json`, `erc.json`, `netlist.net` are tracked and rewritten by every check (diff noise); either git-ignore them or write to a scratch dir.
- low `webview/server/server.py:572`: sole `except Exception`, commented and acceptable. No bare `except:`, no `shell=True`/`os.system` anywhere (grep).
- low: 3 `make_pcb.py` copies (see §0) each carry their own stage_check - the gate fix must be made 3x unless check is moved to `tools/boardgen/` first.
Tests: confirmed none (no tests/ dir, no test_*.py, no CI). Proposed smallest suite (`tests/test_smoke.py`, stdlib unittest, ~40 s, fixture blinky-555, read-only on a temp copy):
 1. `py_compile` all first-party .py + `node --check main.js` (2 s).
 2. `pipeline.py <id> --list` for all 4 projects; assert exact stage list + exit 0 (1 s).
 3. `pipeline.py blinky-555 --only sch-check,check` on a copied tree; parse out/drc.json, erc.json: assert errors==0, unconnected==0, parity==0, netlist mismatches==0 (27 s; needs KiCad).
 4. Run `pinmap.py` (reflex) and assert exit 0 + "0 mismatches" (1 s).
 5. Negative test: mutate one pin in a temp copy of blinky `netlist.py`; assert sch-check exits NON-zero (fails today = the regression that proves the gate fix).
 6. Pure-unit: `webview/tools/kicad_pcb.py` parse of a checked-in .kicad_pcb gives expected net count (blinky: 7 + GND); `vcd.py` on a small fixture.
Skip (not in suite): place/route/finish (need Freerouting, mutate boards), Wokwi (needs token + quota).

## C. Security, performance, dependencies & DX
Threat model: one user on localhost; public repo means strangers clone + run it. No critical/high found. Counts: medium 6, low 10, info 2.
Confirmed from section 0: CLAUDE.md size, webview/README stale, lesson-21 contradiction, `.kicad_pro:92` ignore (uno-toggle, reflex), HANDOVER.md:23 stale.
SECURITY
- medium: no Origin/Host check and no CSRF token on any POST (`webview/server/server.py:340-364`; body parser ignores Content-Type). A page the user visits can fire "simple" cross-origin POSTs at 127.0.0.1:8787: run a declared action (`:380-398`), `/sim/start` (burns Wokwi quota, `:515-530`), `/io` writes (`:455-495`); DNS rebinding adds reads. Fix: reject Origin/Host not equal to 127.0.0.1:<port>/localhost; require Content-Type application/json.
- medium: `webview/server/actions.py:23` runs `action["cmd"]` (no shell, arbitrary argv) and `:12` reads any file, both taken from a project's `actions.json`/`manifest.json`. Fine for own projects, but a cloned third-party project can run arbitrary commands when its action is triggered (or via the CSRF above). Fix: allow-list cmd[0], confine cwd/path under the project dir, document "only onboard projects you trust".
- low: `server.py:117,145,443,526` join `wmap["cwd"]` from `wokwi_map.json` with no confinement (writes `USAGE_LOG.md`, `scenario_*.yaml`); `safe_join` not used there. Same trust issue.
- low: `server.py:446-460` scenario YAML interpolates `step.get('value')` unsanitised (only `name` is sanitised, `:433`). Coerce to float.
- low: `server.py:486-495` `/io` accepts any string as `type`; `net` must already exist, so no arbitrary-key write. Validate against `INPUT_TYPE_ALIASES`.
- low: `safe_join` (`server.py:57-62`) is sound (realpath+commonpath, no traversal found) but commonpath raises ValueError across drives -> 500 not 400.
- low: service proxy (`webview/server/services.py:93-110`): host hard-coded 127.0.0.1, port from service.json, name checked by `ID_RE` (`server.py:47`) -> no SSRF off-host. Services themselves (`webview/services/*/service.py:61,76`) have no Origin check and are reachable directly on 88xx ports.
- low: bind is 127.0.0.1 only (`server.py:667`); Content-Length uncapped (`:340-364`), local DoS only.
- low: `.mcp.json` and ~7 tracked docs/analysis JSON embed `C:\Users\nouir\...` paths (privacy/portability, not a secret).
- info: Wokwi token only read from env / HKCU Environment (`webview/server/wokwi_mcp.py:28-35`), never logged or stored. `.mcp.json` holds no secret. `git ls-files` (426 files) has no key/token/.env files (the "key" matches are the digikey skill's API-client code). run_log.jsonl and model.glb are git-ignored.
PERFORMANCE
- info: polling 400 ms outputs / 700 ms serial / 300 ms status (`webview/app/main.js:884-887`), only while a sim runs; reads are pipelined. GLBs 0.36/3.8/3.4 MB, git-ignored, so a fresh clone has NO model.glb until onboard.py runs with KiCad. No O(n^2) hotspot spotted in make_fab_report/make_connections at 3-board scale (not profiled).
DEPENDENCIES
- medium: no requirements.txt/pyproject anywhere; `.venv/`, `tools/freerouting/` (Java exe), `tools/*` clones, `downloads/` are untracked, so a fresh clone cannot route, import parts or run Wokwi, and no package versions are recorded (easyeda2kicad, skidl, kicad-skip, fastmcp). Add pinned requirements.txt + SETUP/doctor step.
- low: vendored three.js is r160 (`webview/app/vendor/three/three.module.js:6`, Dec 2023, ~34 months old); no license file noted beside it. Local-only, low exposure.
- low: stages need KiCad Python (pcbnew) while pipeline.py/webview use system Python; webview `__pycache__` shows cpython-313, not the 3.11.0 CLAUDE.md states. Split is explained only in README.
DX / DOCS
- medium: CLAUDE.md = 556 lines / 52 KB (~13k tokens) auto-loaded every session; `## Session log` is lines 93-556 (83%). Move to docs/CHANGELOG.md, keep Status + rules (~90 lines).
- medium: `webview/README.md:76` still says "not yet re-verified in a browser" and describes manual onboarding though onboard.py exists; `projects/reflex-machine/HANDOVER.md:23` names per-project make_sch/check_sch (now shared in tools/boardgen/).
- medium: `docs/LESSONS_LEARNED.md:55` (lesson 21: use heredocs) contradicts :64, :311-324, :391-393 (never heredoc content with backslashes/escapes). CLAUDE.md Status header says "last checked 2026-09-11" but holds 09-18 state.
- low: `README.md:92` lists Freerouting under tools/freerouting/ as available; it is git-ignored and absent on a clone. `.mcp.json` `konnect` never connects (plugin not installed) -> error each session.
- low: 3 tracked `projects/*/*-routed.kicad_pro` files match a .gitignore rule (tracked earlier; stale). Windows-only: winreg token read, Program Files fallback, PowerShell instructions.
- low: doc path check: every doc-referenced file with a real path exists (docs/diagrams/*.svg ok); bare names like make_pcb.py/netlist.py are per-project and fine.
- Newcomer path: README -> docs/NEW_BOARD_PLAYBOOK.md (A-M) -> hand-write netlist.py + make_pcb.py placements -> `pipeline.py <id>`. Gaps: no setup/doctor step, no `pipeline.py --new` scaffold (admitted in CLAUDE.md), no automated tests, LICENSE not checked.
