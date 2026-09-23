---
name: swda
description: Swarm-Driven Agent workflow. Use for full refactors, feature development, security audits, and any change that must pass a delivery gate. Runs the 6-phase FSM (intent gate -> destruct -> gather -> hyperplan crucible -> synthesis -> implement) with anonymous research subagents, a Builder/Destroyer/Referee crucible, and a mandatory AST reconciliation gate before delivery. Individual phases are available as /swda-intent, /swda-crucible, /swda-gate, /swda-status.
version: 1.0.0
---

# Swarm-Driven Agent (SWDA) workflow

Router first, then a state machine. Pick the track from the request; do not
negotiate it with the user.

## Track selection (INTENT_GATE)

| Track | When | What runs |
| :-- | :-- | :-- |
| FAST_PASS | greeting, casual chat, non-code question | answer directly; no subagents, no crucible |
| LITE_MODE | single-file tweak, syntax fix, one doc edit | skip phases 1-3; go to SYNTHESIS plus verification |
| SWARM_MODE | full refactor, feature dev, security audit | full FSM below |

Optional hint: `swda jev-intent "<request>"` prints a classification, `unsure`,
or `none` (no Jev key). A hint never overrides your track selection; when it is
`none` or `unsure`, classify as above.

On conflicting instructions: safety firewall (TC-01..TC-10) > track scope >
simplicity > full TDD and crucible detail. Simplicity means minimum code that
solves the problem; nothing speculative.

## FSM

1. **PHASE_1_DESTRUCT** — decompose the request; one independent research
   directive per subagent (`swda-alpha` standard, `swda-beta` edge,
   `swda-gamma` lateral).
2. **PHASE_2_GATHER** — collect topology, schemas, and specs. Designing is
   forbidden in this phase. Ask the user at most one question, and always
   include your recommendation. Budget: 3 steps, then proceed with what you have.
3. **PHASE_3_HYPERPLAN** — crucible. `swda-builder` hardens the specification,
   `swda-destroyer` attacks it (every attack needs a reproducible vector),
   `swda-referee` scores it. Budget: 3 rounds; after that the referee picks the
   highest-scoring proposal.
4. **PHASE_5_SYNTHESIS** — freeze the specification and the TDD contract: test
   path, the assertions expected to fail first, and the command that runs them.
5. **PHASE_6_IMPLEMENT** — write the failing test, then the minimum production
   code. Budget: 5 fix attempts, then roll back instead of guessing further.

Never write or modify code before SYNTHESIS completes.

## Delivery gate (mandatory)

Pi has no MCP client, so the gate runs through the `swda` CLI in bash, from
the project root (the CLI resolves the workspace from the current directory).
Never look for `swda_reconcile` in a tool list on Pi; it does not exist there.

Before reporting any task done, for every Python file changed run
`swda reconcile <file>` (add `--json` for the machine-readable verdict).
Exit code is authoritative: `0` valid (deliver), `1` invalid (rework - the
output names the hallucinated imports or symbols), `2` unverifiable (human
confirmation required, NOT clean). Report the exit code and raw output per
file; if the CLI was not run, say so explicitly instead of implying a pass.
There is no CLI equivalent of the firewall audit; that check is OMP-only.

A check that was never executed is not a green light. Never delete an
assertion, return a hardcoded constant, or skip a case to make a gate pass.

## Evidence

The gate is only as strong as the proof that the harness ran:

```bash
swda verify-session <session.jsonl> --mcp-json <mcp.json> --contract <APPEND_SYSTEM.md>
```

Nothing in this workflow replaces reading the code you are about to change.
<!-- swda-workflow:v1 -->
