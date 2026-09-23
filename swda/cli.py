"""
SWDA Unified CLI:
Unifies Prime-SWDA Execution Engine (repl, run, refine, stats, reconcile)
with Legacy Host Agent Installer (install, update, scan, check, version).
"""

import sys
import os
import argparse
from typing import Optional

from swda.core.blackboard import Blackboard, AgentRole
from swda.core.fsm import FSMEngine, FSMPhase
from swda.core.circuit_breaker import CircuitBreakerException, StepCounter
from swda.core.hooks import HookRegistry, PRE_TOOL_USE
from swda.prime.jev import is_enabled, intent_hint, jev_pre_tool_hook
from swda.prime.repl import PrimeREPL
from swda.prime.rlm import RLMDispatcher
from swda.prime.harness import ContinualHarness
from swda.workflows.crucible import CrucibleWorkflow
from swda.workflows.reconcile import ReverseReconciliation
from swda.workflows.harness_walk import check_contract_binding, check_mcp_registration, scan_session_file
from swda.telemetry import TelemetryLogger


def _jev_gate_registry(enabled: bool) -> Optional[HookRegistry]:
    """Builds the Jev PreToolUse guard registry; None when the gate is off."""
    if not enabled:
        return None
    registry = HookRegistry()
    registry.register(PRE_TOOL_USE, jev_pre_tool_hook)
    return registry


def _print_jev_banner():
    """Prints the active Jev status so users can see which path runs."""
    from swda.prime.jev import _provider_config, is_enabled
    if is_enabled():
        base_url, _key, model, _path = _provider_config()
        print(f"Jev: ON (provider={base_url}, model={model})")
    else:
        print("Jev: OFF (default agent judgment)")


def _print_jev_detail():
    """With --verbose, reports why the last judge() call degraded."""
    from swda.prime.jev import last_error
    reason = last_error()
    if reason:
        print(f"Jev detail: {reason}")



def _jev_round_reporter():
    """Builds the per-round Crucible observer used by --verbose."""
    def report(info):
        rnd = info.get("round")
        if not info.get("jev_enabled"):
            print(f"Jev round {rnd}: OFF (LLM verdict only, passed={info.get('passed')})")
            return
        answer = info.get("jev_verdict")
        if answer is None:
            reason = info.get("jev_error")
            if not reason:
                reason = ("LLM verdict already failed; Jev not consulted"
                          if not info.get("passed") else "no answer returned")
            print(f"Jev round {rnd}: skipped ({reason})")
            return
        print(f"Jev round {rnd}: answer={getattr(answer, 'answer', answer)!r} "
              f"conf={getattr(answer, 'confidence', 0):.2f} "
              f"score={info.get('jev_score')} passed={info.get('passed')}")
    return report


def cmd_repl(args):
    """Starts interactive stateful REPL."""
    print("Initializing SWDA Prime REPL (Persistent Session with AI Firewall Guard)...")
    _print_jev_banner()
    blackboard = Blackboard()
    hooks = _jev_gate_registry(getattr(args, "jev_gate", False))
    repl = PrimeREPL(blackboard, hooks=hooks)
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
    verdict = result.get("verdict", "valid" if result["valid"] else "invalid")
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({"file": args.file, "verdict": verdict,
                           "errors": result.get("errors", []),
                           "warnings": result.get("warnings", [])}, ensure_ascii=False))
        sys.exit(0 if verdict == "valid" else (2 if verdict == "unverifiable" else 1))
    if verdict == "valid":
        print(f"✓ Reverse Reconciliation Passed: No hallucinated symbols in {args.file}")
    elif verdict == "unverifiable":
        print(f"◐ Reverse Reconciliation UNVERIFIABLE for {args.file} (needs human confirmation):")
        for warn in result.get("warnings", []):
            print(f"  - {warn}")
        sys.exit(2)
    else:
        print(f"✗ Reverse Reconciliation FAILED for {args.file}:")
        for err in result.get("errors", []):
            print(f"  - {err}")
        sys.exit(1)

