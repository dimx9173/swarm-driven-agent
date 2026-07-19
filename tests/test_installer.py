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

class TestSWDAInstaller(unittest.TestCase):
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
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
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
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # 1. Create a dummy agent that is not installed
        with open(os.path.join(self.openclaw_workspace_dir, "SOUL.md"), "w") as f:
            f.write("# 1. 系統定位\nFinance Agent positioning.\n")
            
        # 2. Run check and verify it is not checked (since it's not registered/installed)
        result = subprocess.run(
            [sys.executable, script_path, "doctor"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("No installed agents tracked", result.stdout)
        
        # 3. Run install on the dummy agent (which registers it)
        result = subprocess.run(
            [sys.executable, script_path, "install", "test_openclaw", "-y"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully installed/upgraded", result.stdout)
        
        # Verify files are installed
        self.assertTrue(os.path.exists(os.path.join(self.openclaw_workspace_dir, "RULE.md")))
        self.assertTrue(os.path.exists(os.path.join(self.openclaw_workspace_dir, "skills", "swarm", "SKILL.md")))
        
        # 4. Run check (doctor) and verify status is "Up-to-date" (now registered/installed)
        result = subprocess.run(
            [sys.executable, script_path, "doctor"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Status:  Up-to-date", result.stdout)
        
        # 5. Run uninstall
        result = subprocess.run(
            [sys.executable, script_path, "install", "--uninstall", "-y", "test_openclaw"],
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

    def test_cli_comma_separated_agents(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Create two mock agents
        os.makedirs(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent1"), exist_ok=True)
        os.makedirs(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent2"), exist_ok=True)
        
        with open(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent1", "SOUL.md"), "w") as f:
            f.write("# 1. 系統定位\nAgent 1\n")
        with open(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent2", "SOUL.md"), "w") as f:
            f.write("# 1. 系統定位\nAgent 2\n")
            
        # Run install passing agent1,agent2 as a comma-separated list
        result = subprocess.run(
            [sys.executable, script_path, "install", "agent1,agent2", "-y"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully installed/upgraded SWDA for: agent1", result.stdout)
        self.assertIn("Successfully installed/upgraded SWDA for: agent2", result.stdout)
        
        # Verify files created
        self.assertTrue(os.path.exists(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent1", "RULE.md")))
        self.assertTrue(os.path.exists(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent2", "RULE.md")))

    def test_cli_update_command(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Create a mock agent
        os.makedirs(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent_up"), exist_ok=True)
        with open(os.path.join(self.mock_home, ".openclaw", "workspaces", "agent_up", "SOUL.md"), "w") as f:
            f.write("# 1. 系統定位\nAgent Update\n")
            
        # Run update subcommand with --agents
        result = subprocess.run(
            [sys.executable, script_path, "update", "--agents", "agent_up", "-y"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully installed/upgraded SWDA for: agent_up", result.stdout)
    def test_cli_version_command(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Test `version` subcommand
        result = subprocess.run(
            [sys.executable, script_path, "version"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Swarm-Driven Agent (SWDA) Version", result.stdout)
        self.assertIn("Current version:", result.stdout)

        # Test `-v` mapping
        result_v = subprocess.run(
            [sys.executable, script_path, "-v"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result_v.returncode, 0)
        self.assertIn("Current version:", result_v.stdout)

    def test_cli_discover_command(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Test `discover` subcommand
        result = subprocess.run(
            [sys.executable, script_path, "discover", "tdd"],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("SWDA Skill Discovery", result.stdout)
        self.assertIn("tdd (engineering)", result.stdout)

    def test_cli_learn_command(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Create mock customization root
        agents_dir = os.path.join(self.mock_home, ".agents")
        os.makedirs(agents_dir, exist_ok=True)
        
        # Run `learn` subcommand with a known catalog skill name
        result = subprocess.run(
            [sys.executable, script_path, "learn", "tdd", "-y"],
            cwd=self.mock_home,
            capture_output=True,
            text=True,
            env={"SWDA_TEST_MODE": "1", **os.environ}
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Successfully learned and installed skill: 'tdd'", result.stdout)
        
        # Verify SKILL.md file created in the local mock customization root
        skill_file = os.path.join(agents_dir, "skills", "tdd", "SKILL.md")
        self.assertTrue(os.path.exists(skill_file))
        
        # Test AI generation fallback by specifying a custom topic name
        result_gen = subprocess.run(
            [sys.executable, script_path, "learn", "custom-redis-topic", "-y"],
            cwd=self.mock_home,
            capture_output=True,
            text=True,
            env={"SWDA_TEST_MODE": "1", **os.environ}
        )
        self.assertEqual(result_gen.returncode, 0)
        self.assertIn("Successfully learned and installed skill: 'custom-redis-topic'", result_gen.stdout)
        
        # Verify generated file exists
        gen_skill_file = os.path.join(agents_dir, "skills", "custom-redis-topic", "SKILL.md")
        self.assertTrue(os.path.exists(gen_skill_file))
        with open(gen_skill_file, "r") as f:
            gen_content = f.read()
            self.assertIn("custom-redis-topic", gen_content)

    def test_cli_learn_from_codebase_command(self):
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
        
        # Create a mock codebase directory structure inside mock_home
        codebase_dir = os.path.join(self.mock_home, "my_mock_project")
        os.makedirs(os.path.join(codebase_dir, "src"), exist_ok=True)
        os.makedirs(os.path.join(codebase_dir, "tests"), exist_ok=True)
        
        # Write setup.py and CLAUDE.md
        with open(os.path.join(codebase_dir, "setup.py"), "w") as f:
            f.write("# setup config\nversion='1.0.0'\n")
        with open(os.path.join(codebase_dir, "CLAUDE.md"), "w") as f:
            f.write("Developer Instructions for mock project")
            
        # Create mock customizations root
        agents_dir = os.path.join(self.mock_home, ".agents")
        os.makedirs(agents_dir, exist_ok=True)
        
        # Run learn command with --from-codebase pointing to my_mock_project
        result = subprocess.run(
            [sys.executable, script_path, "learn", "my-project-spec", "--from-codebase", codebase_dir, "-y"],
            cwd=self.mock_home,
            capture_output=True,
            text=True,
            env={"SWDA_TEST_MODE": "1", **os.environ}
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Learning conventions from codebase at:", result.stdout)
        self.assertIn("Successfully learned and installed skill: 'my-project-spec'", result.stdout)
        
        # Verify the generated SKILL.md contains mock codebase topology info
        skill_file = os.path.join(agents_dir, "skills", "my-project-spec", "SKILL.md")
        self.assertTrue(os.path.exists(skill_file))
        with open(skill_file, "r") as f:
            content = f.read()
            # The mock learn implementation adds codebase topology to the file in test mode
            self.assertIn("Codebase topology:", content)
            self.assertIn("my_mock_project", content)

if __name__ == '__main__':
    unittest.main()
