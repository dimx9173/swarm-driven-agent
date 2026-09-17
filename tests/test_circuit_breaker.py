"""
Unit tests for SWDA Circuit Breaker and Step Counter.
"""

import unittest
from swda.core.circuit_breaker import StepCounter, CircuitBreakerException


class TestCircuitBreaker(unittest.TestCase):

    def test_step_counting_within_budget(self):
        counter = StepCounter(budgets={"PHASE_4_CRUCIBLE": 3})
        self.assertEqual(counter.record_step("PHASE_4_CRUCIBLE"), 1)
        self.assertEqual(counter.record_step("PHASE_4_CRUCIBLE"), 2)
        self.assertEqual(counter.record_step("PHASE_4_CRUCIBLE"), 3)

    def test_circuit_breaker_trips_when_exceeded(self):
        counter = StepCounter(budgets={"PHASE_4_CRUCIBLE": 2})
        counter.record_step("PHASE_4_CRUCIBLE")
        counter.record_step("PHASE_4_CRUCIBLE")
        with self.assertRaises(CircuitBreakerException) as ctx:
            counter.record_step("PHASE_4_CRUCIBLE")
        self.assertEqual(ctx.exception.phase, "PHASE_4_CRUCIBLE")
    def test_default_crucible_budget_matches_workflow_max_rounds(self):
        from swda.workflows.crucible import CrucibleWorkflow
        import inspect
        default_rounds = inspect.signature(CrucibleWorkflow.__init__).parameters["max_rounds"].default
        self.assertEqual(StepCounter.DEFAULT_BUDGETS["PHASE_4_CRUCIBLE"], default_rounds)
    def test_global_step_limit_trips(self):
        counter = StepCounter(total_step_limit=3)
        counter.record_step("PHASE_1_DESTRUCT")
        counter.record_step("PHASE_2_GATHER")
        counter.record_step("PHASE_3_HYPERPLAN")
        with self.assertRaises(CircuitBreakerException) as ctx:
            counter.record_step("PHASE_4_CRUCIBLE")
        self.assertEqual(ctx.exception.phase, "GLOBAL")

    def test_shared_counter_spans_fsm_and_crucible(self):
        from swda.core.blackboard import Blackboard, AgentRole
        from swda.core.fsm import FSMEngine, FSMPhase
        from swda.prime.rlm import RLMDispatcher
        from swda.workflows.crucible import CrucibleWorkflow

        bb = Blackboard()
        shared = StepCounter()
        fsm = FSMEngine(bb, step_counter=shared)
        rlm = RLMDispatcher(mock_handler=lambda role, prompt: {"content": "x"} if role != "referee" else {"passed": True, "score": 8, "reason": "ok"})
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb, step_counter=shared)
        self.assertIs(fsm.step_counter, crucible.step_counter)

        fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        bb.write(AgentRole.SYSTEM, "active_proposal", {"spec": "x", "draft": True})
        fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
        crucible.run_crucible("x")
        # CRUCIBLE entry is free; only confrontation rounds bill the budget.
        self.assertEqual(shared.get_count("PHASE_4_CRUCIBLE"), 1)
        self.assertGreaterEqual(shared.total_steps, 3)

    def test_third_round_still_reachable_under_shared_counter(self):
        from swda.core.blackboard import Blackboard, AgentRole
        from swda.core.fsm import FSMEngine, FSMPhase
        from swda.prime.rlm import RLMDispatcher
        from swda.workflows.crucible import CrucibleWorkflow

        calls = {"n": 0}

        def handler(role, prompt):
            calls["n"] += 1
            if role == "referee":
                return {"passed": calls["n"] >= 9, "score": 8 if calls["n"] >= 9 else 4, "reason": "ok"}
            return {"content": "x"}

        bb = Blackboard()
        shared = StepCounter()
        fsm = FSMEngine(bb, step_counter=shared)
        crucible = CrucibleWorkflow(rlm=RLMDispatcher(mock_handler=handler), blackboard=bb, step_counter=shared)
        fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        bb.write(AgentRole.SYSTEM, "active_proposal", {"spec": "x", "draft": True})
        fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
        res = crucible.run_crucible("x")
        self.assertTrue(res.passed)
        self.assertEqual(res.rounds_executed, 3)


if __name__ == "__main__":
    unittest.main()
