# ADR 0008: JLCPCB assembly stock as the PCBA stock source

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

A `pcba` board is assembled by JLCPCB from LCSC parts. If a part is out of stock at the assembler, the order
stalls. `docs/design/P1_PARTS_REGISTRY.md` section 9, decision 4, sets the stock policy. The stock source
(`jlcsearch`) does not list some valid LCSC ids (decision 11), so a single source is not enough. Plan
section 7 A1 names JLCPCB as the primary fab.

## Decision

For `pcba` boards, the JLCPCB assembly stock is the reference for stock. The parts stage reads it through
a source chain, so a missing id in one source falls back to the next. Stock severity is ERROR for `pcba`
and INFO for `hand`. Each part needs at least 20 % margin over the required quantity. The stock snapshot must
be no more than 7 days old. An older snapshot gives a WARN with its age, not a PASS.

## Consequences

- A `pcba` release needs a fresh stock snapshot. An offline run reports WARN, not success.
- The source chain adds code to maintain, but it removes the single point of failure.
- Hand-soldered boards are not blocked by stock, only informed.
- Generic passives on `pcba` boards get their MPN bound at release (decision 2).
