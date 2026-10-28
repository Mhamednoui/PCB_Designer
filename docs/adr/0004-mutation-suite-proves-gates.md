# ADR 0004: Mutation suite as the proof that each gate works

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

A check that has never been seen to fail is not evidence of anything. `docs/PLATFORM_PLAN.md` section 2
principle 5 requires a mutation (a deliberately broken board) for every check. Section 11.1 says it plainly:
"a check without a mutation is not supported". The catch rate is a progress measure (section 8).

## Decision

Mutations are data: one entry per deliberate defect, in a data-driven suite (MD-T7). The suite applies each
mutation to a fixture, runs the gate, and expects it to fire. A mutation that is not caught is a failure of
the suite. The catch rate is reported. The suite is run in full before a release. A fast tier (under 60 s)
runs on every change. The planned parallel and tiered runner (PA-5) makes this possible as the suite grows.

## Consequences

- Adding a check means adding its mutation entry in the same change (section 11.3 definition of done).
- Each gate has a known catch rate, not a claimed one.
- The suite takes time and must be kept fast enough to run on every change, which is why it is tiered.
- A "known-gap" mutation is allowed only as a documented gap, and it is flipped when the gap is closed.
  Example: the pin-swap mutation M-libpin-swap (ADR 0007).
