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
- Extending the platform (adding a stage, check, part record): `docs/PLATFORM_PLAN.md` section 11.3.
- Never write backslash code through a bash heredoc (LESSONS_LEARNED section 14); use an editor tool.
