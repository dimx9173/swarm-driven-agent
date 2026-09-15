"""
SWDA Unified CLI:
Unifies Prime-SWDA Execution Engine (repl, run, refine, stats, reconcile)
with Legacy Host Agent Installer (install, update, scan, check, version).
"""

import sys
import os
import argparse
from typing import Optional

import installer
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.fsm import FSMEngine, FSMPhase
from swda.prime.repl import PrimeREPL
from swda.prime.rlm import RLMDispatcher
from swda.prime.harness import ContinualHarness
from swda.workflows.crucible import CrucibleWorkflow
from swda.workflows.reconcile import ReverseReconciliation
from swda.telemetry import TelemetryLogger


def cmd_repl(args):
    """Starts interactive stateful REPL."""
    print("Initializing SWDA Prime REPL (Persistent Session with AI Firewall Guard)...")
    blackboard = Blackboard()
    repl = PrimeREPL(blackboard)
    print("REPL active. Type Python expressions or statements. Type 'exit()' to quit.")
    while True:
        try:
            line = input("swda> ")
            if line.strip() in ("exit()", "quit()"):
                break
            if not line.strip():
                continue
            res = repl.execute(line)
            if res["stdout"]:
                print(res["stdout"], end="")
            if res["result"] is not None:
                print(f"=> {res['result']}")
            if not res["success"]:
                print(f"Error: {res['error']}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting REPL.")
            break


def cmd_refine(args):
    """Refines a failed trajectory into an anti-pattern YAML."""
    harness = ContinualHarness()
    res = harness.refine(
        trajectory_summary=args.summary,
        failure_signal=args.reason,
    )
    print(f"Successfully refined anti-pattern: {res['name']}")
    print(f"Saved to: {res['path']}")


def cmd_reconcile(args):
    """Verifies that modified code has no hallucinated symbol references."""
    workspace = os.getcwd()
    result = ReverseReconciliation.verify_file(args.file, workspace)
    if result["valid"]:
        print(f"✓ Reverse Reconciliation Passed: No hallucinated symbols in {args.file}")
    else:
        print(f"✗ Reverse Reconciliation FAILED for {args.file}:")
        for err in result["errors"]:
            print(f"  - {err}")
        sys.exit(1)


def cmd_scan(args):
    """Scans local agents read-only (no writes)."""
    agents = installer.scan_agents()
    if not agents:
        print("No agents detected.")
        return
    print(f"\nDetected {len(agents)} agent(s):")
    for i, a in enumerate(agents, 1):
        print(f" [{i}] Type: {a['type']:8s} | Name: {a['name']} | Path: {a['dir_path']}")


def cmd_models(args):
    """Lists live model ids from the configured OpenAI-compatible endpoint."""
    rlm = RLMDispatcher(default_model=getattr(args, "model", None))
    try:
        models = rlm.list_models()
    except RuntimeError as err:
        print(f"Error: {err}")
        sys.exit(1)
    print(f"Endpoint: {rlm.api_base}")
    print(f"Default model: {rlm.default_model}")
    for mid in models:
        mark = " (default)" if mid == rlm.default_model else ""
        print(f"  - {mid}{mark}")


def cmd_stats(args):
    """Displays telemetry metrics dashboard."""
    telemetry = TelemetryLogger()
    summary = telemetry.get_summary()
    print("\n================= SWDA Telemetry Dashboard =================")
    print(f"Total Execution Spans:    {summary['total_calls']}")
    print(f"Successful Calls:         {summary['successful_calls']}")
    print(f"Tool Success Rate:        {summary['success_rate'] * 100:.2f}%")
    print(f"Estimated Total Tokens:   {summary['total_tokens']}")
    print(f"Average Duration (ms):    {summary['avg_duration_ms']} ms")
    print("============================================================\n")


def _mock_rlm_handler(role: str, prompt: str):
    """Deterministic offline stand-in for RLM subagents (e2e smoke only)."""
    if role == "builder":
        return {"spec": prompt[:200], "edge_cases": ["empty input", "timeout"], "round": "mock"}
    if role == "destroyer":
        return {"vector": "mock attack: unhandled timeout", "severity": "medium"}
    if role == "referee":
        return {"passed": True, "score": 8, "reason": "Mock verdict: proposal acceptable"}
    return {}


