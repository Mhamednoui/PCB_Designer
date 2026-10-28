# ADR 0001: Shared generators, never copied

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Each board used to carry its own copy of the generic stages (`make_sch.py`, `make_outputs.py`). The copies
diverged: there were three versions of `make_sch.py` and two of `make_outputs.py`, and a bug fixed in one
project stayed broken in the others. The lesson is recorded in `docs/LESSONS_LEARNED.md` section 13 and in
the 2026-09-17 session log of `CLAUDE.md`.

## Decision

Stage code lives once, in `tools/boardgen/`. A project's `gen/` folder holds only what is specific to that
board: `netlist.py` (the design) and `make_pcb.py` (the placement). Generic stages are invoked with the
project's gen folder as their working directory. Nobody copies a stage into a project to change it. If a
board needs different behaviour, it passes data or a parameter.

## Consequences

- A fix to a shared stage reaches every board on its next run.
- A board-specific need must be expressed as data, not as a fork of the file.
- A change to a shared stage affects every fixture, so the fixtures and the mutation suite (ADR 0004) must
  be run after it.
- Drift can be detected by hashing the files that should be identical and counting the distinct hashes.
