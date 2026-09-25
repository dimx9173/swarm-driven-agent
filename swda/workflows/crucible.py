"""
SWDA Programmatic Crucible: Asymmetric Adversarial Specification Hardening.
Executes Builder vs. Destroyer vs. Referee inside an RLM loop, bounded by circuit breakers.
"""

import json
import re
from typing import Dict, Any, Optional, List, Tuple
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.circuit_breaker import StepCounter, CircuitBreakerException
from swda.prime import jev
from swda.prime.rlm import RLMDispatcher


_PASS_TOKENS = frozenset({"pass", "yes", "true"})
_FAIL_TOKENS = frozenset({"fail", "no", "false"})


def _classify_jev_answer(answer: Optional[dict]) -> Tuple[str, str]:
    """Three-valued classification of the Jev 'pass' answer.

    Returns (action, reason_code) with action in {"support", "contest",
    "abstain"}: abstain covers missing, malformed, low-confidence (escalated)
    and unsure answers, so a degraded or flaky judge can never move a
    verdict. Uses only signals the model already emits (answer, noul,
    escalate) — no new threshold machinery.
    """
    if not answer:
        return "abstain", "missing_answer"
    raw = str(getattr(answer, "answer", "")).strip().lower()
    recognized = raw in _PASS_TOKENS or raw in _FAIL_TOKENS or raw == "unsure"
    noul: Optional[float] = None
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
    return "abstain", "unsure_no_escalate"  # well-formed "unsure" below the confidence gate


