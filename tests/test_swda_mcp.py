#!/usr/bin/env python3
"""swda-mcp server tests: tool wiring without a live MCP transport."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "swda-mcp"))
sys.path.insert(0, ROOT)

os.environ["SWDA_REPO"] = ROOT

try:
    from swda_mcp.server import (  # noqa: E402
        swda_reconcile,
        swda_firewall_audit,
        swda_stats,
        swda_models,
    )
except ModuleNotFoundError:
    raise unittest.SkipTest("mcp SDK not installed (swda-mcp extra)")


class TestSwdaMcpTools(unittest.TestCase):
    def test_reconcile_valid_file(self):
        res = swda_reconcile(
            file=os.path.join(ROOT, "swda", "core", "blackboard.py"),
            workspace_root=ROOT,
        )
        self.assertTrue(res["valid"], res.get("errors"))

    def test_reconcile_missing_file(self):
        res = swda_reconcile(file="nope.py", workspace_root=ROOT)
        self.assertFalse(res["valid"])

    def test_firewall_blocks_catastrophic(self):
        res = swda_firewall_audit(command="rm -rf /")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["rule_id"], "TC-01")

    def test_firewall_allows_benign(self):
        res = swda_firewall_audit(command="ls -la")
        self.assertTrue(res["allowed"])

    def test_firewall_phase_lock(self):
        res = swda_firewall_audit(
            code="with open('x.py', 'w') as f: f.write('y')",
            phase="PHASE_2_GATHER",
        )
        self.assertFalse(res["allowed"])
        self.assertEqual(res["rule_id"], "RULE-0.7")

    def test_stats_shape(self):
        res = swda_stats()
        for key in ("total_calls", "successful_calls", "success_rate"):
            self.assertIn(key, res)

    def test_models_offline_error_shape(self):
        saved_base = os.environ.get("OPENAI_BASE_URL")
        os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:1/v1"
        try:
            res = swda_models()
            self.assertIn("endpoint", res)
            self.assertTrue("models" in res or "error" in res)
        finally:
            if saved_base is None:
                del os.environ["OPENAI_BASE_URL"]
            else:
                os.environ["OPENAI_BASE_URL"] = saved_base


if __name__ == "__main__":
    unittest.main()
