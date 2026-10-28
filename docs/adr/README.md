# Architecture Decision Records

Each file records one decision: the context, what was decided, and what follows from it. Format:
`0000-template.md`. Numbers are never reused. A superseded decision gets a new ADR that names it.

| Number | Title | Status |
|---|---|---|
| [0001](0001-shared-generators-never-copied.md) | Shared generators, never copied | Accepted |
| [0002](0002-single-source-of-truth-generated-outputs.md) | Single source of truth, generated outputs, no hand edits | Accepted |
| [0003](0003-honest-gates-fail-closed.md) | Honest gates - non-zero exit, fail closed | Accepted |
| [0004](0004-mutation-suite-proves-gates.md) | Mutation suite as the proof that each gate works | Accepted |
| [0005](0005-independent-verification-no-ml-gate.md) | Independent verification; no ML classifier as a gate | Accepted |
| [0006](0006-parts-registry-verification-tiers.md) | Parts registry with verification tiers; agents never verify | Accepted |
| [0007](0007-pins-by-function.md) | Pins declared by function for registry parts | Accepted |
| [0008](0008-jlcpcb-assembly-stock-as-pcba-stock-source.md) | JLCPCB assembly stock as the PCBA stock source | Accepted |
| [0009](0009-design-ir-input-adapters-one-source.md) | Design IR with input adapters; one SOURCE per project | Accepted |
| [0010](0010-strangler-re-architecture-not-rewrite.md) | Strangler re-architecture instead of a rewrite | Accepted |
| [0011](0011-declarative-stage-registry-incremental-runs.md) | Declarative stage registry and incremental runs | Accepted |
| [0012](0012-per-board-assembly-mode.md) | Per-board assembly mode (pcba / hand) | Accepted |
