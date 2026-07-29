#!/usr/bin/env python3
"""
SWDA Rule & Template Integrity Unit Tests.
Verifies that SWDA templates contain mandatory Socratic Grilling, Scientific Debugging 6-Phase,
and Trajectory Regulation Gate [DEBUG-xxxx] log cleanup clauses.
"""
import unittest
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(ROOT_DIR, "template", "modular")

def scan_for_debug_tags(code_or_log_text: str) -> list[str]:
    """
    Scanner function for Trajectory Regulation Gate.
    Detects any lingering [DEBUG-xxxx] tags in submitted code or logs.
    """
    pattern = r"\[DEBUG-[a-zA-Z0-9_-]+\]"
    return re.findall(pattern, code_or_log_text)

class TestSWDARulesAndTemplates(unittest.TestCase):
    def setUp(self):
        self.skill_path = os.path.join(TEMPLATE_DIR, "SKILL.md")
        self.rule_path = os.path.join(TEMPLATE_DIR, "RULE.md")
        self.soul_path = os.path.join(TEMPLATE_DIR, "SOUL.md")

    def test_template_files_exist(self):
        self.assertTrue(os.path.exists(self.skill_path), "SKILL.md template missing")
        self.assertTrue(os.path.exists(self.rule_path), "RULE.md template missing")
        self.assertTrue(os.path.exists(self.soul_path), "SOUL.md template missing")

    def test_skill_md_has_grilling_gate(self):
        with open(self.skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Conditional Socratic Grilling Gate", content)
        self.assertIn("1-question-at-a-time", content)
        self.assertIn("推薦選項與理由", content)

    def test_skill_md_has_scientific_debugging_and_tag_cleanup(self):
        with open(self.skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Scientific Debugging & TDD", content)
        self.assertIn("可證偽假說", content)
        self.assertIn("[DEBUG-xxxx]", content)
        self.assertIn("偵錯日誌標籤", content)

    def test_rule_md_trajectory_gate_has_debug_scanner(self):
        with open(self.rule_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Trajectory Regulation Gate", content)
        self.assertIn("[DEBUG-xxxx]", content)

    def test_debug_tag_scanner_utility(self):
        clean_code = "def add(a, b):\n    return a + b\n"
        dirty_code = "def add(a, b):\n    print('[DEBUG-a4f2] inputs:', a, b)\n    return a + b\n"
        
        self.assertEqual(scan_for_debug_tags(clean_code), [])
        self.assertEqual(scan_for_debug_tags(dirty_code), ["[DEBUG-a4f2]"])

    def test_soul_and_rule_has_strict_fsm_phase_lock(self):
        with open(self.soul_path, "r", encoding="utf-8") as f:
            soul_content = f.read()
        self.assertIn("FSM 階段與工具權限強鎖定", soul_content)

        with open(self.rule_path, "r", encoding="utf-8") as f:
            rule_content = f.read()
        self.assertIn("Strict FSM Phase Lock", rule_content)

        all_in_rule_path = os.path.join(ROOT_DIR, "template", "integrated", "ALL_IN_RULE.md")
        with open(all_in_rule_path, "r", encoding="utf-8") as f:
            all_in_content = f.read()
        self.assertIn("Strict FSM Phase Lock", all_in_content)

if __name__ == "__main__":
    unittest.main()
