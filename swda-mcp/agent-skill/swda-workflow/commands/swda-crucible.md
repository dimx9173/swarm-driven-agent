---
description: SWDA hyperplan crucible - Builder vs Destroyer judged by a Referee
---

Run the SWDA PHASE_3 crucible on the proposal below. Dispatch `swda-builder`,
`swda-destroyer`, and `swda-referee` as separate subagents through your host's
subagent mechanism (OMP: the `task` tool with the agent name; Pi: the
`subagent` tool with the agent name, which needs pi-interactive-subagents plus
a multiplexer session), then report the outcome.

Proposal: $ARGUMENTS

Rules:

- The builder defends structural integrity and type safety proportionally; no
  speculative abstraction.
- Every destroyer attack must name a reproducible vector (input, sequence, or
  probe) - "could be fragile" is not an attack.
- The referee grades against explicit criteria, applies Occam's razor, and does
  not split the difference or flatter either side.
- Hard budget: 3 rounds. If the builder and destroyer still disagree, the
  referee selects the highest-scoring proposal and you proceed with it.

Report `CRUCIBLE_STATUS`, `CRUCIBLE_SCORE` with justification,
`VULNERABILITY_FOUND`, `ATTACK_POINTS`, and `REQUIRED_FIXES`.
<!-- swda-workflow:v1 -->
