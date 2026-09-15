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

    def test_global_step_limit_trips(self):
        counter = StepCounter(total_step_limit=3)
        counter.record_step("PHASE_1_DESTRUCT")
        counter.record_step("PHASE_2_GATHER")
        counter.record_step("PHASE_3_HYPERPLAN")
        with self.assertRaises(CircuitBreakerException) as ctx:
            counter.record_step("PHASE_4_CRUCIBLE")
        self.assertEqual(ctx.exception.phase, "GLOBAL")


if __name__ == "__main__":
    unittest.main()
