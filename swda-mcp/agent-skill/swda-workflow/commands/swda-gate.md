---
description: SWDA delivery gate - reconcile and firewall-audit before delivering
---

Run the SWDA delivery gate on the files and commands below. Nothing is
delivered until this passes.

Target: $ARGUMENTS

1. For every Python file changed in this task, call the **MCP tool**
   `swda_reconcile` on the `swda-mcp` server with arguments
   `{file, workspace_root}`. This is a model tool call, NOT a shell command:
   never run `swda_reconcile` in bash. If the tool is not in your tool list,
   stop and report `GATE NOT RUN (tool unavailable)` - do not shell out, do
   not invent a verdict, and do not present the task as delivered.
   Read the `verdict` field as authoritative:
   - `valid` - deliver.
   - `invalid` - return to rework; fix the reported imports or symbols.
   - `unverifiable` - human confirmation is required. Report it as unverified;
     never present it as clean.
2. Optionally pre-screen the shell commands and inline code with the **MCP
   tool** `swda_firewall_audit(command=..., code=..., phase=...)` (also a
   model tool call, not a shell command).

Report the raw verdict for each file. If a tool call was not made, say so
explicitly instead of implying a pass.
<!-- swda-workflow:v1 -->
