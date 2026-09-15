"""
Unit tests for SWDA Workflows, Prime REPL, and Continual Harness.
"""

import unittest
import os
import tempfile
import shutil
from swda.core.blackboard import Blackboard
from swda.core.circuit_breaker import StepCounter
from swda.core.firewall import SecurityFirewallException
from swda.prime.repl import PrimeREPL
from swda.prime.rlm import RLMDispatcher
from swda.prime.harness import ContinualHarness
from swda.workflows.crucible import CrucibleWorkflow
from swda.workflows.reconcile import ReverseReconciliation


class TestWorkflows(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_prime_repl_persistent_execution(self):
        bb = Blackboard()
        repl = PrimeREPL(bb)
        # Execute statement 1
        res1 = repl.execute("a = 10")
        self.assertTrue(res1["success"])

        # Execute statement 2 referencing statement 1
        res2 = repl.execute("b = a + 5\nb")
        self.assertTrue(res2["success"])
        self.assertEqual(res2["result"], 15)

    def test_prime_repl_firewall_blocks_mutation_in_gather(self):
        bb = Blackboard()
        bb.write(bb.WRITE_PERMISSIONS["phase"][0], "phase", "PHASE_2_GATHER")
        repl = PrimeREPL(bb)

        with self.assertRaises(SecurityFirewallException):
            repl.execute("with open('malicious.py', 'w') as f: f.write('bad')")

    def test_continual_harness_refine_and_persistence(self):
        harness = ContinualHarness(workspace_root=self.temp_dir)
        res = harness.refine(
            trajectory_summary="Builder repeatedly missed Redis connection pool timeout error",
            failure_signal="ResourceLeakError in production redis connector",
        )
        self.assertTrue(os.path.exists(res["path"]))
        patterns = harness.list_anti_patterns()
        self.assertEqual(len(patterns), 1)

    def test_crucible_workflow_approval(self):
        bb = Blackboard()

        def mock_llm_handler(role: str, prompt: str):
            if role == "builder":
                return {"spec": "Add cache layer", "ttl": 300}
            elif role == "destroyer":
                return {"vector": "Cache stampede under spike load"}
            elif role == "referee":
                return {"passed": True, "score": 9, "reason": "Good specification"}
            return {}

        rlm = RLMDispatcher(mock_handler=mock_llm_handler)
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb, max_rounds=3)
        res = crucible.run_crucible("Optimize database queries")

        self.assertTrue(res.passed)
        self.assertEqual(res.rounds_executed, 1)
        self.assertEqual(bb.read("active_proposal")["spec"], "Add cache layer")

    def test_reverse_reconciliation(self):
        # Create a valid python file
        valid_file = os.path.join(self.temp_dir, "valid_sample.py")
        with open(valid_file, "w", encoding="utf-8") as f:
            f.write("import json\nimport sys\nx = json.dumps({'ok': True})\n")

        res_valid = ReverseReconciliation.verify_file(valid_file, self.temp_dir)
        self.assertTrue(res_valid["valid"])

        # Create an invalid python file importing non-existent module
        invalid_file = os.path.join(self.temp_dir, "invalid_sample.py")
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("import phantom_non_existent_module_xyz\n")

        res_invalid = ReverseReconciliation.verify_file(invalid_file, self.temp_dir)
        self.assertFalse(res_invalid["valid"])
        self.assertTrue(any("phantom_non_existent_module_xyz" in err for err in res_invalid["errors"]))

    def test_reverse_reconciliation_hallucinated_from_symbol(self):
        hallu_file = os.path.join(self.temp_dir, "hallu_from.py")
        with open(hallu_file, "w", encoding="utf-8") as f:
            f.write("from os import hallucinated_func_xyz\nprint(hallucinated_func_xyz)\n")

        res = ReverseReconciliation.verify_file(hallu_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("hallucinated_func_xyz" in err for err in res["errors"]))

    def test_reverse_reconciliation_hallucinated_attribute(self):
        hallu_file = os.path.join(self.temp_dir, "hallu_attr.py")
        with open(hallu_file, "w", encoding="utf-8") as f:
            f.write("import json\nx = json.hallucinated_api_xyz()\n")

        res = ReverseReconciliation.verify_file(hallu_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("json.hallucinated_api_xyz" in err for err in res["errors"]))

    def test_reverse_reconciliation_valid_symbols_still_pass(self):
        valid_file = os.path.join(self.temp_dir, "valid_symbols.py")
        with open(valid_file, "w", encoding="utf-8") as f:
            f.write("import json\nfrom os import path\nx = json.dumps({'ok': True})\ny = path.join('a', 'b')\n")

        res = ReverseReconciliation.verify_file(valid_file, self.temp_dir)
        self.assertTrue(res["valid"])

    def test_reverse_reconciliation_workspace_local_symbol(self):
        pkg_dir = os.path.join(self.temp_dir, "mymod")
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("def real_fn():\n    return 1\n")

        use_file = os.path.join(self.temp_dir, "use_local.py")
        with open(use_file, "w", encoding="utf-8") as f:
            f.write("from mymod import real_fn\nfrom mymod import fake_fn_xyz\nprint(real_fn())\n")

        res = ReverseReconciliation.verify_file(use_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("fake_fn_xyz" in err for err in res["errors"]))
        self.assertFalse(any("real_fn" in err for err in res["errors"]))


if __name__ == "__main__":
    unittest.main()
