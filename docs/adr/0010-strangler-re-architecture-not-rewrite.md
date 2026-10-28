# ADR 0010: Strangler re-architecture instead of a rewrite

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

The pipeline works and has signed-off boards. A rewrite would put that at risk. The architecture-for-scale
phase (`docs/PLATFORM_PLAN.md` section 10, tasks PA-1 to PA-5) changes how stages read their inputs and how
they are run. It is not a change to what they check.

## Decision

Move the platform one stage at a time. Each stage is first declared in the new stage registry with its
behaviour unchanged (PA-2). Then it is ported to read the IR (PA-3), one stage at a time. A ported stage
must produce byte-identical outputs on the existing fixtures before the next stage is ported. The old path is
removed only when the new one is proven.

## Consequences

- The pipeline stays green at every step, and each step is small enough to review.
- For a while, two read paths exist. That is temporary and must be tracked in the roadmap.
- Byte-identical output is a strict test. It also depends on the determinism work (plan section 11.2).
- A rewrite's risk of silently changing a signed-off board is avoided.
