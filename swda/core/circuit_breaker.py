"""
SWDA Circuit Breaker & Step Budget Controller.
Implements the Host Circuit Breaker Protocol (docs/architecture/circuit-breaker-spec.md).
Guarantees liveness and prevents infinite loops, overthinking, and deadlock in multi-agent workflows.
"""

from typing import Dict, Optional


class CircuitBreakerException(Exception):
    """Raised when an execution phase exceeds its allocated step budget."""
    def __init__(self, phase: str, step_count: int, max_limit: int, reason: str = ""):
        self.phase = phase
        self.step_count = step_count
        self.max_limit = max_limit
        self.reason = reason
        super().__init__(
            f"CIRCUIT BREAKER TRIGGERED: Phase '{phase}' exceeded step budget limit "
            f"({step_count}/{max_limit}). Halting to prevent infinite loop. {reason}".strip()
        )


class StepCounter:
    """
    Tracks execution steps per phase and enforces physical circuit breakers.
    """

    DEFAULT_BUDGETS: Dict[str, int] = {
        "INTENT_GATE": 1,
        "PHASE_1_DESTRUCT": 3,
        "PHASE_2_GATHER": 3,
        "PHASE_3_HYPERPLAN": 5,
        "PHASE_4_CRUCIBLE": 5,
        "PHASE_5_SYNTHESIS": 2,
        "PHASE_6_IMPLEMENT": 5,
        "DYNAMIC_COMPILE": 5,
    }

    def __init__(self, budgets: Optional[Dict[str, int]] = None, total_step_limit: int = 20):
        self.budgets = dict(self.DEFAULT_BUDGETS)
        if budgets:
            self.budgets.update(budgets)
        self.total_step_limit = total_step_limit
        self.step_counts: Dict[str, int] = {}
        self.total_steps = 0

    def record_step(self, phase: str) -> int:
        """
        Increments the counter for the given phase and checks against the budget.
        Raises CircuitBreakerException if the budget is breached.
        """
        self.total_steps += 1
        if self.total_steps > self.total_step_limit:
            raise CircuitBreakerException(
                phase="GLOBAL",
                step_count=self.total_steps,
                max_limit=self.total_step_limit,
                reason="Total execution steps exceeded global budget limit."
            )

        current = self.step_counts.get(phase, 0) + 1
        self.step_counts[phase] = current

        limit = self.budgets.get(phase, 10)
        if current > limit:
            raise CircuitBreakerException(
                phase=phase,
                step_count=current,
                max_limit=limit,
                reason=f"Step budget ({limit}) exhausted for phase {phase}."
            )

        return current

    def get_count(self, phase: str) -> int:
        """Returns the current step count for a phase."""
        return self.step_counts.get(phase, 0)

    def reset_phase(self, phase: str) -> None:
        """Resets the counter for a specific phase (e.g. upon successful state transition)."""
        self.step_counts[phase] = 0
