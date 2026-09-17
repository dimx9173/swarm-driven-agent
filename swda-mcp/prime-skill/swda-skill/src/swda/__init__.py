"""SWDA delivery-gate skill for prime-agent kernels.

Calls the `swda-mcp` MCP server through the kernel pre-imported `mcp`
module. Gate policy: `verdict` is authoritative; `valid:true` with
`verdict:"unverifiable"` requires human confirmation.
"""
from typing import Any, Dict


async def run(file: str, workspace_root: str) -> Dict[str, Any]:
    """Alias for reconcile: check one Python file, return the verdict dict."""
    return await reconcile(file, workspace_root)


async def reconcile(file: str, workspace_root: str) -> Dict[str, Any]:
    """Check a Python file for hallucinated imports/APIs before delivery."""
    import mcp
    return await mcp.call_tool(
        "swda", "swda_reconcile",
        {"file": file, "workspace_root": workspace_root},
    )


async def audit(command: str = "", code: str = "", phase: str = "") -> Dict[str, Any]:
    """Audit a shell command and/or Python code block against the SWDA firewall."""
    import mcp
    return await mcp.call_tool(
        "swda", "swda_firewall_audit",
        {"command": command, "code": code, "phase": phase},
    )
