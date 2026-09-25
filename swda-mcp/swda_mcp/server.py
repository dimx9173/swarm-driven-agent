"""SWDA MCP server: thin stdio bridge exposing stateless SWDA tools.

Tools (all synchronous, side-effect free):
  swda_reconcile      AST hallucinated-symbol check at the delivery gate.
  swda_firewall_audit TC-01~05/07 + RULE-0.7 command/code audit.
  swda_stats          Telemetry summary snapshot.
  swda_models         Live gateway model ids.
  swda_judge          Governed Jev judgment over untrusted pipeline state.

Deliberately NOT exposed: run (229s stateful LLM loop), refine (file
side effects), repl (persistent process semantics).

Usage (conda python with mcp SDK):
  python3 -m swda_mcp.server
"""

import os
import sys
from typing import Tuple

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

    Returns {"valid": bool, "verdict": "valid|unverifiable|invalid",
    "imported_modules": [...], "errors": [...], "warnings": [...]}.
    Gate policy: `verdict` is authoritative; `valid` is a compat key that
    stays True for `unverifiable`. Do NOT treat `valid:true` as clean when
    `verdict` is `unverifiable` — that means human confirmation is required.
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


#: Classification tokens mirrored from swda/workflows/crucible.py
#: (_classify_jev_answer); duplicated here because crucible imports are too
#: heavy for this thin bridge.
_PASS_TOKENS = frozenset({"pass", "yes", "true"})
_FAIL_TOKENS = frozenset({"fail", "no", "false"})


def _classify_answer(answer) -> "Tuple[str, str]":
    """Three-valued classification of one Jev answer -> (action, reason).

    Same semantics as crucible._classify_jev_answer: abstain covers missing,
    malformed, escalated (low-confidence), and unsure answers so a degraded
    or flaky judge can never produce an auto-pass.
    """
    if not answer:
        return "abstain", "missing_answer"
    raw = str(getattr(answer, "answer", "")).strip().lower()
    recognized = raw in _PASS_TOKENS or raw in _FAIL_TOKENS or raw == "unsure"
    noul = None
    if not recognized:
        try:
            noul = float(raw)  # check() primitive answers with a 0.0-1.0 float
        except ValueError:
            return "abstain", "malformed_answer"
    if getattr(answer, "escalate", False) is True:
        return "abstain", "low_confidence"
    if raw in _PASS_TOKENS:
        return "support", "choice_yes"
    if raw in _FAIL_TOKENS:
        return "contest", "choice_no"
    if noul is not None:
        if noul >= 0.5:
            return "support", "noul_above_threshold"
        return "contest", "noul_below_threshold"
    return "abstain", "unsure_no_escalate"


@mcp.tool()
def swda_judge(state: dict, questions: dict, question_specs: dict = None) -> dict:
    """Judge assertions/evidence with the optional TypeSafe Jev guard.

    Thin bridge over swda.prime.jev.judge: `state` is untrusted pipeline
    content (jev injects its own anti-injection preamble, bounds the payload,
    and redacts errors), and every failure degrades fail-closed — the tool
    never raises and never auto-passes on `unverifiable`.

    Args:
      state: JSON-serializable dict of assertions/evidence to judge.
      questions: caller-friendly mapping of question id -> plain-string
        description of what to judge; each description becomes a `noul`
        (0.0-1.0 probability) question via jev.check().
      question_specs: optional mapping of question id -> full wire spec
        ({"type": "choice|score|noul", "instructions": ..., "criteria": ...})
        for callers that control the primitive and criteria directly. When
        BOTH `questions` and `question_specs` are provided, `question_specs`
        takes precedence and `questions` is ignored (documented contract).
        Each entry must be a dict with a known `type` and `instructions`;
        invalid entries degrade to invalid/escalate.
    Returns {"tool", "verdict": "valid|invalid|unverifiable",
    "action": "auto|escalate|abstain", "confidence" (min across answers),
    "answers": {id: {"answer", "confidence", "action", "reason"}},
    "error"}: any contested answer -> invalid/escalate; else any abstained
    answer -> unverifiable/abstain; else valid/auto.
    """
    from swda.prime import jev  # lazy: keep module import cost unchanged

    try:
        if not questions and not question_specs:
            return {
                "tool": "swda_judge",
                "verdict": "unverifiable",
                "action": "abstain",
                "confidence": None,
                "answers": {},
                "error": "no questions provided (need `questions` or `question_specs`)",
            }
        if question_specs:
            specs = {}
            for qid, spec in question_specs.items():
                if (not isinstance(spec, dict)
                        or spec.get("type") not in ("choice", "score", "noul")
                        or not spec.get("instructions")):
                    raise ValueError(
                        f"invalid question_specs[{qid!r}]: need a dict with "
                        f"type (choice|score|noul) + instructions"
                    )
                specs[str(qid)] = dict(spec)
        else:
            if not isinstance(questions, dict):
                raise ValueError(
                    "questions must be a dict of question id -> description, "
                    f"got {type(questions).__name__}"
                )
            specs = {str(qid): jev.check(str(desc))
                     for qid, desc in questions.items()}
        # jev.judge wraps non-dict state as {"input": state} itself; do not
        # duplicate that handling here.
        answers = jev.judge(state, specs)
        if not answers:
            # Fail-closed: unverifiable, never auto-pass. last_error() is
            # already redacted at the source by judge().
            return {
                "tool": "swda_judge",
                "verdict": "unverifiable",
                "action": "abstain",
                "confidence": None,
                "answers": {},
                "error": jev.last_error(),
            }
        per_question = {}
        confidences = []
        saw_contest = saw_abstain = False
        for qid, ans in answers.items():
            action, reason = _classify_answer(ans)
            raw_conf = getattr(ans, "confidence", None)
            conf = (float(raw_conf)
                    if isinstance(raw_conf, (int, float)) and not isinstance(raw_conf, bool)
                    else None)
            if conf is not None:
                confidences.append(conf)
            saw_contest = saw_contest or action == "contest"
            saw_abstain = saw_abstain or action == "abstain"
            per_question[str(qid)] = {
                "answer": str(getattr(ans, "answer", "")),
                "confidence": conf,
                "action": action,
                "reason": reason,
            }
        if saw_contest:
            verdict, action = "invalid", "escalate"
        elif saw_abstain:
            verdict, action = "unverifiable", "abstain"
        else:
            verdict, action = "valid", "auto"
        return {
            "tool": "swda_judge",
            "verdict": verdict,
            "action": action,
            "confidence": min(confidences) if confidences else None,
            "answers": per_question,
            "error": None,
        }
    except Exception as e:
        # Tool-argument problems (non-dict inputs, invalid spec entries)
        # degrade to invalid/escalate instead of raising into the MCP layer;
        # the message is kept as-is because tool args never contain the API
        # key (jev redacts its own judge() errors at the source).
        return {
            "tool": "swda_judge",
            "verdict": "invalid",
            "action": "escalate",
            "confidence": None,
            "answers": {},
            "error": str(e) or type(e).__name__,
        }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
