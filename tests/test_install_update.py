#!/usr/bin/env python3
"""
Regression tests for install/update CLI behavior (installer.py + swda.cli delegation).

Locks:
1. `update <names>` updates only the named agent (was: silently rewritten to all).
2. `update --type <t>` filters installed agents by type.
3. Bare `update` still updates every tracked agent.
4. `--create` without --type defaults to the openclaw layout.
5. `--create --type pi` routes into the .pi tree, uses the default identity
   (no literal "None"), and registers the agent for doctor/update tracking.
6. `python3 -m swda.cli doctor/self-update` delegates to the installer
   (was: argparse "invalid choice" error).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "installer.py")
REPO_ROOT = os.path.dirname(SCRIPT)


class UpdateScopeTest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_home = os.path.join(self.test_dir, "mock_home")
        os.makedirs(self.mock_home)
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = self.mock_home
        self.env = dict(os.environ)

    def tearDown(self):
        if self.original_home is not None:
            os.environ["HOME"] = self.original_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]
        shutil.rmtree(self.test_dir)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, env=self.env,
        )

    def _install_all(self):
        r = self._run("install", "--type", "all", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("Successfully installed/upgraded", r.stdout)
        return r

    def _tracked(self):
        with open(os.path.join(self.mock_home, ".swda", "installed_agents.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_update_single_name_selects_one_agent(self):
        self._install_all()
        r = self._run("update", "workspace", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("You selected 1 agent(s)", r.stdout)
        self.assertIn("workspace (OpenClaw)", r.stdout)

    def test_update_type_filter_selects_only_that_type(self):
        self._install_all()
        r = self._run("update", "--type", "omp", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("You selected 1 agent(s)", r.stdout)
        self.assertIn("(OMP)", r.stdout)

    def test_update_bare_still_updates_all_tracked(self):
        self._install_all()
        n = len(self._tracked())
        self.assertGreaterEqual(n, 2)
        r = self._run("update", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn(f"You selected {n} agent(s)", r.stdout)

    def test_create_defaults_to_openclaw_and_tracks(self):
        r = self._run("install", "--create", "bare_agent", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        soul = os.path.join(self.mock_home, ".openclaw", "workspaces", "bare_agent", "SOUL.md")
        self.assertTrue(os.path.exists(soul))
        self.assertTrue(any("bare_agent" in p for p in self._tracked()))

    def test_create_pi_routes_and_tracks_with_default_identity(self):
        r = self._run("install", "--create", "pi_probe", "--type", "pi", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        append = os.path.join(self.mock_home, ".pi", "agent", "profiles", "pi_probe", "APPEND_SYSTEM.md")
        self.assertTrue(os.path.exists(append))
        with open(append, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("System Identity)\nNone", content)
        self.assertIn("你是一個全能的智慧 Agent。", content)
        self.assertIn("<!-- swda-begin -->", content)
        self.assertTrue(any("pi_probe" in p for p in self._tracked()))

    def test_create_prime_routes_and_tracks(self):
        r = self._run("install", "--create", "prime_probe", "--type", "prime", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        append = os.path.join(self.mock_home, ".prime", "agent", "profiles", "prime_probe", "APPEND_SYSTEM.md")
        self.assertTrue(os.path.exists(append))
        with open(append, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<!-- swda-begin -->", content)
        self.assertTrue(any("prime_probe" in p for p in self._tracked()))

    def test_install_prime_type_detects_and_upgrades(self):
        prime_dir = os.path.join(self.mock_home, ".prime", "agent")
        os.makedirs(prime_dir, exist_ok=True)
        with open(os.path.join(prime_dir, "APPEND_SYSTEM.md"), "w", encoding="utf-8") as f:
            f.write("# 1. 系統定位 (System Identity)\ntest\n")
        r = self._run("install", "--type", "prime", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("Prime", r.stdout)
        r2 = self._run("doctor")
        self.assertEqual(r2.returncode, 0, r2.stderr[-500:])
        self.assertIn("Prime", r2.stdout)

    def test_create_hermes_registers_yaml_mcp(self):
        import installer as _installer
        cfg = os.path.join(self.mock_home, ".hermes", "config.yaml")
        os.makedirs(os.path.dirname(cfg), exist_ok=True)
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("plugins:\n  enabled:\n    - orca-status\n")
        r = self._run("install", "--create", "hermes_probe", "--type", "hermes", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        with open(cfg, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("swda-mcp:", content)
        self.assertIn("mcp_servers:", content)
        self.assertIn("orca-status", content)
        import glob as _glob
        self.assertTrue(_glob.glob(cfg + ".*.bak"))

    def test_doctor_supported_matrix(self):
        import installer as _installer
        prime = _installer.verify_agent_doctor("prime")
        self.assertTrue(prime["supported"])
        omp = _installer.verify_agent_doctor("omp")
        self.assertTrue(omp["supported"])
        for t in ("hermes", "openclaw", "pi"):
            d = _installer.verify_agent_doctor(t)
            self.assertFalse(d["supported"])
        base = os.path.join(REPO_ROOT, "swda-mcp", "prime-skill", "swda-skill")
        for rel in ("SKILL.md", "pyproject.toml", "src/swda/__init__.py",
                    "references/wiring.md"):
            self.assertTrue(os.path.exists(os.path.join(base, rel)), rel)
        with open(os.path.join(base, "src/swda/__init__.py"), encoding="utf-8") as f:
            src = f.read()
        tree = __import__("ast").parse(src)
        names = {n.name for n in __import__("ast").walk(tree)
                 if isinstance(n, __import__("ast").AsyncFunctionDef)}
        self.assertIn("reconcile", names)
        self.assertIn("audit", names)

    def test_corrupt_tracking_file_errors_loudly(self):
        self._install_all()
        cfg = os.path.join(self.mock_home, ".swda", "installed_agents.json")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        r = self._run("doctor")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("corrupt", (r.stdout + r.stderr).lower())

    def test_stale_tracking_entry_warns(self):
        self._install_all()
        tracked = self._tracked()
        shutil.rmtree(tracked[0])
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("stale entry", (r.stdout + r.stderr).lower())

class CliDelegationTest(unittest.TestCase):
    def test_module_entry_delegates_installer_commands(self):
        for cmd in ("doctor", "scan"):
            r = subprocess.run(
                [sys.executable, "-m", "swda.cli", cmd],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(r.returncode, 0, r.stderr[-500:])
            self.assertIn("Detected", r.stdout)

    def test_module_entry_self_update_test_mode(self):
        env = dict(os.environ, SWDA_TEST_MODE="1")
        r = subprocess.run(
            [sys.executable, "-m", "swda.cli", "self-update"],
            capture_output=True, text=True, env=env, cwd=REPO_ROOT,
        )
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("Test mode: upgrade_swda executed successfully.", r.stdout)


if __name__ == "__main__":
    unittest.main()
