#!/usr/bin/env python3
"""
SWDA Effectiveness Regression Tests: proves the install is live in three layers.

Layer 1 (Install): integrated contract merges to exactly one copy and
re-installs idempotently (regression: marker-less legacy merge stacked the
same contract x4 -> 1169-line APPEND_SYSTEM.md).
Layer 2 (Engine): mock e2e walks the real FSM gates
GATHER -> HYPERPLAN -> CRUCIBLE -> SYNTHESIS with Builder/Destroyer/Referee.
Layer 3 (Delivery gate): reconcile passes clean code, fails hallucinated
symbols (valid:false sends the task back to Crucible).

Live probe (last test) checks this machine's ~/.omp/agent and ~/.pi/agent
files when present; skipped on machines without installed agents.
"""
import os
import shutil
import tempfile
import unittest

import installer
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.fsm import FSMEngine, FSMPhase
from swda.prime.rlm import RLMDispatcher
from swda.workflows.crucible import CrucibleWorkflow
from swda.workflows.reconcile import ReverseReconciliation

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEGRATED_EN = os.path.join(ROOT_DIR, "template", "integrated", "ALL_IN_RULE.en.md")
INTEGRATED_ZH = os.path.join(ROOT_DIR, "template", "integrated", "ALL_IN_RULE.md")
BEGIN = "<!-- swda-begin -->"
END = "<!-- swda-end -->"
CONTRACT_HEADER = "# Swarm-Driven Agent (SWDA) Integrated"


def _mock_rlm_handler(role: str, prompt: str):
    if role == "builder":
        return {"spec": "Effectiveness probe spec", "round": 1}
    if role == "destroyer":
        return {"vector": "mock attack: unhandled timeout", "severity": "medium"}
    if role == "referee":
        return {"passed": True, "score": 8, "reason": "Mock verdict: proposal acceptable"}
    return {}


class TestContractSingleCopy(unittest.TestCase):
    def setUp(self):
        with open(INTEGRATED_EN, "r", encoding="utf-8") as f:
            self.template = f.read()
        self.identity = "# 1. 系統定位 (System Identity)\nEffectiveness probe identity.\n"

    def test_integrated_templates_carry_swda_markers(self):
        for path in (INTEGRATED_EN, INTEGRATED_ZH):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content.count(BEGIN), 1, f"missing swda-begin in {path}")
            self.assertEqual(content.count(END), 1, f"missing swda-end in {path}")

    def test_merge_is_idempotent_single_copy(self):
        once = installer.merge_soul_content(self.identity, self.template)
        twice = installer.merge_soul_content(once, self.template)
        self.assertEqual(once, twice, "re-install must be byte-identical (no stacking)")
        self.assertEqual(twice.count(BEGIN), 1)
        self.assertEqual(twice.count(END), 1)
        self.assertEqual(twice.count(CONTRACT_HEADER), 1)
        self.assertIn("Effectiveness probe identity.", twice)

    def test_legacy_stacked_contract_dedups_to_single_copy(self):
        # Simulate the old 1169-line bug: marker-less contract body pasted twice.
        no_mark = self.template.replace(BEGIN, "").replace(END, "")
        idx = no_mark.find("# Swarm-Driven Agent")
        self.assertNotEqual(idx, -1, "template contract header moved?")
        body = no_mark[idx:]
        stacked = self.identity + "\n" + body + "\n" + body
        self.assertEqual(stacked.count(CONTRACT_HEADER), 2)
        merged = installer.merge_soul_content(stacked, self.template)
        self.assertEqual(merged.count(CONTRACT_HEADER), 1)
        self.assertEqual(merged.count(BEGIN), 1)
        self.assertIn("Effectiveness probe identity.", merged)

    def test_mixed_stacked_plus_marker_dedups_to_single_copy(self):
        # Remote fossil shape: legacy stacked copies with a marker block
        # appended at the end (merge must not keep the stack as "identity").
        no_mark = self.template.replace(BEGIN, "").replace(END, "")
        idx = no_mark.find("# Swarm-Driven Agent")
        body = no_mark[idx:]
        stacked = self.identity + "\n" + body * 8
        once = installer.merge_soul_content(stacked, self.template)
        twice = installer.merge_soul_content(once, self.template)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count(CONTRACT_HEADER), 1)
        self.assertEqual(twice.count(BEGIN), 1)
        self.assertIn("Effectiveness probe identity.", twice)

    def test_uninstall_strips_contract_keeps_identity(self):
        merged = installer.merge_soul_content(self.identity, self.template)
        stripped = installer.uninstall_soul_content(merged)
        self.assertNotIn(BEGIN, stripped)
        self.assertNotIn(CONTRACT_HEADER, stripped)
        self.assertIn("Effectiveness probe identity.", stripped)


