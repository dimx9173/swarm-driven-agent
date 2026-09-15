"""
Unit tests for SWDA AI Firewall and AST security hooks.
"""

import unittest
from swda.core.firewall import SafetyFirewall, SecurityFirewallException


class TestSafetyFirewall(unittest.TestCase):

    def test_audit_safe_command(self):
        # Should not raise
        SafetyFirewall.audit_command("git status")
        SafetyFirewall.audit_command("python3 -m unittest")

    def test_audit_catastrophic_deletion(self):
        with self.assertRaises(SecurityFirewallException) as ctx:
            SafetyFirewall.audit_command("rm -rf /")
        self.assertEqual(ctx.exception.rule_id, "TC-01")

        with self.assertRaises(SecurityFirewallException):
            SafetyFirewall.audit_command("rm -rf ~")

    def test_audit_credential_read(self):
        with self.assertRaises(SecurityFirewallException) as ctx:
            SafetyFirewall.audit_command("cat ~/.ssh/id_rsa")
        self.assertEqual(ctx.exception.rule_id, "TC-03")

        with self.assertRaises(SecurityFirewallException):
            SafetyFirewall.audit_command("cat .env")

    def test_audit_contract_tampering(self):
        with self.assertRaises(SecurityFirewallException) as ctx:
            SafetyFirewall.audit_command("rm template/modular/RULE.md")
        self.assertEqual(ctx.exception.rule_id, "TC-07")

    def test_ast_file_mutation_forbidden_in_gather(self):
        mutation_code = "with open('foo.py', 'w') as f:\n    f.write('bad code')"
        with self.assertRaises(SecurityFirewallException) as ctx:
            SafetyFirewall.audit_code_ast(mutation_code, current_phase="PHASE_2_GATHER")
        self.assertEqual(ctx.exception.rule_id, "RULE-0.7")

    def test_ast_file_mutation_allowed_in_implement(self):
        mutation_code = "with open('foo.py', 'w') as f:\n    f.write('good code')"
        # Should not raise in IMPLEMENT phase
        SafetyFirewall.audit_code_ast(mutation_code, current_phase="PHASE_6_IMPLEMENT")

    def test_ast_read_allowed_in_gather(self):
        read_code = "with open('foo.py', 'r') as f:\n    content = f.read()"
        # Should not raise
        SafetyFirewall.audit_code_ast(read_code, current_phase="PHASE_2_GATHER")


if __name__ == "__main__":
    unittest.main()
