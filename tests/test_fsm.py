"""
Unit tests for SWDA FSM Engine and DAG dependency validation.
"""

import unittest
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.fsm import FSMEngine, FSMPhase


class TestFSMEngine(unittest.TestCase):

    def setUp(self):
        self.bb = Blackboard()
        self.fsm = FSMEngine(self.bb)

    def test_valid_dag_transitions(self):
        self.assertEqual(self.fsm.current_phase, FSMPhase.INTENT_GATE)
        self.fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        self.assertEqual(self.fsm.current_phase, FSMPhase.PHASE_2_GATHER)

        self.fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        self.assertEqual(self.fsm.current_phase, FSMPhase.PHASE_3_HYPERPLAN)

    def test_invalid_skip_transition(self):
        # Cannot jump from INTENT_GATE straight to IMPLEMENT
        with self.assertRaises(ValueError):
            self.fsm.advance_to(FSMPhase.PHASE_6_IMPLEMENT)

    def test_crucible_prerequisite_blocked_without_proposal(self):
        self.fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        self.fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        # active_proposal is None -> cannot enter CRUCIBLE
        with self.assertRaises(ValueError) as ctx:
            self.fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
        self.assertIn("Dependency failure", str(ctx.exception))

    def test_synthesis_prerequisite_blocked_without_passing_verdict(self):
        self.fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        self.fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        self.bb.write(AgentRole.BUILDER, "active_proposal", {"title": "Valid Plan"})
        self.fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)

        # verdict missing -> cannot enter SYNTHESIS
        with self.assertRaises(ValueError):
            self.fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)

        # failed verdict -> cannot enter SYNTHESIS
        self.bb.write(AgentRole.REFEREE, "crucible_verdict", {"passed": False})
        with self.assertRaises(ValueError):
            self.fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)

        # passed verdict -> allowed
        self.bb.write(AgentRole.REFEREE, "crucible_verdict", {"passed": True})
        self.fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)
        self.assertEqual(self.fsm.current_phase, FSMPhase.PHASE_5_SYNTHESIS)


if __name__ == "__main__":
    unittest.main()
