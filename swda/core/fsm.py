"""
SWDA Finite State Machine (FSM) Engine:
Strict DAG validation and phase-gating mechanism for Swarm-Driven Development.
Prevents deadlocks, premature implementation, and out-of-order phase jumps.
"""

from enum import Enum
from typing import Dict, List, Optional
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.circuit_breaker import StepCounter, CircuitBreakerException


class FSMPhase(str, Enum):
    INTENT_GATE = "INTENT_GATE"
    PHASE_1_DESTRUCT = "PHASE_1_DESTRUCT"
    PHASE_2_GATHER = "PHASE_2_GATHER"
    PHASE_3_HYPERPLAN = "PHASE_3_HYPERPLAN"
    PHASE_4_CRUCIBLE = "PHASE_4_CRUCIBLE"
    PHASE_5_SYNTHESIS = "PHASE_5_SYNTHESIS"
    PHASE_6_IMPLEMENT = "PHASE_6_IMPLEMENT"
    HITL_SUSPEND = "HITL_SUSPEND"
    COMPLETE = "COMPLETE"


class FSMEngine:
    """
    Orchestrates SWDD phase transitions with strict DAG dependency verification.
    """

    # Allowed Directed Acyclic Graph transitions
    VALID_TRANSITIONS: Dict[FSMPhase, List[FSMPhase]] = {
        FSMPhase.INTENT_GATE: [FSMPhase.PHASE_1_DESTRUCT, FSMPhase.PHASE_2_GATHER, FSMPhase.HITL_SUSPEND, FSMPhase.COMPLETE],
        FSMPhase.PHASE_1_DESTRUCT: [FSMPhase.PHASE_2_GATHER, FSMPhase.HITL_SUSPEND],
        FSMPhase.PHASE_2_GATHER: [FSMPhase.PHASE_3_HYPERPLAN, FSMPhase.HITL_SUSPEND],
        FSMPhase.PHASE_3_HYPERPLAN: [FSMPhase.PHASE_4_CRUCIBLE, FSMPhase.HITL_SUSPEND],
        FSMPhase.PHASE_4_CRUCIBLE: [FSMPhase.PHASE_3_HYPERPLAN, FSMPhase.PHASE_5_SYNTHESIS, FSMPhase.HITL_SUSPEND],
        FSMPhase.PHASE_5_SYNTHESIS: [FSMPhase.PHASE_6_IMPLEMENT, FSMPhase.HITL_SUSPEND],
        FSMPhase.PHASE_6_IMPLEMENT: [FSMPhase.COMPLETE, FSMPhase.HITL_SUSPEND, FSMPhase.PHASE_3_HYPERPLAN],
        FSMPhase.HITL_SUSPEND: [FSMPhase.PHASE_1_DESTRUCT, FSMPhase.PHASE_2_GATHER, FSMPhase.PHASE_3_HYPERPLAN, FSMPhase.PHASE_5_SYNTHESIS, FSMPhase.PHASE_6_IMPLEMENT, FSMPhase.COMPLETE],
        FSMPhase.COMPLETE: [],
    }

    def __init__(self, blackboard: Blackboard, step_counter: Optional[StepCounter] = None):
        self.blackboard = blackboard
        self.step_counter = step_counter or StepCounter()
        self.current_phase = FSMPhase(self.blackboard.read("phase"))

    def advance_to(self, next_phase: FSMPhase) -> FSMPhase:
        """
        Advances the FSM to the target phase after checking DAG validity and artifact dependencies.
        Raises ValueError or PermissionError if transitions or prerequisites fail.
        """
        if next_phase == FSMPhase.HITL_SUSPEND:
            return self._commit_transition(next_phase)

        allowed = self.VALID_TRANSITIONS.get(self.current_phase, [])
        if next_phase not in allowed:
            raise ValueError(
                f"Invalid DAG transition: Cannot transition from {self.current_phase.value} to {next_phase.value}. "
                f"Valid target phases: {[p.value for p in allowed]}"
            )

        # Prerequisite validation (Exit gates)
        self._verify_phase_prerequisites(next_phase)

        # Record step in circuit breaker
        self.step_counter.record_step(next_phase.value)

        return self._commit_transition(next_phase)

    def _verify_phase_prerequisites(self, target_phase: FSMPhase) -> None:
        """Enforces hard dependencies before allowing state transition."""
        if target_phase == FSMPhase.PHASE_4_CRUCIBLE:
            proposal = self.blackboard.read("active_proposal")
            if not proposal:
                raise ValueError("Dependency failure: Cannot enter CRUCIBLE without an active proposal from Builder.")

        elif target_phase == FSMPhase.PHASE_5_SYNTHESIS:
            verdict = self.blackboard.read("crucible_verdict")
            if not verdict or not verdict.get("passed", False):
                raise ValueError("Dependency failure: Cannot enter SYNTHESIS without a verified Crucible verdict (passed=True).")

        elif target_phase == FSMPhase.PHASE_6_IMPLEMENT:
            blueprint = self.blackboard.read("synthesis_blueprint")
            if not blueprint:
                raise ValueError("Dependency failure: Cannot enter IMPLEMENT without a formal synthesis blueprint.")

    def _commit_transition(self, new_phase: FSMPhase) -> FSMPhase:
        self.current_phase = new_phase
        self.blackboard.write(AgentRole.SYSTEM, "phase", new_phase.value)
        return self.current_phase