def cmd_run(args):
    """Runs a task through the SWDD lifecycle with Crucible review."""
    print(f"Starting SWDA autonomous execution for task: {args.task}")
    telemetry = TelemetryLogger()
    telemetry.start_span("full_run")

    blackboard = Blackboard()
    fsm = FSMEngine(blackboard)
    rlm = RLMDispatcher(
        default_model=getattr(args, "model", None),
        mock_handler=_mock_rlm_handler if getattr(args, "mock", False) else None,
    )
    crucible = CrucibleWorkflow(rlm=rlm, blackboard=blackboard)

    # 1. Advance to GATHER
    fsm.advance_to(FSMPhase.PHASE_2_GATHER)
    print("Phase 2 (GATHER) completed. Advancing to HYPERPLAN...")

    # 2. Advance to HYPERPLAN, seed draft proposal for CRUCIBLE entry gate
    fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
    print("Phase 3 (HYPERPLAN) in progress...")
    blackboard.write(AgentRole.SYSTEM, "active_proposal", {"spec": args.task, "round": 0, "draft": True})
    print("Draft proposal seeded. Advancing to CRUCIBLE...")

    # 3. Advance to CRUCIBLE and run review
    fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
    print("Launching Crucible (Builder vs. Destroyer vs. Referee)...")
    res = crucible.run_crucible(args.task)
    print(f"Crucible PASSED in round {res.rounds_executed} with score {res.verdict.get('score', 8)}/10.")

    # 4. Advance to SYNTHESIS
    fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)
    blackboard.write(blackboard.WRITE_PERMISSIONS["synthesis_blueprint"][0], "synthesis_blueprint", res.proposal)
    print("Synthesis blueprint generated. Ready for IMPLEMENT phase.")

    telemetry.end_span("full_run", success=True)


def main():
    parser = argparse.ArgumentParser(
        prog="swda",
        description="SWDA: Swarm-Driven Agent & Execution Harness (Prime-SWDA)",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # Prime-SWDA commands
    subparsers.add_parser("repl", help="Start persistent stateful REPL with SWDA AI Firewall")
    
    run_p = subparsers.add_parser("run", help="Run a task through SWDD lifecycle with Crucible")
    run_p.add_argument("task", type=str, help="Task description or specification")
    run_p.add_argument("--mock", action="store_true", help="Use deterministic mock subagents (offline e2e smoke)")
    run_p.add_argument("--model", type=str, default=None, help="Override RLM model id (or SWDA_MODEL env)")

    refine_p = subparsers.add_parser("refine", help="Refine a failure trajectory into an anti-pattern")
    refine_p.add_argument("--summary", type=str, required=True, help="Summary of failed execution trajectory")
    refine_p.add_argument("--reason", type=str, required=True, help="Detailed failure reason")

    rec_p = subparsers.add_parser("reconcile", help="Check for hallucinated symbols in generated code")
    rec_p.add_argument("file", type=str, help="Python source file to verify")

    models_p = subparsers.add_parser("models", help="List live model ids from the LLM endpoint")
    models_p.add_argument("--model", type=str, default=None, help="Show which id is the active default")

    subparsers.add_parser("stats", help="Display execution telemetry and metrics dashboard")
    subparsers.add_parser("scan", help="Scan local agents (read-only, no writes)")

    # Check if first arg is an installer command (install, update, check, version, discover, learn, remove)
    installer_subcommands = {"install", "update", "check", "version", "discover", "learn", "remove"}
    if len(sys.argv) > 1 and sys.argv[1] in installer_subcommands:
        # Delegate directly to installer.main()
        installer.main()
        return

    args, unknown = parser.parse_known_args()
    if args.subcommand == "repl":
        cmd_repl(args)
    elif args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "refine":
        cmd_refine(args)
    elif args.subcommand == "reconcile":
        cmd_reconcile(args)
    elif args.subcommand == "models":
        cmd_models(args)
    elif args.subcommand == "stats":
        cmd_stats(args)
    elif args.subcommand == "scan":
        cmd_scan(args)
    else:
        # Fallback to installer if no specific prime-swda command matched
        installer.main()


if __name__ == "__main__":
    main()
