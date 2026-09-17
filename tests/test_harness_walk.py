#!/usr/bin/env python3
"""
Regression tests for the harness-walk proof scanner (harness_walk.py).

Each test builds a synthetic OMP session trace in the exact on-disk shapes
(tool_execution_start envelope; assistant toolCall + toolResult messages) and
pins the verdict contract:

  full      Python touched + gate verdict valid:true + FSM trace.
  gate      Gate walked, no FSM discipline -> pass w/ fsm-discipline note.
  none      Python touched, no gate -> fail.
  none      Gate ran only before the SYNTHESIS spec -> fail (order).
  none      Latest gate verdict valid:false -> fail (must return to CRUCIBLE).
  fast_pass Chat with no Python and no gate -> pass.

One live test scans this repo's own sessions dir and asserts the known state:
zero MCP-delivered sessions so far (documents the baseline; flip it once the
first trap probe lands).
"""
import json
import os
import unittest

from swda.workflows.harness_walk import scan_lines

SESSIONS_DIR = os.path.expanduser("~/.omp/agent/sessions/-pywork-swarm-driven-agent")


def _start(tool, args, cid):
    return json.dumps({
        "type": "custom", "customType": "tool_execution_start",
        "data": {"toolName": tool, "args": args, "toolCallId": cid},
    })


def _assistant_text(text):
    return json.dumps({
        "type": "message",
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    })


def _assistant_call(name, args, cid):
    return json.dumps({
        "type": "message",
        "message": {"role": "assistant", "content": [{
            "type": "toolCall", "name": name, "arguments": args, "id": cid,
        }]},
    })


def _result(tool, cid, text):
    return json.dumps({
        "type": "message", "id": cid,
        "message": {"role": "toolResult", "toolName": tool,
                    "toolCallId": cid, "content": [{"type": "text", "text": text}]},
    })


FULL_TRACE = [
    _assistant_text(
        "<INTENT_GATE_RESULT>\nINTENT_CLASSIFICATION: FEATURE_DEV\n"
        "EXECUTION_TRACK: SWARM_MODE\n</INTENT_GATE_RESULT>\n"
        "[NEXT_STATE: PHASE_1_DESTRUCT | Zero-Chat Contract Active]"
    ),
    _start("edit", {"path": "swda/x.py"}, "c1"),
    _assistant_text(
        "<SYSTEM_SPECIFICATION>\n1. Architecture Decision Record (ADR)\n"
        "</SYSTEM_SPECIFICATION>\n[NEXT_STATE: PHASE_6_IMPLEMENT | Zero-Chat Contract Active]"
    ),
    _start("swda_reconcile", {"file": "swda/x.py", "workspace_root": "."}, "c2"),
    _result("swda_reconcile", "c2", '{"valid": true, "imported_modules": [], "errors": []}'),
    _assistant_text(
        "<TASK_SUMMARY_REPORT>\nTASK_STATUS: SUCCESS\n</TASK_SUMMARY_REPORT>\n"
        "[NEXT_STATE: None | Zero-Chat Contract Active]"
    ),
]


