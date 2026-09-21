---
description: SWDA status - workflow install, CLI health, and telemetry snapshot
---

Report the SWDA state for this machine.

1. Confirm the `swda` CLI answers: run `swda stats` and `swda models` from the
   project root and report what they return. (Pi has no MCP client, so there
   is no MCP bridge to check here.)
2. Confirm the contract is bound: look for the `swda-begin` / `swda-end`
   markers in the host's contract file (`APPEND_SYSTEM.md`).
3. Confirm this workflow pack is complete: the `swda` skill is loadable, and
   the prompt directory contains the `swda-*` entries plus `agents/` with the
   `swda-*` subagents (agents need pi-interactive-subagents plus a multiplexer
   session to run).

Extra context: $ARGUMENTS

Report each item as present or missing with the concrete path you checked. Do
not describe the workflow as installed from memory - check the files.

<!-- swda-workflow:v1 -->
