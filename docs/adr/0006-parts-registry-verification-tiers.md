# ADR 0006: Parts registry with verification tiers; agents never verify

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Parts were taken from libraries without evidence that their pinout or footprint matched the real part. This is
risk R1 in `docs/PLATFORM_PLAN.md`. Plan section 7 A4 requires a person to check the pinouts of new parts
against the datasheet. The registry design (`docs/design/P1_PARTS_REGISTRY.md` section 9, decision 1) makes
this a set of tiers, so automation reduces the human work without removing it.

## Decision

Each registry record has one of three tiers:

- `unverified`: the default. The record has not been cross-checked.
- `crosschecked`: set by a tool only when at least two independent machine sources agree on every pin (KiCad
  symbol, EasyEDA/LCSC pin names, and a datasheet page cited by the agent), and the `assist` step reports zero
  differences.
- `verified`: set only by the owner, who signs it.

Agents never set `verified`. A `crosschecked` part may be released, but the sign-off report lists every
non-`verified` part as an open human-check item.

## Consequences

- No agent can approve its own part.
- Released boards show exactly which parts still need a human look.
- Parts whose evidence is weak stay `unverified`. For example, the PC817C stays unverified because its KiCad
  symbol has empty pin names.
- Clone parts carry a release item to verify the part marking before power-up.

Release rule (2026-10-28, reconciles plan A4): a release package may contain `crosschecked` parts, listed as OPEN
human-check items; the release is not signed off until the owner raises each to `verified`.
