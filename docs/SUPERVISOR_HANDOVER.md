# Supervisor handover - read this first to continue the work

Written for: the next Claude session (after a compaction, a usage limit, or a new chat) continuing as
SUPERVISOR of this repo. Everything needed is in files; nothing lives only in chat. Updated after every merge.
**Last updated: 2026-10-28 (after P2-T9 merge cf8cba5; only P2-T6 in flight).**

## 1. Where things are
| What | Where |
|---|---|
| Master plan (scope, risks R1-R22, verification matrix, phases P0-P7, §9 independent verification, §10 scale, §11 standards) | `docs/PLATFORM_PLAN.md` |
| Execution tracker (every task + status) | `ROADMAP.md` |
| Phase designs | `docs/design/P1_PARTS_REGISTRY.md`, `docs/design/P2_ELECTRICAL_ANALYZER.md` |
| Decisions (why) | `docs/adr/0001-0012` |
| Facts/traps for agents | `AGENT_NOTES.md` (§E = current stages + traps) |
| History | `docs/SESSION_LOG.md`, `CHANGELOG.md`, `git log` |
| Branch | `improve/roadmap-v1` (pushed to public GitHub `Mhamednoui/PCB_Designer`); `main` = baseline |

## 2. The user (owner) - standing instructions
- Goal: a **platform** that produces valid, expert-level, fab-ready designs + PCBs. Old boards (blinky-555,
  uno-toggle, reflex-machine) are **regression fixtures**, freely rebuildable.
- "You are the expert, decide and act" - don't ask approval for routine work; ask only for destructive /
  irreversible / outward actions (force-push, deleting branches, spending Wokwi quota).
- Assembly mode per board: `ASSEMBLY = "pcba"` (JLCPCB SMD) or `"hand"` (THT).
- **Cost discipline** (subagents were 68% of usage): use agent types `pcb-worker` (Sonnet, medium) and
  `pcb-light` (Haiku, low) from `.claude/agents/`; ≤2 agents in parallel; no `high` effort unless truly
  cross-file; agents run the cheapest proving verification.
- **Write everything down** in repo files (this file, ROADMAP, AGENT_NOTES) - never rely on chat memory.
- The user may have files open in KiCad (an untracked `projects/reflex-machine/lib/arduino-library.pretty/Untitled.kicad_mod`
  is theirs - leave it; their earlier GUI saves are backed up in `C:\Users\nouir\PCB_user_backup\`).

## 3. Supervisor procedure (works; follow exactly)
1. **Launch** an agent (`pcb-worker`/`pcb-light`, background) with a brief: goal, spec section refs, files in
   scope, acceptance, commit message (ending `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`), report ≤8 lines.
2. **Isolation:** harness worktree isolation is BROKEN ("Could not read the repository git config to neutralize
   filter drivers"). Agents create their own: `git -C /c/Users/nouir/PCB worktree add /c/Users/nouir/PCB_wt/<task> -b <branch> improve/roadmap-v1`
   and work only there. Freerouting (git-ignored) is linked in when routing is needed:
   `cmd //c "mklink /J tools\freerouting C:\Users\nouir\PCB\tools\freerouting"` (remove with `cmd //c "rmdir tools\freerouting"`).
3. **Review** the report; check `git diff --stat`; insist on fail-closed behaviour, no silent skips, real findings
   reported not waived. Send corrections to the SAME agent (SendMessage) when possible.
4. **Merge** from the main checkout: `git merge --no-ff -q <branch> -m "Merge <ID>: ..."`. Generated-file conflicts
   (MANUFACTURING.md, CONNECTIONS.md) → take either side and regenerate. Code conflicts → read hunks, combine.
5. **Verify** after merge: `python tools/ci_checks.py all`; affected stages on the 3 fixtures
   (`python pipeline.py <id> --no-cache --only ...`); `python tests/mutations/run_mutations.py --tier fast --jobs 4`.
6. **Stage explicit paths only - NEVER `git commit -a`** (it once swept the owner's KiCad GUI saves into a commit).
   Then update ROADMAP status + this file, commit, `git push -q`, `git worktree remove /c/Users/nouir/PCB_wt/<task>`.
7. **Interrupted agent** (rate limit): `SendMessage` to resume. If resume fails ("worktree could not be verified"),
   commit its worktree state as a `wip(...)` commit and brief a fresh agent to continue from that commit.
8. Never write backslash-containing code via bash heredocs (LESSONS §14); `ci_checks ctrlchars` guards it.

## 4. State right now
- **Done:** P0 (honest + independent gates; mutation suite full 39/39), P1 (parts registry; fixtures migrated,
  pins by function, strict), PA-1 (design IR), PA-2 (stage registry + cache), PA-5 (parallel tiered mutations),
  PA-6 (run report), PA-9 (CI on GitHub), PA-10 (ADRs, CHANGELOG, VERSION 0.2.0), P2-T1 (rule engine),
  P2-T2 (electrical data, IR v2), P2-T3 (electrical model), P2-T4 (EL-ABSMAX/CONTENTION/OD-PULLUP +
  `electrical` stage), P2-T7(+b) (EXTERNAL + EL-CONN-PROT; blinky got a reverse-polarity diode), P2-T8 (EL-STRAP),
  P2-T9 (requirements engine + `requirements` stage; fast mutation tier 41/41).
- All 3 fixtures green on every stage; pipeline order: see `python pipeline.py blinky-555 --list`.

### Agents in flight (check their worktrees if the session restarted)
| Task | Branch | Worktree | What to do |
|---|---|---|---|
| P2-T6 budget/dropout/thermal | `feat/p2-t6-power` | `C:\Users\nouir\PCB_wt\p2t6` | if it has a final commit `feat(P2-T6)...` → review + merge per §3; if only uncommitted work → wip-commit + new agent |
Check with: `git worktree list`, `git -C <worktree> log --oneline -3`, `git -C <worktree> status --short`.

## 5. Next queue (in order)
1. Merge P2-T6.
2. P2-T5 (EL-FLOAT, EL-LEVEL, EL-NETSPEC - note reflex has 2 NET_SPEC conflicts: +5V K7805 tolerance, +12V_REG after diode).
3. P2-T10 (release coverage gate, `docs/RULES.md` generator, migrate remaining lint rules) → **P2 exit**.
4. PA-3 (port remaining checks to the IR), PA-8 (scaffolds + CONTRIBUTING), PA-4 (layer-agnostic + blinky-4L), PA-11 (hand-drawn schematic input).
5. P3 design blocks → P4 layout engine (auto-placement, MS-T0 antenna keep-out) → P5 PCBA package/sign-off (IV-3 gerber DRC, IV-4 IPC-356) → P6 ref-esp32 board + fuzzing.
6. Fixture fixes logged for MV-T2: LED LCSC C2895470 is a 3 mm LED on 5 mm footprints; reflex DESIGN_BRIEF promised a P-MOSFET reverse-polarity stage the board lacks.

## 6. Open items for the owner (none blocking)
- PC817C record stays `unverified` (KiCad symbol has empty pin names) - owner sign-off.
- All electrical data is agent-read (cited); owner sign-off raises records to `verified` (ADR 0006 release rule).
- 26 merged `worktree-agent-*` branches remain (worktree dirs removed); deleting branches needs the owner's OK.
