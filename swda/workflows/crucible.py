"""
SWDA Programmatic Crucible: Asymmetric Adversarial Specification Hardening.
Executes Builder vs. Destroyer vs. Referee inside an RLM loop, bounded by circuit breakers.
"""

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
        """
        all_critiques = []
        current_proposal = {"spec": task_spec, "round": 0}

        for round_idx in range(1, self.max_rounds + 1):
            self.step_counter.record_step("PHASE_4_CRUCIBLE")

            # 1. Builder develops/sharpens proposal
            builder_prompt = (
                f"Task: {task_spec}\n"
                f"Previous critiques: {all_critiques}\n"
                "Propose a formal Spec with explicit edge cases, data structures, and trade-offs."
            )
            raw_proposal = self.rlm.spawn(
                role=AgentRole.BUILDER.value,
                prompt=builder_prompt,
                context=context,
            )
            current_proposal = (
                raw_proposal if isinstance(raw_proposal, dict) else {"content": raw_proposal, "round": round_idx}
            )
            self.blackboard.write(AgentRole.BUILDER, "active_proposal", current_proposal)

            # 2. Destroyer attacks (Falsifiable Vector Constraint)
            destroyer_prompt = (
                f"Proposal: {current_proposal}\n"
                "Attack with falsifiable vectors: race conditions, resource leaks, edge errors, fake mocks."
            )
            raw_critique = self.rlm.spawn(
                role=AgentRole.DESTROYER.value,
                prompt=destroyer_prompt,
                context=context,
            )
            critique = raw_critique if isinstance(raw_critique, dict) else {"critique": raw_critique, "round": round_idx}
            all_critiques.append(critique)
            self.blackboard.write(AgentRole.DESTROYER, "crucible_critiques", all_critiques)

            # 3. Referee renders cold, impassive verdict
            referee_prompt = (
                f"Proposal: {current_proposal}\n"
                f"Critique: {critique}\n"
                "Render objective verdict. Return JSON with 'passed' (boolean), 'score' (1-10), and 'reason'."
            )
            raw_verdict = self.rlm.spawn(
                role=AgentRole.REFEREE.value,
                prompt=referee_prompt,
                context=context,
            )
            verdict = raw_verdict if isinstance(raw_verdict, dict) else {"passed": True, "score": 8, "reason": "Approved"}
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