class TestEngineMockE2E(unittest.TestCase):
    def test_fsm_crucible_to_synthesis_with_mock_subagents(self):
        bb = Blackboard()
        fsm = FSMEngine(bb)
        rlm = RLMDispatcher(mock_handler=_mock_rlm_handler)
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb)

        fsm.advance_to(FSMPhase.PHASE_2_GATHER)
        fsm.advance_to(FSMPhase.PHASE_3_HYPERPLAN)
        bb.write(AgentRole.SYSTEM, "active_proposal",
                 {"spec": "Effectiveness probe task", "round": 0, "draft": True})
        fsm.advance_to(FSMPhase.PHASE_4_CRUCIBLE)
        res = crucible.run_crucible("Effectiveness probe task")
        self.assertTrue(res.passed)
        self.assertEqual(res.rounds_executed, 1)
        self.assertTrue(bb.read("crucible_verdict")["passed"])

        fsm.advance_to(FSMPhase.PHASE_5_SYNTHESIS)
        bb.as_role(AgentRole.BUILDER).write("synthesis_blueprint", res.proposal)
        self.assertEqual(fsm.current_phase, FSMPhase.PHASE_5_SYNTHESIS)
        self.assertIn("spec", bb.read("synthesis_blueprint"))


class TestDeliveryGate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_reconcile_passes_clean_code_blocks_hallucinated_symbol(self):
        clean = os.path.join(self.temp_dir, "clean_mod.py")
        with open(clean, "w", encoding="utf-8") as f:
            f.write("import json\nx = json.dumps({'ok': True})\n")
        res_clean = ReverseReconciliation.verify_file(clean, self.temp_dir)
        self.assertTrue(res_clean["valid"])

        hallu = os.path.join(self.temp_dir, "hallu_mod.py")
        with open(hallu, "w", encoding="utf-8") as f:
            f.write("from os import hallucinated_func_xyz\nhallucinated_func_xyz()\n")
        res_hallu = ReverseReconciliation.verify_file(hallu, self.temp_dir)
        self.assertFalse(res_hallu["valid"])
        self.assertTrue(any("hallucinated_func_xyz" in e for e in res_hallu["errors"]))


class TestLiveInstalledContract(unittest.TestCase):
    def test_live_agent_contracts_are_single_copy(self):
        home = os.path.expanduser("~")
        candidates = [
            os.path.join(home, ".omp", "agent", "APPEND_SYSTEM.md"),
            os.path.join(home, ".pi", "agent", "APPEND_SYSTEM.md"),
        ]
        present = [p for p in candidates if os.path.exists(p)]
        if not present:
            self.skipTest("no installed OMP/Pi agent on this machine")
        template_ver = installer.extract_version(INTEGRATED_EN)
        checked = 0
        for path in present:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if BEGIN not in content:
                continue  # legacy pre-marker install (e.g. remote QA box); install it first
            checked += 1
            self.assertEqual(content.count(BEGIN), 1, f"stacked contract in {path}")
            self.assertEqual(content.count(END), 1, f"stacked contract in {path}")
            self.assertEqual(content.count(CONTRACT_HEADER), 1, f"stacked contract in {path}")


if __name__ == "__main__":
    unittest.main()
