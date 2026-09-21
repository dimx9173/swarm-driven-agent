---
description: SWDA delivery gate - reconcile via the swda CLI before delivering
---

Run the SWDA delivery gate on the files below. Nothing is delivered until this
passes.

Target: $ARGUMENTS

Pi has no MCP client: the gate runs through the `swda` CLI in bash, from the
project root (the CLI resolves the workspace from the current directory).

1. For every Python file changed in this task, run:
   `swda reconcile <file>`
   (add `--json` when you need the machine-readable verdict). Read the exit
   code as authoritative:
   - `0` - valid: deliver.
   - `1` - invalid: return to rework; the output names the hallucinated
     imports or symbols, fix them.
   - `2` - unverifiable: human confirmation is required. Report it as
     unverified; never present it as clean.
2. There is no `swda` CLI equivalent of the firewall audit; that check is
   OMP-only (MCP tool `swda_firewall_audit`). Say so and move on.

Report the exit code and the raw output for each file. If the CLI was not run,
say so explicitly instead of implying a pass.

<!-- swda-workflow:v1 -->
