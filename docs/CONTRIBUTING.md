# Contributing

## Run the checks locally

```
python -m pip install ruff jsonschema -r requirements.txt
python tools/ci_checks.py all                          # same command CI runs
python tools/ci_checks.py compile secrets ctrlchars    # the fast pre-commit set
```

Sub-checks: `compile` (syntax of every tracked .py), `schemas` (parts records vs `parts/schema.json`,
`stages.json`, `mutations.json`), `selftests` (parts registry self-tests), `secrets` (token-like strings),
`ctrlchars` (stray control bytes, see LESSONS_LEARNED section 14), `ruff` (pyflakes F-rules only; vendored
`.claude/skills` excluded; findings are warnings except undefined names).

Optional git hook (not installed for you): `pip install pre-commit && pre-commit install`.

## What CI covers, and what it does not

GitHub's hosted runners have no KiCad, Freerouting or LTspice, so CI covers only what needs none of them:
the checks above. **CI does NOT run**: the pipeline stages (`pipeline.py`), the mutation suite
(`tests/mutations/run_mutations.py`), ERC/DRC, gerber LVS, SPICE or Wokwi simulation, webview browser tests.
Run those locally before merging; a green CI badge is not a signed-off board.

## More

- Architectural decisions: `docs/adr/`.
- Extending the platform: the "How to add" sections below (design: `docs/PLATFORM_PLAN.md` section 11.3).
- Never write backslash code through a bash heredoc (LESSONS_LEARNED section 14); use an editor tool.

## Scaffolding: how to add X

`python pipeline.py --scaffold <kind> <NAME>` creates the stubs (templates in `tools/boardgen/templates/`, code in
`tools/boardgen/scaffold.py`); it refuses to overwrite and validates the name. Selftest: `tests/scaffold/test_scaffold.py`.

| Add | Command | You then fill in |
|---|---|---|
| Rule | `--scaffold rule EL-MY-CHECK` (id `[A-Z]{2,4}-[A-Z0-9-]+`) | `tools/boardgen/rules/el_my_check.py` (auto-registered: the engine imports every `rules/*.py`; no core file changes), `docs/rules/EL-MY-CHECK.md`, `tests/rules/fixtures/EL-MY-CHECK/{green,red}.json` (green: `expected` `[]`; red: the mutated IR plus the expected findings), and the mutation `M-el-my-check` (created with `"status": "planned"`) |
| Stage | `--scaffold stage my-stage` | `tools/boardgen/my_stage.py` (stub fails closed) and the entry appended to `tools/boardgen/stages.json`: move it to its place in the order, set `inputs` (cache key) / `outputs` / `applies`; check with `python pipeline.py --describe my-stage` |
| Mutation | `--scaffold mutation M-my-mistake` | the planned entry in `tests/mutations/mutations.json` (field docs: top of `tests/mutations/run_mutations.py`); remove `"status"` once it runs |
| Part | `--scaffold part C123456` (same as `python tools/parts.py new C123456`) | the generated record in `parts/records/`: verify it against the datasheet and raise its tier per `parts/` rules |
| Block | `--scaffold block my-block` | `blocks/my-block.json` (model: `blocks/esp32s3.strap.json`: sources with pages, pins, policy) |
| Project | `--scaffold project my-board` | `projects/my-board/gen/netlist.py` (ASSEMBLY, PARTS, EXTERNAL, NET_SPEC, REQUIREMENTS), `gen/make_pcb.py`, README; then `docs/NEW_BOARD_PLAYBOOK.md` |
| Fab profile | not scaffoldable yet | fab rules are code in `tools/boardgen/fab_rules.py`; there is no `fab_profiles/` file format to template |

A scaffolded rule reports NOT_JUDGED (never a pass), so `python tools/ci_checks.py rules` stays red until the body, both
fixtures and the doc are real: that is the to-do list. The planned mutation is skipped by the suite (excluded from the
catch rate) until you delete `"status"`; fill in `op`, `stages`, `expect_stage`, `expect_text`, run
`python tests/mutations/run_mutations.py --only M-el-my-check -v` and it must be CAUGHT.

## Definition of done (any new check or stage)

1. Code: the rule/stage, with the failure message saying what, why and how to fix.
2. Schema: any new field is in `parts/schema.json` / `ir/schema.json` / the stage registry validator; `ci_checks.py schemas` passes.
3. Doc: `docs/rules/<ID>.md` (rules) or the `description` and README/ROADMAP lines (stages), no `TODO` left.
4. Fixture: `green.json` gives no finding, `red.json` gives exactly the expected findings (`python tools/boardgen/rules --check`).
5. Mutation: the entry names the catching stage and is CAUGHT with `"status"` removed; the fast tier stays all caught.
6. Run report: the findings reach `out/run/<ts>/report.json` (stages through the registry; rules through `$PCB_FINDINGS_FILE`, so counts and `counts.rules` include the new id).
7. `CHANGELOG.md`: one line under [Unreleased]. Then `python tools/ci_checks.py all`.

## Worktree and commit rules

- Work on a branch in your own worktree: `git worktree add ../PCB_wt/<task> -b feat/<task> <base>`; never edit another agent's worktree.
- Stage explicit paths (`git add path1 path2`); never `git commit -a` / `git add -A`. Check `git status` for stray scaffold output.
- `core.autocrlf=true` here: write new files with LF (the scaffold does); do not rewrite whole shared files (`stages.json`,
  `mutations.json`) with a JSON dumper, append entries so diffs stay one hunk.
- Commit message: `type(TASK): summary`, plus the Co-Authored-By trailer.