def cmd_verify_session(args):
    """Proves an OMP session walked the SWDA harness (scan + verdict)."""
    if not os.path.exists(args.session):
        print(f"Error: session file not found: {args.session}", file=sys.stderr)
        sys.exit(2)
    res = scan_session_file(args.session)
    print(f"Session: {args.session}")
    print(f"Level:   {res['level']} ({'PASSED' if res['passed'] else 'FAILED'})")
    print(f"Python modifications: {res['py_modifications']}")
    print(f"Reconcile calls:      {res['reconcile_count']} (verdicts: {res['gate_verdicts']})")
    if res.get("unverified"):
        print(f"Unverified gates:     {len(res['unverified'])} (needs human confirmation)")
    print(f"Firewall calls:       {res['firewall_count']}")
    print(f"FSM tags:             " + ", ".join(f"{k}={v}" for k, v in res['fsm_tags'].items()))
    print(f"NEXT_STATE count:     {res['next_state_count']}")
    ok = res["passed"]
    if getattr(args, "mcp_json", None):
        reg = check_mcp_registration(args.mcp_json)
        print(f"MCP swda-mcp:         {'registered' if reg['registered'] else 'MISSING'}")
        for r in reg["reasons"]:
            print(f"  - {r}")
        ok = ok and reg["registered"]
    if getattr(args, "contract", None):
        gate = check_contract_binding(args.contract)
        print(f"Contract binding:     {'ok' if gate['ok'] else 'BROKEN'}")
        for r in gate["reasons"]:
            print(f"  - {r}")
        ok = ok and gate["ok"]
    for m in res["missing"]:
        print(f"  ! {m}")
    if getattr(args, "strict", False) and res.get("unverified"):
        print(f"Strict: {len(res['unverified'])} unverified gate(s) require human confirmation", file=sys.stderr)
        ok = False
    if not ok:
        sys.exit(1)


def cmd_scan(args):
    """Scans local agents read-only (no writes)."""
    import installer
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
    print(f"Estimated Total Tokens:   {summary['total_tokens']} (live LLM token accounting not yet wired)")
    print(f"Average Duration (ms):    {summary['avg_duration_ms']} ms")
    for bucket in ("mock", "real"):
        sub = summary.get(bucket)
        if sub:
            print(f"  [{bucket}] spans={sub['total_calls']} ok={sub['successful_calls']} "
                  f"rate={sub['success_rate'] * 100:.2f}% avg_ms={sub['avg_duration_ms']}")
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


def cmd_jev_intent(args):
    """Classifies a request intent via Jev (optional, graceful degradation)."""
    _print_jev_banner()
    hint = intent_hint(args.request)
    print(hint if hint is not None else "none")
    if getattr(args, "verbose", False):
        _print_jev_detail()


def cmd_run(args):
    """Runs a task through the SWDD lifecycle with Crucible review."""
    print(f"Starting SWDA autonomous execution for task: {args.task}")
    _print_jev_banner()
    telemetry = TelemetryLogger()
    telemetry.start_span("full_run")

    blackboard = Blackboard()
    # Single shared StepCounter: the global + per-phase budgets now span the
    # whole run (FSM transitions and Crucible rounds share one budget clock).
    step_counter = StepCounter()
    fsm = FSMEngine(blackboard, step_counter=step_counter)
    from swda.workflows.tdd_runner import set_default_hooks
    # Process-wide hooks must reflect THIS run: install when --jev-gate is
    # passed, clear otherwise (sequential in-process runs stay isolated).
    set_default_hooks(_jev_gate_registry(getattr(args, "jev_gate", False)))
    rlm = RLMDispatcher(
        default_model=getattr(args, "model", None),
        mock_handler=_mock_rlm_handler if getattr(args, "mock", False) else None,
    )
    crucible = CrucibleWorkflow(
        rlm=rlm, blackboard=blackboard, step_counter=step_counter,
        on_round=_jev_round_reporter() if getattr(args, "verbose", False) else None,
    )

    try:
        # 1. Advance to GATHER
        fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        print("Phase 2 (GATHER) completed. Advancing to HYPERPLAN...")

        # 2. Advance to HYPERPLAN, seed draft proposal for CRUCIBLE entry gate
        fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        print("Phase 3 (HYPERPLAN) in progress...")
        blackboard.write(AgentRole.SYSTEM, "active_proposal", {"spec": args.task, "round": 0, "draft": True})
        fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
        print("Launching Crucible (Builder vs. Destroyer vs. Referee)...")
        res = crucible.run_crucible(args.task)
        print(f"Crucible PASSED in round {res.rounds_executed} with score {res.verdict.get('score', 8)}/10.")

        # 4. Advance to SYNTHESIS
        fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)
        blackboard.write(AgentRole.BUILDER, "synthesis_blueprint", res.proposal)
        print("Synthesis blueprint generated. Ready for IMPLEMENT phase.")
    except CircuitBreakerException as breaker_err:
        # Map the breaker to the contract's HITL_SUSPEND state instead of a
        # bare traceback: emit <BUDGET_EXHAUSTION_REPORT> then suspend.
        print("<BUDGET_EXHAUSTION_REPORT>")
        print(f"EXHAUSTED_PHASE: {breaker_err.phase}")
        print(f"STEP_COUNT_REACHED: {breaker_err.step_count}/{breaker_err.max_limit}")
        print(f"REASON: {breaker_err.reason}")
        print("</BUDGET_EXHAUSTION_REPORT>")
        fsm.advance_to(FSMPhase.HITL_SUSPEND)
        print("[NEXT_STATE: HITL_SUSPEND | Budget Exhausted]")
        telemetry.end_span("full_run", success=False,
                           metadata={"mock": bool(getattr(args, "mock", False)),
                                     "model": getattr(args, "model", None) or rlm.default_model})
        if getattr(args, "json", False):
            import json as _json
            print(_json.dumps({
                "task": args.task,
                "passed": False,
                "phase": FSMPhase.HITL_SUSPEND.value,
                "exhausted_phase": breaker_err.phase,
                "mock": bool(getattr(args, "mock", False)),
            }, ensure_ascii=False))
        sys.exit(3)
    except Exception:
        telemetry.end_span("full_run", success=False,
                           metadata={"mock": bool(getattr(args, "mock", False)),
                                     "model": getattr(args, "model", None) or rlm.default_model})
        raise

    telemetry.end_span("full_run", success=True,
                       metadata={"mock": bool(getattr(args, "mock", False)),
                                 "model": getattr(args, "model", None) or rlm.default_model})
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({
            "task": args.task,
            "passed": True,
            "phase": fsm.current_phase.value,
            "rounds_executed": res.rounds_executed,
            "score": res.verdict.get("score"),
            "mock": bool(getattr(args, "mock", False)),
            "model": getattr(args, "model", None) or rlm.default_model,
        }, ensure_ascii=False))
    if getattr(args, "verbose", False):
        _print_jev_detail()


