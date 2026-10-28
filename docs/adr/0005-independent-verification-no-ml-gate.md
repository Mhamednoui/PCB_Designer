# ADR 0005: Independent verification; no machine-learning classifier as a gate

- **Status:** Accepted
- **Date:** 2026-10-27

## Context

`docs/PLATFORM_PLAN.md` section 9 is built on one principle: no single tool's opinion is trusted. Every
property that can reach fabrication is checked by engines that share no code. A machine-learning classifier
was considered as a gate. It was rejected. It outputs probabilities. There is no labelled corpus of PCB
wiring defects to train on. Its errors cannot be explained. A 98 % accurate gate lets one bad board in fifty
through with a green light.

## Decision

Every property that reaches the fab is checked by at least one deterministic engine. Where possible, two
engines that share no code check it (for example, netlist comparison and gerber LVS). ML or LLM output is
used only to find candidate problems, such as a design review or datasheet extraction, and it is advisory.
Every confirmed finding is turned into a deterministic rule with a mutation (ADR 0004). KiCad ERC and DRC
remain, as one voice among several.

## Consequences

- A gate's result can always be explained by a rule id and a measured value.
- The AI design review stage (planned for P6) can add findings but cannot pass a board.
- More engines must be maintained, and their agreement is itself a check.
- New tools are judged by whether they are deterministic and explainable, not by how accurate they look.