class TestHarnessWalkLevels(unittest.TestCase):
    def test_full_walk_passes(self):
        res = scan_lines(FULL_TRACE)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "full")
        self.assertEqual(res["swda_tool_calls"]["swda_reconcile"], 1)
        self.assertEqual(res["gate_verdicts"], [True])

    def test_gate_without_fsm_passes_with_note(self):
        lines = [
            _start("edit", {"path": "swda/x.py"}, "c1"),
            _start("swda_reconcile", {"file": "swda/x.py"}, "c2"),
            _result("swda_reconcile", "c2", '{"valid": true, "errors": []}'),
        ]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "gate")
        self.assertTrue(any("fsm-discipline" in m for m in res["missing"]))

    def test_modified_python_without_gate_fails(self):
        lines = [
            _assistant_text("Looks good, merged."),
            _start("edit", {"path": "swda/x.py"}, "c1"),
        ]
        res = scan_lines(lines)
        self.assertFalse(res["passed"])
        self.assertEqual(res["level"], "none")
        self.assertTrue(any("delivery-gate" in m for m in res["missing"]))

    def test_gate_before_spec_only_fails_order(self):
        lines = [
            _start("swda_reconcile", {"file": "swda/x.py"}, "c1"),
            _result("swda_reconcile", "c1", '{"valid": true, "errors": []}'),
            _start("edit", {"path": "swda/x.py"}, "c2"),
            _assistant_text("<SYSTEM_SPECIFICATION>\nbla\n</SYSTEM_SPECIFICATION>\n[NEXT_STATE: X]"),
        ]
        res = scan_lines(lines)
        self.assertFalse(res["passed"])
        self.assertTrue(any(m.startswith("order:") for m in res["missing"]))

    def test_valid_false_verdict_fails_delivery(self):
        lines = list(FULL_TRACE)
        lines[4] = _result("swda_reconcile", "c2",
                           '{"valid": false, "errors": ["phantom symbol swda/x.py:7"]}')
        res = scan_lines(lines)
        self.assertFalse(res["passed"])
        self.assertTrue(any("valid:false" in m for m in res["missing"]))

    def test_fast_pass_chat_passes(self):
        lines = [_assistant_text("Hello! How can I help you today?")]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "fast_pass")

    def test_cli_reconcile_counts_as_gate(self):
        lines = [
            _start("edit", {"path": "swda/x.py"}, "c1"),
            _start("bash", {"command": "swda reconcile swda/x.py"}, "c2"),
            _result("bash", "c2", "\u2713 Reverse Reconciliation Passed: No hallucinated symbols in swda/x.py"),
        ]
        res = scan_lines(lines)
        self.assertEqual(res["reconcile_count"], 1)
        self.assertEqual(res["uncovered_files"], [])
        self.assertEqual(res["level"], "gate")
    def test_toolresult_never_double_counts_calls(self):
        lines = list(FULL_TRACE)
        res = scan_lines(lines)
        self.assertEqual(res["swda_tool_calls"]["swda_reconcile"], 1)

    def test_alternate_assistant_toolcall_shape_counts(self):
        lines = [
            json.dumps({
                "type": "message",
                "message": {"role": "assistant", "content": [{
                    "toolCall": {"id": "c9", "name": "swda_firewall_audit",
                                 "arguments": {"command": "ls"},
                                 "partialArgs": {}},
                    "intent": "x",
                }]},
            }),
        ]
        res = scan_lines(lines)
        self.assertEqual(res["swda_tool_calls"]["swda_firewall_audit"], 1)

    def test_mcp_wrapper_tool_name_normalized(self):
        lines = [_start("mcp__swda__swda_reconcile", {"file": "swda/x.py"}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["swda_tool_calls"]["swda_reconcile"], 1)

    def test_file_path_key_detected_as_py_write(self):
        lines = [_start("edit", {"file_path": "swda/y.py"}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["py_modifications"], 1)

    def test_flat_toplevel_toolcall_shape_counts(self):
        lines = [json.dumps({"type": "toolCall", "name": "swda_stats",
                             "arguments": {}, "id": "t1"})]
        res = scan_lines(lines)
        self.assertEqual(res["swda_tool_calls"]["swda_stats"], 1)

    def test_echo_swda_reconcile_does_not_count(self):
        lines = [_start("bash", {"command": 'echo "swda reconcile swda/x.py"'}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["reconcile_count"], 0)
        self.assertEqual(res["cli_harness_calls"], [])

    def test_bare_tag_mention_without_close_does_not_count(self):
        lines = [_assistant_text("we discussed SYSTEM_SPECIFICATION earlier")]
        res = scan_lines(lines)
        self.assertEqual(res["fsm_tags"]["SYSTEM_SPECIFICATION"], 0)
        self.assertEqual(res["level"], "fast_pass")
    def test_cli_reconcile_pass_output_extracts_verdict(self):
        lines = [
            _start("bash", {"command": "swda reconcile swda/x.py"}, "c1"),
            _result("bash", "c1", "Reconcile done\n\xe2\x9c\x93 Reverse Reconciliation Passed: No hallucinated symbols in swda/x.py"),
        ]
        res = scan_lines(lines)
        self.assertEqual(res["gate_verdicts"], [True])
        self.assertEqual(res["gate_verdicts_by_file"].get("x.py"), [True])
        self.assertEqual(res["unverified"], [])

    def test_cli_reconcile_without_verdict_is_unverified(self):
        lines = [
            _start("edit", {"path": "swda/x.py"}, "c1"),
            _start("bash", {"command": "swda reconcile swda/x.py"}, "c2"),
        ]
        res = scan_lines(lines)
        self.assertEqual(res["reconcile_count"], 1)
        self.assertEqual(res["gate_verdicts"], [])
        self.assertTrue(any("x.py" in u for u in res["unverified"]))
        self.assertIn("unverified", " ".join(res["missing"]))

    def test_per_file_verdict_cross_file_fail_blocks_delivery(self):
        lines = [
            _start("edit", {"path": "swda/a.py"}, "c0"),
            _start("swda_reconcile", {"file": "swda/a.py"}, "c1"),
            _result("swda_reconcile", "c1", '{"valid": false, "errors": ["x"]}'),
            _start("swda_reconcile", {"file": "swda/b.py"}, "c2"),
            _result("swda_reconcile", "c2", '{"valid": true, "errors": []}'),
        ]
        res = scan_lines(lines)
        self.assertFalse(res["passed"])
        self.assertEqual(res["level"], "none")
        self.assertTrue(any("a.py" in m for m in res["missing"]))

    def test_same_file_fix_then_reverify_passes(self):
        lines = [
            _start("edit", {"path": "swda/a.py"}, "c0"),
            _start("swda_reconcile", {"file": "swda/a.py"}, "c1"),
            _result("swda_reconcile", "c1", '{"valid": false, "errors": ["x"]}'),
            _start("swda_reconcile", {"file": "swda/a.py"}, "c2"),
            _result("swda_reconcile", "c2", '{"valid": true, "errors": []}'),
        ]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["gate_verdicts_by_file"].get("a.py"), [False, True])

    def test_bash_redirect_py_counts_as_modification(self):
        lines = [_start("bash", {"command": "cat > swda/gen.py <<'EOF'\nx = 1\nEOF"}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["py_modifications"], 1)
        self.assertFalse(res["passed"])

    def test_fast_pass_objective_despite_fsm_trace(self):
        lines = [_assistant_text(
            "<INTENT_GATE_RESULT>\nEXECUTION_TRACK: FAST_PASS\n</INTENT_GATE_RESULT>\n"
            "[NEXT_STATE: FAST_PASS_EXIT]"
        )]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "fast_pass")

    def test_mcp_reconcile_without_verdict_caps_at_gate(self):
        lines = [
            _assistant_text("<INTENT_GATE_RESULT>\nA\n</INTENT_GATE_RESULT>\n[NEXT_STATE: PHASE_1_DESTRUCT]"),
            _start("edit", {"path": "x.py"}, "c1"),
            _assistant_text("<SYSTEM_SPECIFICATION>\nX\n</SYSTEM_SPECIFICATION>\n[NEXT_STATE: Y]"),
            _start("swda_reconcile", {"file": "swda/x.py"}, "c2"),
            _assistant_text("<TASK_SUMMARY_REPORT>\nQ\n</TASK_SUMMARY_REPORT>\n[NEXT_STATE: None]"),
        ]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "gate")
        self.assertTrue(any("no verdict observed" in m for m in res["missing"]))

    def test_cross_file_innocent_bystander_fails_coverage(self):
        lines = [
            _start("edit", {"path": "a.py"}, "c1"),
            _start("swda_reconcile", {"file": "b.py"}, "c2"),
            _result("swda_reconcile", "c2", '{"valid": true, "verdict": "valid", "errors": []}'),
        ]
        res = scan_lines(lines)
        self.assertFalse(res["passed"])
        self.assertEqual(res["level"], "none")
        self.assertTrue(any("coverage" in m and "a.py" in m for m in res["missing"]))

    def test_inline_python_write_never_fast_pass(self):
        lines = [_start("bash", {"command": 'python3 -c "open(\'evil.py\',\'w\').write(\'x\')" curiosity'}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["py_modifications"], 1)
        self.assertFalse(res["passed"])
        self.assertNotEqual(res["level"], "fast_pass")

    def test_sed_inplace_counts_as_modification(self):
        lines = [_start("bash", {"command": "sed -i 's/a/b/' swda/x.py"}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["py_modifications"], 1)
        self.assertIn("x.py", res["modified_files"])
        self.assertFalse(res["passed"])

    def test_git_apply_never_fast_pass(self):
        lines = [_start("bash", {"command": "git apply fix.patch"}, "c1")]
        res = scan_lines(lines)
        self.assertEqual(res["py_modifications"], 1)
        self.assertFalse(res["passed"])

    def test_spec_less_walk_caps_at_gate(self):
        lines = [
            _assistant_text("<INTENT_GATE_RESULT>\nA\n</INTENT_GATE_RESULT>\n[NEXT_STATE: PHASE_1_DESTRUCT]"),
            _start("edit", {"path": "x.py"}, "c1"),
            _start("swda_reconcile", {"file": "swda/x.py"}, "c2"),
            _result("swda_reconcile", "c2", '{"valid": true, "verdict": "valid", "errors": []}'),
            _assistant_text("<HYPERPLAN_RESULT>\nH\n</HYPERPLAN_RESULT>\n[NEXT_STATE: Y]\n<TASK_SUMMARY_REPORT>\nQ\n</TASK_SUMMARY_REPORT>\n[NEXT_STATE: None]"),
        ]
        res = scan_lines(lines)
        self.assertTrue(res["passed"])
        self.assertEqual(res["level"], "gate")
        self.assertTrue(any("SYSTEM_SPECIFICATION" in m for m in res["missing"]))

    def test_live_baseline_zero_mcp_deliveries(self):
        if not os.path.isdir(SESSIONS_DIR):
            self.skipTest("no OMP sessions on this machine")
        total = 0
        for name in sorted(os.listdir(SESSIONS_DIR)):
            if not name.endswith(".jsonl"):
                continue
            with open(os.path.join(SESSIONS_DIR, name), encoding="utf-8", errors="replace") as f:
                res = scan_lines(f)
            total += sum(res["swda_tool_calls"].values())
        # Baseline as of 2026-09-16: swda-mcp registered, never invoked from OMP.
        # Flip this assertion once the first trap probe lands.
        self.assertEqual(total, 0, "unexpected: an OMP session invoked swda tools")


if __name__ == "__main__":
    unittest.main()
