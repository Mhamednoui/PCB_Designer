# ADR 0012: Per-board assembly mode (pcba / hand)

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

Boards are built in two ways. Some are assembled by JLCPCB, which places SMD parts from LCSC. Others are
through-hole and soldered by the owner. The two need different BOM and CPL output, and different stock rules.
`docs/PLATFORM_PLAN.md` section 1 lists both as in scope, and names `pcba` and `hand` as the two modes.

## Decision

Every board declares its assembly mode, `pcba` or `hand`, in its project. The mode decides three things:
the BOM and CPL content, the stock severity (ERROR for `pcba`, INFO for `hand`, ADR 0008), and whether a
generic passive must be bound to an orderable MPN at release
(`docs/design/P1_PARTS_REGISTRY.md` section 9, decision 2). A board with no declared mode must not
be assumed to be either.

## Consequences

- The release report states the mode, so a reader knows which checks applied.
- A through-hole board is not blocked by JLCPCB stock, but its stock is still reported.
- A board that changes mode needs its BOM and stock checks run again.
