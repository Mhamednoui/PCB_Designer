# ADR 0007: Pins declared by function for registry parts

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Netlists connected pins by pad number. If a part was swapped for one with a different pinout, the wiring
silently went to the wrong pin. This is the wrong-library-pinout class of risk (R1). The known gap
M-libpin-swap showed it could happen. `docs/design/P1_PARTS_REGISTRY.md` section 9, decision 9, records the
decision.

## Decision

For registry parts, `netlist.py` connects pins by the record's pin name or function, for example
`pins={"B": "BASE", "E": "GND", "C": "LED_K"}`. `registry_part` derives the pad numbers from the crosschecked
record. Numbers are still accepted for generic 2-pin passives and for connectors. Ambiguous names (two pins
both called GND, or NC) are resolved by name plus index, or by an explicit number. The strict-project check
PR-BYNAME closes the pad-number escape hatch.

## Consequences

- Swapping a part for one with a different pinout renumbers the wiring correctly, by construction.
- The M-libpin-swap mutation changes from known-gap to an expected catch.
- Authors must name pins in registry parts. Ambiguous names need an explicit rule, which costs some typing.
- Generic passives and connectors keep their current, simpler numbering.
