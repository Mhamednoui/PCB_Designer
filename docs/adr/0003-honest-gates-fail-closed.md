# ADR 0003: Honest gates - non-zero exit, fail closed

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Shared stages used to print a failure and still exit with status 0, so a pipeline could report success while
a check had failed. `docs/PLATFORM_PLAN.md` section 2 principle 4 says a check that cannot judge something
must say so. Section 11.1 says unknown input, missing data, an offline source, or zero items examined must
produce WARN with a reason, or FAIL. Never PASS.

## Decision

Every stage that finds a failure exits with a non-zero status, and the pipeline stops at that stage. The
pipeline prints a summary of every stage. A check that cannot judge something reports WARN with the reason.
If it examined zero items, it reports WARN or FAIL, not PASS. Accepted exceptions are written in
`projects/<id>/waivers.json` with a reason, and unused waivers are reported.

## Consequences

- A green run means every stage ran and judged its input.
- Some runs that used to pass now show WARN or FAIL. That is the intended effect.
- Offline sources (stock, distributor data) cannot silently produce a pass. They produce a WARN with the age
  of the data.
- Every new check needs a defined behaviour for "no data", and a mutation that proves it (ADR 0004).
