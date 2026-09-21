---
description: SWDA status - workflow install, MCP bridge, and telemetry snapshot
---

Report the SWDA state for this machine.

1. Confirm the `swda-mcp` tools answer: call `swda_stats` and `swda_models`.
2. Confirm the contract is bound: look for the `swda-begin` / `swda-end` markers
   in the host's contract file (`APPEND_SYSTEM.md`).
3. Confirm this workflow pack is complete: the `swda` skill is loadable, and the
   host's command or prompt directory and (where the host supports task agents)
   the agent directory contain the `swda-*` entries.

Extra context: $ARGUMENTS

Report each item as present or missing with the concrete path you checked. Do
not describe the workflow as installed from memory - check the files.
<!-- swda-workflow:v1 -->
