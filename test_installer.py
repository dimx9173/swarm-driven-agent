#!/usr/bin/env python3
import unittest
import tempfile
import os
import shutil
import re
import subprocess
import sys

# Import helper functions directly from installer.py
import installer

class TestSDAInstaller(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_home = os.path.join(self.test_dir, "mock_home")
        os.makedirs(self.mock_home)
        
        # Save original home
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = self.mock_home
        
        # Paths for mock agents
        self.hermes_profile_dir = os.path.join(self.mock_home, ".hermes", "profiles", "test_hermes")
        self.openclaw_workspace_dir = os.path.join(self.mock_home, ".openclaw", "workspaces", "test_openclaw")
        
        os.makedirs(self.hermes_profile_dir, exist_ok=True)
        os.makedirs(self.openclaw_workspace_dir, exist_ok=True)
        
        # Base templates versions
        self.template_versions = {
            "SOUL.md": "13.0.0-deterministic",
            "RULE.md": "2.0.0-agent-optimized",
            "SKILL.md": "2.0.0 (Deterministic-Actionable)"
        }

    def tearDown(self):
        # Restore home
        if self.original_home:
            os.environ["HOME"] = self.original_home
        else:
            del os.environ["HOME"]
            
        shutil.rmtree(self.test_dir)

    def test_parse_semver(self):
        self.assertEqual(installer.parse_semver("13.0.0-deterministic"), (13, 0, 0))
        self.assertEqual(installer.parse_semver("2.0.0-agent-optimized"), (2, 0, 0))
        self.assertEqual(installer.parse_semver("2.0.0 (Deterministic-Actionable)"), (2, 0, 0))
        self.assertEqual(installer.parse_semver(""), (0, 0, 0))
        self.assertEqual(installer.parse_semver(None), (0, 0, 0))

    def test_uninstall_soul_content(self):
        sample_soul = (
            "---\n"
            "system_core: \"Systemic Orchestration & Unification Logic (SOUL)\"\n"
            "version: \"13.0.0-deterministic\"\n"
            "related:\n"
            "  - \"RULE Engine Contract: [RULE.md](RULE.md)\"\n"
            "  - \"SWDD Development Skill: [SKILL.md](skills/swarm/SKILL.md)\"\n"
            "---\n"
            "# 1. 系統定位 (System Identity)\n"
            "你是一個全能的智慧 Agent。\n"
            "\n"
            "---\n"
            "# 2. 認知合約與運行規範 (System Contract & Protocols)\n"
            "Some FSM rules...\n"
        )
        expected = (
            "---\n"
            "system_core: \"Systemic Orchestration & Unification Logic (SOUL)\"\n"
            "version: \"13.0.0-deterministic\"\n"
            "---\n"
            "# 1. 系統定位 (System Identity)\n"
            "你是一個全能的智慧 Agent。"
        )
        result = installer.uninstall_soul_content(sample_soul).strip()
        self.assertEqual(result, expected)

    def test_merge_soul_content(self):
        target = "# 1. 系統定位\nPreserve this custom identity.\n"
        template = (
            "---\n"
            "version: \"13.0.0-deterministic\"\n"
            "---\n"
            "# 1. 系統定位\nTemplate positioning.\n"
            "\n"
            "---\n"
            "# 2. 認知合約與運行規範\nTemplate FSM rules.\n"
        )
        merged = installer.merge_soul_content(target, template)
        self.assertIn("Preserve this custom identity.", merged)
        self.assertIn("Template FSM rules.", merged)
        self.assertNotIn("Template positioning.", merged)

    def test_scan_agents_with_home_in_parent_path(self):
        # Create a mock home directory structure containing "/home/" in its path
        home_with_slash_home = os.path.join(self.test_dir, "home", "carlos")
        os.makedirs(home_with_slash_home, exist_ok=True)
        
        # Backup original environment home
        original_home = os.environ.get("HOME")
        os.environ["HOME"] = home_with_slash_home
        
        try:
            # Create a mock agent in this home structure
            workspace_dir = os.path.join(home_with_slash_home, ".openclaw", "workspaces", "devpc_agent")
            os.makedirs(workspace_dir, exist_ok=True)
            with open(os.path.join(workspace_dir, "SOUL.md"), "w") as f:
                f.write("# 1. 系統定位\nDevPC agent identity\n")
                
            # Create a folder that SHOULD be skipped (nested mock home inside the agent)
            skipped_dir = os.path.join(workspace_dir, "home", "nested_dir")
            os.makedirs(skipped_dir, exist_ok=True)
            with open(os.path.join(skipped_dir, "SOUL.md"), "w") as f:
                f.write("# 1. 系統定位\nShould be skipped\n")
            
            # Scan agents
            agents = installer.scan_agents()
            
            # We should detect 'devpc_agent', but NOT the nested 'SOUL.md' in skipped_dir
            names = [a['name'] for a in agents]
            self.assertIn("devpc_agent", names)
            self.assertNotIn("nested_dir", names)
            self.assertEqual(len(agents), 1)
        finally:
            if original_home:
                os.environ["HOME"] = original_home
            else:
                del os.environ["HOME"]

    def test_cli_create_agent(self):
        # Run installer command to create a new agent
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer.py")
        result = subprocess.run(
            [sys.executable, script_path, "--create", "new_cli_agent", "--type", "openclaw", "--identity", "Testing CLI creation.", "-y"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        
        # Verify files were created
        agent_dir = os.path.join(self.mock_home, ".openclaw", "workspaces", "new_cli_agent")
        self.assertTrue(os.path.exists(os.path.join(agent_dir, "SOUL.md")))
        self.assertTrue(os.path.exists(os.path.join(agent_dir, "RULE.md")))
        self.assertTrue(os.path.exists(os.path.join(agent_dir, "skills", "swarm", "SKILL.md")))
        
        with open(os.path.join(agent_dir, "SOUL.md"), "r") as f:
            content = f.read()
            self.assertIn("Testing CLI creation.", content)

    def test_cli_install_check_uninstall_e2e(self):
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer.py")
        
        # 1. Create a dummy agent that is not installed
        with open(os.path.join(self.openclaw_workspace_dir, "SOUL.md"), "w") as f:
            f.write("# 1. 系統定位\nFinance Agent positioning.\n")
            
        # 2. Run check and verify status is "Not Installed"
        result = subprocess.run(
            [sys.executable, script_path, "--check"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Status:  Not Installed", result.stdout)
        
        # 3. Run install on all agents
        result = subprocess.run(
            [sys.executable, script_path, "-y", "all"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully installed/upgraded", result.stdout)
        
        # Verify files are installed
        self.assertTrue(os.path.exists(os.path.join(self.openclaw_workspace_dir, "RULE.md")))
        self.assertTrue(os.path.exists(os.path.join(self.openclaw_workspace_dir, "skills", "swarm", "SKILL.md")))
        
        # 4. Run check and verify status is "Up-to-date"
        result = subprocess.run(
            [sys.executable, script_path, "--check"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Status:  Up-to-date", result.stdout)
        
        # 5. Run uninstall
        result = subprocess.run(
            [sys.executable, script_path, "--uninstall", "-y", "all"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully uninstalled", result.stdout)
        
        # Verify files were removed
        self.assertFalse(os.path.exists(os.path.join(self.openclaw_workspace_dir, "RULE.md")))
        self.assertFalse(os.path.exists(os.path.join(self.openclaw_workspace_dir, "skills", "swarm", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(self.openclaw_workspace_dir, "skills")))
        
        # Verify SOUL.md reverted
        with open(os.path.join(self.openclaw_workspace_dir, "SOUL.md"), "r") as f:
            content = f.read()
            self.assertNotIn("RULE Engine Contract", content)
            self.assertNotIn("SWDD Development Skill", content)
            self.assertIn("Finance Agent positioning.", content)

if __name__ == '__main__':
    unittest.main()
