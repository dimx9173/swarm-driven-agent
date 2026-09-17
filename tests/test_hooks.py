#!/usr/bin/env python3
"""Regression tests for P0 execution hooks (PreToolUse/PostToolUse/Stop)."""
import os
import tempfile
import unittest

from swda.core.blackboard import Blackboard
from swda.core.hooks import HookBlocked, HookRegistry
from swda.prime.repl import PrimeREPL
from swda.workflows.tdd_runner import TDDRunner, set_default_hooks


class TestHookRegistry(unittest.TestCase):
    def test_pre_block_aborts_with_reason(self):
        reg = HookRegistry()

        def deny(event):
            return {"decision": "block", "reason": "nope"}

        reg.register("PreToolUse", deny)
        with self.assertRaises(HookBlocked) as ctx:
            reg.run_pre("repl.execute", {"code": "x"})
        self.assertIn("nope", str(ctx.exception))

    def test_pre_allow_passes_through(self):
        reg = HookRegistry()
        reg.register("PreToolUse", lambda event: None)
        reg.run_pre("repl.execute", {"code": "x"})  # must not raise

    def test_unknown_event_rejected(self):
        reg = HookRegistry()
        with self.assertRaises(ValueError):
            reg.register("Nope", lambda event: None)

    def test_unregister_and_clear(self):
        reg = HookRegistry()
        fn = lambda event: {"decision": "block", "reason": "x"}  # noqa: E731
        reg.register("PreToolUse", fn)
        reg.unregister("PreToolUse", fn)
        reg.run_pre("t", {})  # must not raise
        reg.register("PreToolUse", fn)
        reg.clear("PreToolUse")
        reg.run_pre("t", {})  # must not raise

    def test_stop_block_forces_rework(self):
        reg = HookRegistry()
        reg.register("Stop", lambda event: {"decision": "block", "reason": "gate red"})
        with self.assertRaises(HookBlocked):
            reg.run_stop("deliver", {"phase": "SYNTHESIS"})

    def test_post_hooks_never_raise(self):
        reg = HookRegistry()

        def boom(event):
            raise RuntimeError("post must not propagate")

        reg.register("PostToolUse", boom)
        reg.run_post("t", {}, {})  # must not raise


class TestReplHooks(unittest.TestCase):
    def test_pre_hook_block_aborts_before_exec(self):
        bb = Blackboard()
        reg = HookRegistry()
        seen = []
        reg.register("PreToolUse", lambda e: seen.append(e) or {"decision": "block", "reason": "denied"})
        repl = PrimeREPL(bb, hooks=reg)
        res = repl.execute("__import__('os').system('echo PWNED')")
        self.assertFalse(res["success"])
        self.assertIn("denied", res["error"])
        self.assertEqual(len(seen), 1)

    def test_post_hook_observes_result(self):
        bb = Blackboard()
        reg = HookRegistry()
        observed = []
        reg.register("PostToolUse", lambda e: observed.append(e))
        repl = PrimeREPL(bb, hooks=reg)
        res = repl.execute("1 + 1")
        self.assertTrue(res["success"])
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["tool"], "repl.execute")

    def test_no_hooks_behaves_as_before(self):
        bb = Blackboard()
        repl = PrimeREPL(bb)
        res = repl.execute("1 + 1")
        self.assertTrue(res["success"])
        self.assertEqual(res["result"], 2)


class TestTddHooksAndSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        set_default_hooks(None)

    def tearDown(self):
        set_default_hooks(None)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_firewall_blocks_dangerous_command(self):
        res = TDDRunner.run_tests("rm -rf /", cwd=self.tmp)
        self.assertFalse(res.passed)
        self.assertEqual(res.returncode, 126)
        self.assertIn("Firewall blocked", res.stderr)

    def test_sandbox_escape_rejected(self):
        res = TDDRunner.run_tests("echo hi", cwd="/", sandbox_dir=self.tmp)
        self.assertFalse(res.passed)
        self.assertEqual(res.returncode, 126)
        self.assertIn("Sandbox escape", res.stderr)

    def test_pre_hook_can_block_run(self):
        reg = HookRegistry()
        reg.register("PreToolUse", lambda e: {"decision": "block", "reason": "frozen"})
        res = TDDRunner.run_tests("echo hi", cwd=self.tmp, hooks=reg)
        self.assertFalse(res.passed)
        self.assertIn("frozen", res.stderr)

    def test_post_hook_observes_run(self):
        reg = HookRegistry()
        observed = []
        reg.register("PostToolUse", lambda e: observed.append(e))
        res = TDDRunner.run_tests("echo hi", cwd=self.tmp, hooks=reg)
        self.assertTrue(res.passed)
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0]["result"]["passed"])

    def test_default_hooks_registry_used(self):
        reg = HookRegistry()
        observed = []
        reg.register("PostToolUse", lambda e: observed.append(e))
        set_default_hooks(reg)
        try:
            res = TDDRunner.run_tests("echo hi", cwd=self.tmp)
            self.assertTrue(res.passed)
            self.assertEqual(len(observed), 1)
        finally:
            set_default_hooks(None)

    def test_benign_command_still_runs(self):
        res = TDDRunner.run_tests("echo hi", cwd=self.tmp)
        self.assertTrue(res.passed)
        self.assertIn("hi", res.stdout)


if __name__ == "__main__":
    unittest.main()
