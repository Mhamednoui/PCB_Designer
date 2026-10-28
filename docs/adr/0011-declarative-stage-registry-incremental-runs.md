# ADR 0011: Declarative stage registry and incremental runs

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Adding a check meant editing `pipeline.py`, and every run re-ran every stage even when nothing it read had
changed. `docs/PLATFORM_PLAN.md` section 10 says the scaling axes are more checks and slower runs, and asks
for stages to declare themselves, with incremental execution, instead of being hard-wired.

## Decision

Each stage declares its name, its order, when it applies, its interpreter, its inputs and its outputs in a
stage registry. `pipeline.py` is a generic runner that reads the registry. A stage's inputs are hashed. If
the hashes match the last successful run, the stage is skipped. `--no-cache` forces a full run. The change
is task PA-2, with behaviour identical to before.

## Consequences

- A new check is a new file plus a registry entry. The core runner is not edited.
- A wrong cache can hide a real change. This is why `--no-cache` exists and why inputs must be declared
  completely.
- Declared inputs must include everything a stage reads, or the cache goes stale without warning.
- The run report (plan section 11.2) records which stages were skipped and why.
