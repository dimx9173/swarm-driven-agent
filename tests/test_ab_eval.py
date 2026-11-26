#!/usr/bin/env python3
"""
Unit tests for SWDA Coding A/B Benchmark Evaluator (tests/benchmark/ab_eval.py).
"""
import json
import os
import unittest

from tests.benchmark.ab_eval import ABBenchmarkRunner, DEFAULT_CODING_TASKS_FILE


class TestSWDACodingABEval(unittest.TestCase):

    def test_coding_tasks_schema_and_red_state(self):
        self.assertTrue(os.path.exists(DEFAULT_CODING_TASKS_FILE))
        with open(DEFAULT_CODING_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        tasks = data.get("tasks", [])
        self.assertGreaterEqual(len(tasks), 10)

        runner = ABBenchmarkRunner(tasks_file=DEFAULT_CODING_TASKS_FILE, driver="mock")
        for task in tasks:
            self.assertIn("id", task)
            self.assertIn("starter_files", task)
            if task.get("type") == "scored_sim":
                self.assertIn("eval_script", task)
            else:
                self.assertIn("test_code", task)
            self.assertTrue(
                runner.verify_starter_fails(task),
                f"Starter code for {task['id']} must FAIL or score < 60 (Red State)",
            )

    def test_mock_ab_comparison_and_report(self):
        runner = ABBenchmarkRunner(tasks_file=DEFAULT_CODING_TASKS_FILE, driver="mock")
        data = runner.run_ab_comparison()

        self.assertEqual(data["total_tasks"], 14)
        self.assertEqual(data["baseline_passed"], 1)
        self.assertEqual(data["swda_passed"], 14)
        self.assertEqual(data["baseline_pass_rate_pct"], 7.1)
        self.assertEqual(data["swda_pass_rate_pct"], 100.0)
        self.assertEqual(data["delta_pass_rate_pct"], 92.9)
        self.assertGreater(data["swda_avg_score"], 85.0)
        self.assertGreater(data["delta_avg_score"], 75.0)

        report = runner.generate_markdown_report(data)
        self.assertIn("# SWDA Coding A/B Benchmark Report", report)
        self.assertIn("SIM-01-HFT-MARKET-MAKER", report)
        self.assertIn("SIM-05-COMPLEX-SEARCH-INDEX", report)
        self.assertIn("LOGIC-01-SAT-CSP-SOLVER", report)

    def test_multi_run_aggregation_and_failure_logging(self):
        import tempfile
        with tempfile.TemporaryDirectory() as log_dir:
            runner = ABBenchmarkRunner(
                tasks_file=DEFAULT_CODING_TASKS_FILE,
                driver="mock",
                runs=2,
                log_dir=log_dir,
            )
            data = runner.run_single_mode("baseline")
            self.assertEqual(data["total_tasks"], 14)
            self.assertEqual(data["passed"], 1)
            self.assertEqual(data["results"][1]["metrics"]["trial_passes"], "0/2")
            logs = os.listdir(log_dir)
            self.assertGreater(len(logs), 0)


if __name__ == "__main__":
    unittest.main()
