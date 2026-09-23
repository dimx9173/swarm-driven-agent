---
name: swda
description: SWDA delivery-gate tools for prime-agent sessions. Call reconcile(file, workspace_root) before delivering Python changes; audit shell/code with audit(). Read ONLY the verdict field — valid:true with verdict:unverifiable means human confirmation required.
---

# SWDA Delivery Gate (prime-agent skill)

Thin wrapper over the `swda-mcp` MCP server (stdio, stateless). The kernel
pre-imports `mcp`; this package exposes two typed async callables.

```python
import swda
verdict = await swda.reconcile("src/foo.py", "/path/to/repo")
# {"valid": ..., "verdict": "valid|unverifiable|invalid", "errors": [...], "warnings": [...]}

gate = await swda.audit(command="pytest -q")
# {"allowed": bool, "rule_id": str, "message": str}
```

Gate policy: `verdict` is authoritative. `valid:true` with
`verdict:"unverifiable"` means human confirmation is required — do NOT treat
it as clean. `verdict:"invalid"` returns the task to rework.

Setup (one-time, outside the kernel):

```bash
export SWDA_REPO=/Users/carlos/pywork/swarm-driven-agent
export PYTHONPATH=/Users/carlos/pywork/swarm-driven-agent
prime-agent mcp add swda --cwd /Users/carlos/pywork/swarm-driven-agent/swda-mcp \
  --env SWDA_REPO=SWDA_REPO --env PYTHONPATH=PYTHONPATH \
  -- /Users/carlos/miniconda3/bin/python3 -m swda_mcp.server
```

See `references/wiring.md` for the settings.json shape and troubleshooting.

## Optional: Jev intent hint (CLI)

`swda jev-intent "<request>"` prints a classification string, `unsure`, or
`none` (no Jev key configured). Treat it as an optional hint for INTENT_GATE;
`none` or `unsure` means classify with your own judgment as before.
