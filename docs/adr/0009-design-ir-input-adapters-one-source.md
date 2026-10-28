# ADR 0009: Design IR with input adapters; one SOURCE per project

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Every stage re-parsed `netlist.py` or the KiCad files on its own. That duplicated the logic and let stages
disagree. `docs/PLATFORM_PLAN.md` section 10 asks for one design intermediate representation (IR), built
once, at `out/design.json`. Section 10.1 adds that a person may draw the schematic by hand in KiCad. That
input must produce the same IR.

## Decision

A single IR holds parts, pins by function, nets, board, requirements, assembly mode and fab profile. An
`ir` stage builds it. Input adapters feed it: `netlist.py` (today's path) and `ir_from_kicad_sch`, which
reads a hand-drawn schematic. KiCad API calls are confined to the adapters (the R16 firewall). Every project
declares exactly one `SOURCE`. The generator never overwrites a hand-drawn schematic. Missing electrical
intent fails closed, for example "VBUS: no current declared".

## Consequences

- All checkers read the same IR, so downstream stages do not care where the design came from.
- A change of KiCad version touches only the adapter.
- The IR schema must be versioned and validated against JSON Schema on load.
- The IR work (PA-1) and the drawn-schematic adapter (PA-11) are real effort. The drawn-schematic adapter must
  reproduce the blinky IR from `netlist.py` before it is trusted.
