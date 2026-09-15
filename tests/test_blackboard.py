"""
Unit tests for SWDA Core Blackboard with RBAC permissions.
"""

import unittest
from swda.core.blackboard import Blackboard, AgentRole


class TestBlackboard(unittest.TestCase):

    def setUp(self):
        self.bb = Blackboard(task_id="test_task")

    def test_initial_state(self):
        self.assertEqual(self.bb.read("phase"), "INTENT_GATE")
        self.assertEqual(self.bb.read("active_proposal"), None)
        self.assertEqual(self.bb.read("crucible_critiques"), [])

    def test_builder_write_proposal_allowed(self):
        proposal = {"spec": "Refactor auth system", "modules": ["auth.py"]}
        self.bb.write(AgentRole.BUILDER, "active_proposal", proposal)
        self.assertEqual(self.bb.read("active_proposal"), proposal)

    def test_destroyer_write_proposal_forbidden(self):
        proposal = {"spec": "Hacked proposal"}
        with self.assertRaises(PermissionError):
            self.bb.write(AgentRole.DESTROYER, "active_proposal", proposal)

    def test_destroyer_write_critique_allowed(self):
        critiques = [{"vector": "race condition in token refresh"}]
        self.bb.write(AgentRole.DESTROYER, "crucible_critiques", critiques)
        self.assertEqual(self.bb.read("crucible_critiques"), critiques)

    def test_builder_write_verdict_forbidden(self):
        verdict = {"passed": True}
        with self.assertRaises(PermissionError):
            self.bb.write(AgentRole.BUILDER, "crucible_verdict", verdict)

    def test_referee_write_verdict_allowed(self):
        verdict = {"passed": True, "score": 9}
        self.bb.write(AgentRole.REFEREE, "crucible_verdict", verdict)
        self.assertEqual(self.bb.read("crucible_verdict"), verdict)

    def test_invalid_key_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.bb.read("non_existent_key")
        with self.assertRaises(KeyError):
            self.bb.write(AgentRole.SYSTEM, "non_existent_key", 123)


if __name__ == "__main__":
    unittest.main()
