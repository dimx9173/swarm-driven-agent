"""SWDA MCP server: thin stdio bridge exposing stateless SWDA tools.

Tools (all synchronous, side-effect free):
  swda_reconcile      AST hallucinated-symbol check at the delivery gate.
  swda_firewall_audit TC-01~05/07 + RULE-0.7 command/code audit.
  swda_stats          Telemetry summary snapshot.
  swda_models         Live gateway model ids.

Deliberately NOT exposed: run (229s stateful LLM loop), refine (file
side effects), repl (persistent process semantics).

Usage (conda python with mcp SDK):
  python3 -m swda_mcp.server
"""

import os
import sys

_REPO = os.environ.get("SWDA_REPO") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
from mcp.server.fastmcp import FastMCP

from swda.core.firewall import SafetyFirewall, SecurityFirewallException
from swda.prime.rlm import RLMDispatcher
from swda.telemetry import TelemetryLogger
from swda.workflows.reconcile import ReverseReconciliation

mcp = FastMCP("swda")


@mcp.tool()
def swda_reconcile(file: str, workspace_root: str = "") -> dict:
    """Check a Python file for hallucinated imports/APIs before delivery.

    Returns {"valid": bool, "imported_modules": [...], "errors": [...]}.
    """
    root = workspace_root or os.getcwd()
    return ReverseReconciliation.verify_file(file, root)


@mcp.tool()
def swda_firewall_audit(command: str = "", code: str = "", phase: str = "") -> dict:
    """Audit a shell command and/or Python code block against SWDA firewall.

    Returns {"allowed": bool, "rule_id": str, "message": str}.
    """
    try:
        if command:
            SafetyFirewall.audit_command(command)
        if code:
            SafetyFirewall.audit_code_ast(code, phase or None)
    except SecurityFirewallException as e:
        return {"allowed": False, "rule_id": e.rule_id, "message": e.message}
    return {"allowed": True, "rule_id": "", "message": "ok"}


@mcp.tool()
def swda_stats() -> dict:
    """Return the SWDA telemetry summary snapshot."""
    return TelemetryLogger().get_summary()


@mcp.tool()
def swda_models() -> dict:
    """List live model ids from the configured OpenAI-compatible gateway."""
    rlm = RLMDispatcher()
    try:
        models = rlm.list_models()
    except RuntimeError as e:
        return {"endpoint": rlm.api_base, "default": rlm.default_model, "error": str(e)}
    return {"endpoint": rlm.api_base, "default": rlm.default_model, "models": models}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
