#!/usr/bin/env python3
"""
SWDA Benchmark Harness Unit & Integration Test.

Verifies:
1. Benchmark tasks.json schema validity.
2. SWDAEvaluator weighted 100-point calculation accuracy.
3. HarnessRunner offline evaluation execution and report generation.
"""
import unittest
import os
import json
import shutil

from tests.benchmark.scoring import SWDAEvaluator
from tests.benchmark.harness_runner import HarnessRunner, DEFAULT_TASKS_FILE


class TestSWDABenchmarkHarness(unittest.TestCase):

    def test_tasks_json_file_exists_and_valid(self):
        self.assertTrue(os.path.exists(DEFAULT_TASKS_FILE), f"tasks.json missing at {DEFAULT_TASKS_FILE}")
        with open(DEFAULT_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        self.assertIn("tasks", data)
        self.assertGreaterEqual(len(data["tasks"]), 6, "At least 6 benchmark tasks must be defined")

    def test_evaluator_scoring_logic(self):
        task_spec = {
            "id": "TEST-TASK-01",
            "expected_intent": "CASUAL_CHAT",
            "expected_track": "FAST_PASS",
            "expected_next_state": "FAST_PASS_EXIT"
        }
        perfect_output = """<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: CASUAL_CHAT
EXECUTION_TRACK: FAST_PASS
RESOURCE_LOCK_REQUIRED: False
USE_SWARM_WORKFLOW: False
AUDITOR_SAFETY_STATUS: PASSED
STRATEGY_TRACK: Direct Response.
</INTENT_GATE_RESULT>
[NEXT_STATE: FAST_PASS_EXIT | Zero-Chat Contract Active]"""

        eval_res = SWDAEvaluator.evaluate_task(task_spec, perfect_output)
        self.assertEqual(eval_res["total_score"], 100.0)
        self.assertEqual(eval_res["status"], "PASS")

    def test_evaluator_deduction_for_overthinking_loop(self):
        task_spec = {
            "id": "TEST-TASK-02",
            "expected_intent": "CASUAL_CHAT",
            "expected_track": "FAST_PASS",
            "expected_next_state": "FAST_PASS_EXIT"
        }
        overthinking_output = """<INTENT_GATE_RESULT>
INTENT_CLASSIFICATION: CASUAL_CHAT
EXECUTION_TRACK: SWARM_MODE
RESOURCE_LOCK_REQUIRED: True
USE_SWARM_WORKFLOW: True
AUDITOR_SAFETY_STATUS: PASSED
STRATEGY_TRACK: Dispatching 3 subagents for casual greeting.
</INTENT_GATE_RESULT>
[NEXT_STATE: PHASE_1_DESTRUCT | Zero-Chat Contract Active]"""

        eval_res = SWDAEvaluator.evaluate_task(task_spec, overthinking_output)
        # Efficiency score should be 0 for running SWARM_MODE on greeting
        self.assertEqual(eval_res["breakdown"]["track_efficiency"], 0.0)
        self.assertLess(eval_res["total_score"], 75.0)
        self.assertEqual(eval_res["status"], "FAIL")

    def test_harness_runner_execution(self):
        runner = HarnessRunner(tasks_file=DEFAULT_TASKS_FILE, offline=True)
        eval_data = runner.run_evaluation("swda(deepseek-v4-flash)")
        
        # Allow for minor variations if the mock or task suite evolves
        self.assertGreaterEqual(eval_data["pass_rate_pct"], 80.0)
        self.assertGreaterEqual(eval_data["average_score"], 80.0)
        
        report_md = runner.generate_markdown_report(eval_data)
        self.assertIn("# SWDA Evaluation Harness Benchmark Report", report_md)
        self.assertIn("BENCH-01-FAST-PASS-GREETING", report_md)
        self.assertIn("BENCH-06-SECURITY-FIREWALL-TC08", report_md)
        # Verify the report table columns are correctly split (expected vs actual)
        self.assertIn("Expected Track", report_md)
        self.assertIn("Actual Track", report_md)

    def test_pi_agent_runner_initialization(self):
        """Verifies HarnessRunner initialization with Pi Agent live driver (offline fallback)."""
        from tests.benchmark.harness_runner import run_pi_agent_live  # noqa: F401 — verify importable
        runner = HarnessRunner(tasks_file=DEFAULT_TASKS_FILE, offline=True, agent_driver="pi")
        self.assertEqual(runner.agent_driver, "pi")
        
        # When offline=True, Pi driver falls back to mock — verify model_name is preserved
        eval_data = runner.run_evaluation("swda(pi-agent)")
        self.assertEqual(eval_data["model_name"], "swda(pi-agent)")
        self.assertGreaterEqual(eval_data["pass_rate_pct"], 80.0)

    @unittest.skipIf(shutil.which("pi") is None, "pi CLI not installed — skipping live Pi Agent integration test")
    def test_pi_agent_live_driver(self):
        """Live integration test: requires the `pi` CLI to be installed and on PATH."""
        from tests.benchmark.harness_runner import run_pi_agent_live
        output = run_pi_agent_live("hi", timeout=30)
        # Simple greeting must NOT trigger SWARM_MODE or overthinking loops
        self.assertNotIn("SWARM_MODE", output, "Over-thinking loop detected: SWARM_MODE triggered for a simple greeting")
        self.assertNotIn("PHASE_1_DESTRUCT", output, "Over-thinking loop detected: PHASE_1_DESTRUCT triggered for a simple greeting")


if __name__ == "__main__":
    unittest.main()
