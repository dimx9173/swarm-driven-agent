"""
SWDA Programmatic Crucible: Asymmetric Adversarial Specification Hardening.
Executes Builder vs. Destroyer vs. Referee inside an RLM loop, bounded by circuit breakers.
"""

import json
import re
from typing import Dict, Any, Optional, List
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.circuit_breaker import StepCounter, CircuitBreakerException
from swda.prime.rlm import RLMDispatcher


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
    ):
        self.rlm = rlm
        self.blackboard = blackboard
        self.step_counter = step_counter or StepCounter()
        self.max_rounds = max_rounds

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
                digest.append({k: c.get(k) for k in ("vector", "severity", "round", "critique") if c.get(k) is not None})
        return digest

    @staticmethod
    def _proposal_brief(proposal: Any) -> Any:
        """Trims the proposal for Destroyer/Referee (no internal reasoning leakage)."""
        if isinstance(proposal, dict):
            return {k: proposal.get(k) for k in ("spec", "content", "edge_cases", "round") if proposal.get(k) is not None}
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
                        }
                except Exception:
                    pass
        return {
            "passed": False,
            "score": 0,
            "reason": f"Unparseable referee output in round {round_idx}; failing closed for re-review.",
            "round": round_idx,
        }
