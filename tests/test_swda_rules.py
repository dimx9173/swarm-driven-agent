#!/usr/bin/env python3
"""
SWDA Rule & Template Integrity Unit Tests.
Verifies that SWDA templates contain mandatory Socratic Grilling, Scientific Debugging 6-Phase,
and Trajectory Regulation Gate [DEBUG-xxxx] log cleanup clauses across both Chinese and English bundles.
"""
import unittest
import os
import re

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULAR_DIR = os.path.join(ROOT_DIR, "template", "modular")
INTEGRATED_DIR = os.path.join(ROOT_DIR, "template", "integrated")

def scan_for_debug_tags(code_or_log_text: str) -> list[str]:
    """
    Scanner function for Trajectory Regulation Gate.
    Detects any lingering [DEBUG-xxxx] tags in submitted code or logs.
    """
    pattern = r"\[DEBUG-[a-zA-Z0-9_-]+\]"
    return re.findall(pattern, code_or_log_text)

class TestSWDARulesAndTemplates(unittest.TestCase):
    def setUp(self):
        self.skill_zh = os.path.join(MODULAR_DIR, "SKILL.md")
        self.skill_en = os.path.join(MODULAR_DIR, "SKILL.en.md")
        self.rule_zh = os.path.join(MODULAR_DIR, "RULE.md")
        self.rule_en = os.path.join(MODULAR_DIR, "RULE.en.md")
        self.soul_zh = os.path.join(MODULAR_DIR, "SOUL.md")
        self.soul_en = os.path.join(MODULAR_DIR, "SOUL.en.md")
        self.all_in_zh = os.path.join(INTEGRATED_DIR, "ALL_IN_RULE.md")
        self.all_in_en = os.path.join(INTEGRATED_DIR, "ALL_IN_RULE.en.md")

    def test_template_files_exist(self):
        for path in [self.skill_zh, self.skill_en, self.rule_zh, self.rule_en,
                     self.soul_zh, self.soul_en, self.all_in_zh, self.all_in_en]:
            self.assertTrue(os.path.exists(path), f"Template missing: {path}")

    def test_skill_md_has_grilling_gate(self):
        # Check Chinese version
        with open(self.skill_zh, "r", encoding="utf-8") as f:
            content_zh = f.read()
        self.assertIn("Conditional Socratic Grilling Gate", content_zh)
        self.assertIn("1-question-at-a-time", content_zh)
        self.assertIn("推薦選項與理由", content_zh)

        # Check English version
        with open(self.skill_en, "r", encoding="utf-8") as f:
            content_en = f.read()
        self.assertIn("Conditional Socratic Grilling Gate", content_en)
        self.assertIn("1-question-at-a-time", content_en)
        self.assertIn("recommended option and rationale", content_en)

    def test_skill_md_has_scientific_debugging_and_tag_cleanup(self):
        # Check Chinese version
        with open(self.skill_zh, "r", encoding="utf-8") as f:
            content_zh = f.read()
        self.assertIn("Scientific Debugging & TDD", content_zh)
        self.assertIn("可證偽假說", content_zh)
        self.assertIn("[DEBUG-xxxx]", content_zh)
        self.assertIn("偵錯日誌標籤", content_zh)

        # Check English version
        with open(self.skill_en, "r", encoding="utf-8") as f:
            content_en = f.read()
        self.assertIn("Scientific Debugging & TDD", content_en)
        self.assertIn("falsifiable hypotheses", content_en.lower())
        self.assertIn("[DEBUG-xxxx]", content_en)
        self.assertIn("debug instrumentation tags", content_en.lower())

    def test_rule_md_trajectory_gate_has_debug_scanner(self):
        for rule_path in [self.rule_zh, self.rule_en, self.all_in_zh, self.all_in_en]:
            with open(rule_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Trajectory Regulation Gate", content, f"Missing Trajectory Gate in {rule_path}")
            self.assertIn("[DEBUG-xxxx]", content, f"Missing [DEBUG-xxxx] in {rule_path}")

    def test_debug_tag_scanner_utility(self):
        clean_code = "def add(a, b):\n    return a + b\n"
        dirty_code = "def add(a, b):\n    print('[DEBUG-a4f2] inputs:', a, b)\n    return a + b\n"
        
        self.assertEqual(scan_for_debug_tags(clean_code), [])
        self.assertEqual(scan_for_debug_tags(dirty_code), ["[DEBUG-a4f2]"])

    def test_strict_fsm_phase_lock_across_all_templates(self):
        with open(self.soul_zh, "r", encoding="utf-8") as f:
            self.assertIn("FSM 階段與工具權限強鎖定", f.read())

        with open(self.soul_en, "r", encoding="utf-8") as f:
            self.assertIn("Strict FSM Phase & Tool Lock", f.read())

        with open(self.rule_zh, "r", encoding="utf-8") as f:
            self.assertIn("Strict FSM Phase Lock", f.read())

        with open(self.rule_en, "r", encoding="utf-8") as f:
            self.assertIn("Strict FSM Phase & Tool Lock", f.read())

        with open(self.all_in_zh, "r", encoding="utf-8") as f:
            self.assertIn("Strict FSM Phase Lock", f.read())

        with open(self.all_in_en, "r", encoding="utf-8") as f:
            self.assertIn("Strict FSM Phase & Tool Lock", f.read())

    def test_firewall_precedence_hierarchy_has_full_tc_range(self):
        for rule_path in [self.rule_zh, self.rule_en, self.all_in_zh, self.all_in_en]:
            with open(rule_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("TC-01 ~ TC-10", content, f"Missing TC-01 ~ TC-10 range in {rule_path}")
            self.assertIn("TC-10", content, f"Missing TC-10 definition in {rule_path}")

    def test_omp_topology_hierarchy_and_academic_protocols(self):
        """Verifies Three-Tier Topology Hierarchy, Zero-TypeError Pre-flight, and State Hygiene Rollback."""
        for rule_path in [self.rule_zh, self.rule_en, self.all_in_zh, self.all_in_en]:
            with open(rule_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Three-Tier Topology Hierarchy", content, f"Missing Three-Tier Topology in {rule_path}")
            self.assertIn("find_references", content, f"Missing LSP find_references in {rule_path}")
            self.assertIn("goto_definition", content, f"Missing LSP goto_definition in {rule_path}")
            self.assertIn("Zero-TypeError Pre-flight", content, f"Missing Zero-TypeError Pre-flight in {rule_path}")
            self.assertIn("State Hygiene Rollback Protocol", content, f"Missing State Hygiene Rollback in {rule_path}")
            self.assertIn("arXiv:2605.22166", content, f"Missing Life-Harness citation in {rule_path}")

    def test_installed_local_omp_agent_integrity(self):
        """Verifies that if ~/.omp/agent/APPEND_SYSTEM.md exists, it matches the latest template version."""
        home_dir = os.path.expanduser("~")
        local_omp_append = os.path.join(home_dir, ".omp", "agent", "APPEND_SYSTEM.md")
        if os.path.exists(local_omp_append):
            with open(local_omp_append, "r", encoding="utf-8") as f:
                omp_content = f.read()
            with open(self.all_in_en, "r", encoding="utf-8") as f:
                expected_content = f.read()
            self.assertIn("version: 14.3.0-deterministic", omp_content)
            self.assertIn("Three-Tier Topology Hierarchy", omp_content)
            self.assertIn("find_references", omp_content)
            self.assertIn("State Hygiene Rollback Protocol", omp_content)


if __name__ == "__main__":
    unittest.main()