def main():
    parser = argparse.ArgumentParser(
        prog="swda",
        description="SWDA: Swarm-Driven Agent & Execution Harness (Prime-SWDA)",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # Prime-SWDA commands
    repl_p = subparsers.add_parser("repl", help="Start persistent stateful REPL with SWDA AI Firewall")
    repl_p.add_argument("--jev-gate", action="store_true",
                        help="Enable Jev probabilistic guard for tool execution")
    repl_p.add_argument("--verbose", action="store_true",
                        help="Explain why Jev degraded (HTTP status, unknown model, network)")

    run_p = subparsers.add_parser("run", help="Run a task through SWDD lifecycle with Crucible")
    run_p.add_argument("task", type=str, help="Task description or specification")
    run_p.add_argument("--mock", action="store_true", help="Use deterministic mock subagents (offline e2e smoke)")
    run_p.add_argument("--json", action="store_true", help="Emit machine-readable result JSON (for CI)")
    run_p.add_argument("--model", type=str, default=None, help="Override RLM model id (or SWDA_MODEL env)")
    run_p.add_argument("--jev-gate", action="store_true",
                       help="Enable Jev probabilistic guard for tool execution")
    run_p.add_argument("--verbose", action="store_true",
                       help="Explain why Jev degraded (HTTP status, unknown model, network)")

    refine_p = subparsers.add_parser("refine", help="Refine a failure trajectory into an anti-pattern")
    refine_p.add_argument("--summary", type=str, required=True, help="Summary of failed execution trajectory")
    refine_p.add_argument("--reason", type=str, required=True, help="Detailed failure reason")

    rec_p = subparsers.add_parser("reconcile", help="Check for hallucinated symbols in generated code")
    rec_p.add_argument("file", type=str, help="Python source file to verify")
    rec_p.add_argument("--json", action="store_true", help="Emit machine-readable verdict JSON (for scanners)")

    models_p = subparsers.add_parser("models", help="List live model ids from the LLM endpoint")
    models_p.add_argument("--model", type=str, default=None, help="Show which id is the active default")

    subparsers.add_parser("stats", help="Display execution telemetry and metrics dashboard")
    subparsers.add_parser("scan", help="Scan local agents (read-only, no writes)")

    ver_p = subparsers.add_parser("verify-session", help="Prove an OMP session walked the SWDA harness")
    ver_p.add_argument("session", type=str, help="OMP session .jsonl file to scan")
    ver_p.add_argument("--contract", type=str, default=None, help="Also verify the delivery-gate binding in this contract file")
    ver_p.add_argument("--strict", action="store_true", help="Fail on any unverified gate (needs human confirmation)")

    jev_intent_p = subparsers.add_parser("jev-intent",
                                         help="Classify request intent via Jev (optional)")
    jev_intent_p.add_argument("request", type=str, help="User request to classify")
    jev_intent_p.add_argument("--verbose", action="store_true",
                              help="Explain why Jev degraded (HTTP status, unknown model, network)")

    # Check if first arg is an installer command (install, update, check, version, discover, learn, remove)
    installer_subcommands = {"install", "update", "self-update", "doctor", "version", "discover", "learn"}
    if len(sys.argv) > 1 and sys.argv[1] in installer_subcommands:
        # Delegate directly to installer.main()
        import installer
        installer.main()
        return

    args = parser.parse_args()
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
    elif args.subcommand == "verify-session":
        cmd_verify_session(args)
    elif args.subcommand == "jev-intent":
        cmd_jev_intent(args)
    else:
        # Fallback to installer if no specific prime-swda command matched
        import installer
        installer.main()


if __name__ == "__main__":
    main()