def _arbitrate_verdict(verdict: Dict[str, Any], jev_answers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Applies Jev arbitration: fail closed ONLY when Jev actively and confidently
    disagrees with an LLM-passed verdict. Support and abstain (missing,
    malformed, or escalated/low-confidence answers) return the original
    verdict object unchanged; an LLM-failed verdict stays failed.
    """
    if not jev_answers:
        return verdict
    answer = jev_answers.get("pass")
    action, reason_code = _classify_jev_answer(answer)
    if action != "contest" or not verdict.get("passed"):
        return verdict
    outcome = dict(verdict)
    raw = str(getattr(answer, "answer", "")).strip().lower()
    try:
        outcome["jev_score"] = float(raw)  # noul 0.0-1.0 pass probability
    except ValueError:
        outcome["jev_score"] = 0.0
    outcome["jev_confidence"] = getattr(answer, "confidence", None)
    outcome["jev_action"] = action
    outcome["jev_reason"] = reason_code
    outcome["passed"] = False
    base = str(verdict.get("reason", ""))
    suffix = " | Jev disagreed with the pass verdict - LLM re-review required."
    outcome["reason"] = (base + suffix).strip() if base else suffix.lstrip(" |")
    return outcome


class CrucibleResult:
    """Outcome of a Crucible review workflow."""
    def __init__(
        self,
        passed: bool,
        proposal: Dict[str, Any],
        verdict: Dict[str, Any],
        rounds_executed: int,
        critiques: List[Dict[str, Any]],
    ):
        self.passed = passed
        self.proposal = proposal
        self.verdict = verdict
        self.rounds_executed = rounds_executed
        self.critiques = critiques


class CrucibleWorkflow:
    """
    Automates the Crucible dialectic review loop without manual prompt interleaving.
    """

    def __init__(
        self,
        rlm: RLMDispatcher,
        blackboard: Blackboard,
        step_counter: Optional[StepCounter] = None,
        max_rounds: int = 3,
        on_round: Optional[Any] = None,
        use_jev: Optional[bool] = None,
    ):
        self.rlm = rlm
        self.blackboard = blackboard
        self.step_counter = step_counter or StepCounter()
        self.max_rounds = max_rounds
        # Optional observer called after each round's arbitration with a dict
        # {round, passed, jev_enabled, jev_verdict, jev_score, jev_confidence,
        #  jev_error}. Default None = zero behavior change.
        self.on_round = on_round
        # None = auto (arbitrate whenever a Jev key is configured). False forces
        # the run hermetic, so offline/mock runs never call the live judge.
        self.use_jev = use_jev

    def _jev_active(self) -> bool:
        """True when this run may consult the Jev judge."""
        if self.use_jev is False:
            return False
        return jev.is_enabled()

    def run_crucible(self, task_spec: str, context: Optional[Dict[str, Any]] = None) -> CrucibleResult:
        """
        Executes iterative Crucible rounds until Referee approves or circuit breaker trips.

        Role isolation: Builder sees the task plus a digest of prior rounds
        (never raw Destroyer monologue); Destroyer sees the current proposal
        only; Referee sees proposal + critique digest plus a reconcile re-run
        verdict when the proposal names Python files.
        """
        all_critiques = []
        current_proposal = {"spec": task_spec, "round": 0}

        for round_idx in range(1, self.max_rounds + 1):
            self.step_counter.record_step("PHASE_4_CRUCIBLE")

            # 1. Builder develops/sharpens proposal (digest only, no raw critique)
            builder_prompt = (
                f"Task: {task_spec}\n"
                f"Previous round digests: {self._digest_critiques(all_critiques)}\n"
                "Propose a formal Spec with explicit edge cases, data structures, and trade-offs."
            )
            raw_proposal = self.rlm.spawn(
                role=AgentRole.BUILDER.value,
                prompt=builder_prompt,
                context=self._role_context(context, AgentRole.BUILDER.value),
            )
            current_proposal = (
                raw_proposal if isinstance(raw_proposal, dict) else {"content": raw_proposal, "round": round_idx}
            )
            self.blackboard.write(AgentRole.BUILDER, "active_proposal", current_proposal)

            # 2. Destroyer attacks (proposal only, no task context bleed)
            destroyer_prompt = (
                f"Proposal: {self._proposal_brief(current_proposal)}\n"
                "Attack with falsifiable vectors: race conditions, resource leaks, edge errors, fake mocks."
            )
            raw_critique = self.rlm.spawn(
                role=AgentRole.DESTROYER.value,
                prompt=destroyer_prompt,
                context=self._role_context(context, AgentRole.DESTROYER.value),
            )
            critique = raw_critique if isinstance(raw_critique, dict) else {"critique": raw_critique, "round": round_idx}
            all_critiques.append(critique)
            self.blackboard.write(AgentRole.DESTROYER, "crucible_critiques", all_critiques)

            # 3. Referee renders cold, impassive verdict (digest + re-run check)
            referee_prompt = (
                f"Proposal: {self._proposal_brief(current_proposal)}\n"
                f"Critique digest: {self._digest_critiques([critique])}\n"
                f"Reconcile re-run: {self._reconcile_check(current_proposal)}\n"
                "Render objective verdict. Return JSON with 'passed' (boolean), 'score' (1-10), and 'reason'."
            )
            raw_verdict = self.rlm.spawn(
                role=AgentRole.REFEREE.value,
                prompt=referee_prompt,
                context=self._role_context(context, AgentRole.REFEREE.value),
            )
            verdict = self._parse_verdict(raw_verdict, round_idx)
            jev_answers: Optional[Dict[str, Any]] = None
            if self._jev_active() and verdict.get("passed"):
                try:
                    jev_answers = jev.judge(
                        {
                            "task_spec": task_spec,
                            "proposal": self._proposal_brief(current_proposal),
                            "critique": self._digest_critiques([critique]),
                            "verdict": verdict,
                        },
                        {"pass": jev.check("Does this proposal fully satisfy the task spec?")},
                    )
                except Exception:
                    jev_answers = None  # degrade silently; LLM verdict stands
                verdict = _arbitrate_verdict(verdict, jev_answers)
            if self.on_round is not None:
                self.on_round({
                    "round": round_idx,
                    "passed": bool(verdict.get("passed", False)),
                    "jev_enabled": self._jev_active(),
                    "jev_verdict": (jev_answers or {}).get("pass"),
                    "jev_score": verdict.get("jev_score"),
                    "jev_confidence": verdict.get("jev_confidence"),
                    "jev_error": jev.last_error(),
                })
            self.blackboard.write(AgentRole.REFEREE, "crucible_verdict", verdict)

            if verdict.get("passed", False):
                return CrucibleResult(
                    passed=True,
                    proposal=current_proposal,
                    verdict=verdict,
                    rounds_executed=round_idx,
                    critiques=all_critiques,
                )

        # Reached limit without approval -> Trip circuit breaker
        raise CircuitBreakerException(
            phase="PHASE_4_CRUCIBLE",
            step_count=self.max_rounds,
            max_limit=self.max_rounds,
            reason="Crucible deadlock: Builder and Destroyer failed to reach consensus. Suspending to HITL."
        )
    @staticmethod
    def _role_context(context: Optional[Dict[str, Any]], role: str) -> Optional[Dict[str, Any]]:
        """Role-scoped context: role tag plus shared anchors, never raw peer monologue."""
        base = dict(context or {})
        base["role"] = role
        return base

    @staticmethod
    def _digest_critiques(critiques: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compresses critiques to vector/severity/round triples for Builder/Referee."""
        digest = []
        for c in critiques[-3:]:
            if isinstance(c, dict):
                row = {k: c.get(k) for k in ("vector", "severity", "round", "critique") if c.get(k) is not None}
                anchors = CrucibleWorkflow.normalize_anchors(c.get("anchors"))
                if anchors:
                    row["anchors"] = anchors
                digest.append(row)
        return digest

    @staticmethod
    def normalize_anchors(anchors: Any) -> List[Dict[str, Any]]:
        """Normalizes optional hashline anchors [{file, line, id?}]; garbage -> []."""
        out: List[Dict[str, Any]] = []
        if not isinstance(anchors, list):
            return out
        for a in anchors[:32]:
            if not isinstance(a, dict):
                continue
            try:
                line = int(a.get("line", 0))
            except (TypeError, ValueError):
                continue
            if line <= 0 or not isinstance(a.get("file"), str) or not a["file"]:
                continue
            row: Dict[str, Any] = {"file": a["file"], "line": line}
            if isinstance(a.get("id"), str) and a["id"]:
                row["id"] = a["id"]
            out.append(row)
        return out

    @staticmethod
    def _proposal_brief(proposal: Any) -> Any:
        """Trims the proposal for Destroyer/Referee (no internal reasoning leakage)."""
        if isinstance(proposal, dict):
            brief = {k: proposal.get(k) for k in ("spec", "content", "edge_cases", "round") if proposal.get(k) is not None}
            anchors = CrucibleWorkflow.normalize_anchors(proposal.get("anchors"))
            if anchors:
                brief["anchors"] = anchors
            return brief
        return proposal

    @staticmethod
    def _reconcile_check(proposal: Any) -> str:
        """Re-runs reconcile when the proposal names workspace Python files."""
        import os as _os
        from swda.workflows.reconcile import ReverseReconciliation
        files = []
        stack = [proposal]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                stack.extend(cur.values())
            elif isinstance(cur, (list, tuple)):
                stack.extend(cur)
            elif isinstance(cur, str) and cur.strip().endswith(".py") and _os.path.exists(cur.strip()):
                files.append(cur.strip())
        if not files:
            return "no workspace Python files named; skipped"
        parts = []
        for f in sorted(set(files))[:5]:
            try:
                res = ReverseReconciliation.verify_file(f, _os.getcwd())
                parts.append(f"{f}: {res.get('verdict', 'unknown')}")
            except Exception as e:
                parts.append(f"{f}: check failed ({e})")
        return "; ".join(parts)

    @staticmethod
    def _parse_verdict(raw_verdict: Any, round_idx: int) -> Dict[str, Any]:
        """Parses a referee verdict; unparseable output fails closed, never auto-passes."""
        if isinstance(raw_verdict, dict):
            return {
                "passed": bool(raw_verdict.get("passed", False)),
                "score": raw_verdict.get("score", 0),
                "reason": str(raw_verdict.get("reason", "")),
                "round": round_idx,
                "jev_score": None,  # only _arbitrate_verdict sets these (spoof guard)
                "jev_confidence": None,
            }
        if isinstance(raw_verdict, str):
            match = re.search(r"\{.*\}", raw_verdict, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if isinstance(data, dict):
                        return {
                            "passed": bool(data.get("passed", False)),
                            "score": data.get("score", 0),
                            "reason": str(data.get("reason", raw_verdict[:200])),
                            "round": round_idx,
                            "jev_score": None,  # arbitration sets these, not the referee
                            "jev_confidence": None,
                        }
                except Exception:
                    pass
        return {
            "passed": False,
            "score": 0,
            "reason": f"Unparseable referee output in round {round_idx}; failing closed for re-review.",
            "round": round_idx,
            "jev_score": None,
            "jev_confidence": None,
        }
