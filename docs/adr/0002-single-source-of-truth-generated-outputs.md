# ADR 0002: Single source of truth, generated outputs, no hand edits

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

`docs/PLATFORM_PLAN.md` section 2 principle 1 says intent is defined once. Everything else is derived. Hand
edits to schematics, PCB files and reports made the board and its intent disagree, and the disagreement was
found late. Section 11.1 of the plan asks that hand edits of generated files be detected and refused.

## Decision

Each project declares exactly one source of intent: `netlist.py` for scripted boards, or one hand-drawn
KiCad schematic for drawn boards (ADR 0009). The schematic, the PCB, the gerbers, the BOM, the CPL and the
reports are generated from that source. A generated file that was edited by hand is detected by its hash and
refused, so the fix is always made in the source and the output is regenerated.

## Consequences

- The correct workflow is: edit the source, run the pipeline, commit the regenerated outputs.
- A KiCad GUI save of a generated file is a trap. One such accidental commit was reverted in the history.
- Generated files must be deterministic (sorted output, fixed timestamps; section 11.2 of the plan), or the
  hash check would fire on every run.
- Reviewers can trust that a diff in a generated file has a matching diff in the source.
