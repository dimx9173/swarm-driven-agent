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
        self.env = dict(os.environ, SWDA_TEST_MODE="1")

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

    def test_prime_type_rejected(self):
        r = self._run("install", "--create", "prime_probe", "--type", "prime", "-y")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("invalid choice", (r.stdout + r.stderr))

    def test_create_hermes_installs_skill_no_mcp(self):
        import installer as _installer
        r = self._run("install", "--create", "hermes_probe", "--type", "hermes", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("Skill: installed", r.stdout)
        self.assertIn("contract + skill mode", r.stdout)
        skill = os.path.join(self.mock_home, ".hermes", "profiles", "hermes_probe",
                             "skills", "swda", "SKILL.md")
        self.assertTrue(os.path.exists(skill))
        res = _installer.register_swda_mcp("hermes")
        self.assertFalse(res["registered"])
        self.assertIn("contract + skill", res["reason"])

    def test_omp_uses_mcp_no_skill(self):
        import installer as _installer
        omp_dir = os.path.join(self.mock_home, ".omp", "agent")
        os.makedirs(omp_dir, exist_ok=True)
        with open(os.path.join(omp_dir, "APPEND_SYSTEM.md"), "w", encoding="utf-8") as f:
            f.write("# 1. 系統定位\nt\n")
        r = self._run("install", "--type", "omp", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("MCP: registered", r.stdout)
        self.assertIn("Skill: skipped", r.stdout)
        self.assertIn("contract + workflow", r.stdout)
        res = _installer.install_swda_skill("omp", omp_dir)
        self.assertFalse(res["installed"])


    def test_doctor_supported_matrix(self):
        import installer as _installer
        omp = _installer.verify_agent_doctor("omp")
        self.assertTrue(omp["supported"])
        for t in ("hermes", "openclaw", "pi"):
            d = _installer.verify_agent_doctor(t)
            self.assertFalse(d["supported"])
        base = os.path.join(REPO_ROOT, "swda-mcp", "agent-skill", "swda-skill")
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

class WorkflowPackTest(unittest.TestCase):
    """Locks the host workflow pack: which surfaces each host gets, marker-scoped
    removal, and idempotent reinstall.

    1. OMP gets skill + commands + task agents; Pi gets skill + prompts and no
       agents dir (Pi has no task-agent surface).
    2. Reinstalling identical content rewrites nothing and creates no backups.
    3. Uninstall removes only marker-carrying pack files - a user's own skill or
       command sharing the directory survives.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_home = os.path.join(self.test_dir, "mock_home")
        os.makedirs(self.mock_home)
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = self.mock_home
        self.env = dict(os.environ, SWDA_TEST_MODE="1")
        self.omp = os.path.join(self.mock_home, ".omp", "agent")
        self.pi = os.path.join(self.mock_home, ".pi", "agent")

    def tearDown(self):
        if self.original_home is not None:
            os.environ["HOME"] = self.original_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]
        shutil.rmtree(self.test_dir)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, env=self.env, cwd=REPO_ROOT,
        )

    def _seed_user_files(self):
        os.makedirs(os.path.join(self.omp, "skills", "mine"), exist_ok=True)
        with open(os.path.join(self.omp, "skills", "mine", "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("# user owned skill\n")
        os.makedirs(os.path.join(self.omp, "commands"), exist_ok=True)
        with open(os.path.join(self.omp, "commands", "mycmd.md"), "w", encoding="utf-8") as f:
            f.write("user owned command\n")

    def _install(self):
        r = self._run("install", "--type", "all", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        return r

    def test_omp_and_pi_get_host_appropriate_surfaces(self):
        self._install()

        # OMP: skill + commands + task agents.
        self.assertTrue(os.path.exists(os.path.join(self.omp, "skills", "swda", "SKILL.md")))
        for name in ("swda-intent", "swda-crucible", "swda-gate", "swda-status"):
            self.assertTrue(os.path.exists(os.path.join(self.omp, "commands", f"{name}.md")), name)
        for name in ("swda-alpha", "swda-beta", "swda-gamma",
                     "swda-builder", "swda-destroyer", "swda-referee"):
            self.assertTrue(os.path.exists(os.path.join(self.omp, "agents", f"{name}.md")), name)

        # Pi: skill + prompts, and no task-agent dir it cannot consume.
        self.assertTrue(os.path.exists(os.path.join(self.pi, "skills", "swda", "SKILL.md")))
        for name in ("swda-intent", "swda-crucible", "swda-gate", "swda-status"):
            self.assertTrue(os.path.exists(os.path.join(self.pi, "prompts", f"{name}.md")), name)
        self.assertFalse(os.path.exists(os.path.join(self.pi, "agents")))

        # The two pack variants must not be cross-installed.
        self.assertFalse(os.path.exists(os.path.join(self.omp, "prompts")))
        self.assertFalse(os.path.exists(os.path.join(self.pi, "commands")))

    def test_reinstall_is_idempotent_and_creates_no_backups(self):
        self._install()

        def digest():
            out = {}
            for base in (self.omp, self.pi):
                for cur, _dirs, files in os.walk(base):
                    for fn in files:
                        if fn.endswith(".bak") or ".db" in fn:
                            continue
                        path = os.path.join(cur, fn)
                        with open(path, "rb") as f:
                            out[os.path.relpath(path, self.mock_home)] = f.read()
            return out

        before = digest()
        self._install()
        after = digest()

        self.assertEqual(before, after)
        self.assertFalse([p for p in after if p.endswith(".bak")])

    def test_uninstall_removes_only_pack_files(self):
        self._seed_user_files()
        self._install()
        self.assertTrue(os.path.exists(os.path.join(self.omp, "skills", "swda", "SKILL.md")))

        r = self._run("install", "-u", "-y", "all")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])

        # Pack gone.
        self.assertFalse(os.path.exists(os.path.join(self.omp, "skills", "swda")))
        self.assertFalse(os.path.exists(os.path.join(self.omp, "agents")))
        self.assertFalse(os.path.exists(os.path.join(self.omp, "commands", "swda-gate.md")))
        self.assertFalse(os.path.exists(os.path.join(self.pi, "prompts", "swda-gate.md")))
        self.assertFalse(os.path.exists(os.path.join(self.pi, "skills", "swda")))

        # User's own files survive.
        self.assertTrue(os.path.exists(os.path.join(self.omp, "skills", "mine", "SKILL.md")))
        self.assertTrue(os.path.exists(os.path.join(self.omp, "commands", "mycmd.md")))

    def test_workflow_only_lands_for_hosts_with_the_surface(self):
        r = self._run("install", "--create", "wf_hermes", "--type", "hermes", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        hermes = os.path.join(self.mock_home, ".hermes", "profiles", "wf_hermes")
        self.assertTrue(os.path.exists(os.path.join(hermes, "skills", "swda", "SKILL.md")))
        self.assertFalse(os.path.exists(os.path.join(hermes, "commands")))
        self.assertFalse(os.path.exists(os.path.join(hermes, "agents")))

    def test_doctor_reports_workflow_presence(self):
        self._install()
        r = self._run("doctor")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("WORKFLOW: 1.0.0 (ok)", r.stdout)

        # Deleting one pack file must surface as a degraded status, not "ok".
        os.remove(os.path.join(self.omp, "commands", "swda-gate.md"))
        r = self._run("doctor")
        self.assertIn("partial", r.stdout)


class PiSubagentsTest(unittest.TestCase):
    """Locks the team-mandated Pi subagent runtime wiring.

    1. Without the plugin on disk, the Pi pack is skill + prompts only (5
       files) and no agents dir is created.
    2. With the plugin present (simulated by seeding the on-disk package dir
       plus the settings.json entry), the Pi-native agents land in agents/.
    3. The Pi-native agent files use Pi-compatible frontmatter: no OMP-only
       keys, and Pi guardrail keys present.
    4. check_pi_subagents reports all three states truthfully.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mock_home = os.path.join(self.test_dir, "mock_home")
        os.makedirs(self.mock_home)
        self.original_home = os.environ.get("HOME")
        os.environ["HOME"] = self.mock_home
        self.env = dict(os.environ, SWDA_TEST_MODE="1")
        self.pi = os.path.join(self.mock_home, ".pi", "agent")

    def tearDown(self):
        if self.original_home is not None:
            os.environ["HOME"] = self.original_home
        elif "HOME" in os.environ:
            del os.environ["HOME"]
        shutil.rmtree(self.test_dir)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            capture_output=True, text=True, env=self.env, cwd=REPO_ROOT,
        )

    def _seed_plugin(self):
        pkg = os.path.join(self.pi, "git", "github.com", "HazAT", "pi-interactive-subagents")
        os.makedirs(pkg, exist_ok=True)
        with open(os.path.join(pkg, "package.json"), "w", encoding="utf-8") as f:
            f.write('{"name": "pi-interactive-subagents"}')
        with open(os.path.join(self.pi, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"packages": ["git:github.com/HazAT/pi-interactive-subagents"]}, f)

    def test_check_reports_absent_without_plugin(self):
        import installer as _installer
        state = _installer.check_pi_subagents()
        self.assertFalse(state["registered"])
        self.assertFalse(state["present"])
        self.assertIsNone(state["source"])

    def test_check_reports_present_with_seeded_plugin(self):
        import installer as _installer
        self._seed_plugin()
        state = _installer.check_pi_subagents()
        self.assertTrue(state["registered"])
        self.assertTrue(state["present"])
        self.assertIn("pi-interactive-subagents", state["source"])

    def test_pi_pack_without_plugin_has_no_agents(self):
        import installer as _installer
        base, layout = _installer._workflow_dest("pi", self.pi)
        pairs = list(_installer._workflow_pairs(base, layout))
        self.assertEqual(len(pairs), 5)
        self.assertFalse(any("/agents/" in d for _, d in pairs))

    def test_pi_pack_with_plugin_gains_native_agents(self):
        import installer as _installer
        self._seed_plugin()
        res = _installer.install_swda_workflow("pi", self.pi)
        self.assertTrue(res["installed"])
        self.assertEqual(len(res["files"]), 11)
        for name in ("swda-alpha", "swda-beta", "swda-gamma",
                     "swda-builder", "swda-destroyer", "swda-referee"):
            path = os.path.join(self.pi, "agents", f"{name}.md")
            self.assertTrue(os.path.exists(path), name)
            with open(path, encoding="utf-8") as f:
                head = f.read(2048)
            # Pi-compatible: native tools only, Pi guardrail keys present.
            self.assertIn("spawning: false", head)
            self.assertIn("auto-exit: true", head)
            # OMP-only keys must not leak into the Pi variant.
            self.assertNotIn("read-summarize", head)
            self.assertNotIn("glob", head.split("---")[1])
            self.assertNotIn("web_search", head)
            self.assertIn("<!-- swda-workflow:v1 -->", head)

    def test_uninstall_removes_pi_agents_but_keeps_user_files(self):
        import installer as _installer
        self._seed_plugin()
        _installer.install_swda_workflow("pi", self.pi)
        mine = os.path.join(self.pi, "agents", "mymine.md")
        with open(mine, "w", encoding="utf-8") as f:
            f.write("# user owned agent\n")
        out = _installer.uninstall_swda_workflow("pi", self.pi)
        self.assertFalse(os.path.exists(os.path.join(self.pi, "agents", "swda-alpha.md")))
        self.assertTrue(os.path.exists(mine))
        removed_names = [os.path.basename(p) for p in out["removed"]]
        self.assertIn("swda-alpha.md", removed_names)
        self.assertNotIn("mymine.md", removed_names)

    def test_pi_skill_and_gate_use_cli_not_mcp(self):
        import installer as _installer
        self._seed_plugin()
        res = _installer.install_swda_workflow("pi", self.pi)
        self.assertTrue(res["installed"])
        with open(os.path.join(self.pi, "skills", "swda", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        self.assertIn("swda reconcile", skill)
        self.assertNotIn("swda_reconcile(file", skill)
        with open(os.path.join(self.pi, "prompts", "swda-gate.md"), encoding="utf-8") as f:
            gate = f.read()
        self.assertIn("swda reconcile", gate)
        self.assertIn("exit\n   code as authoritative", gate)
        with open(os.path.join(self.pi, "prompts", "swda-status.md"), encoding="utf-8") as f:
            status = f.read()
        self.assertIn("swda stats", status)
        self.assertIn("no MCP client", status)
        # OMP keeps the MCP-driven originals.
        omp_base, omp_layout = _installer._workflow_dest("omp", os.path.join(self.mock_home, ".omp", "agent"))
        omp_src = {os.path.basename(d): s for s, d in _installer._workflow_pairs(omp_base, omp_layout)}
        with open(omp_src["swda-gate.md"], encoding="utf-8") as f:
            self.assertIn("swda_reconcile", f.read())

    def test_pi_writes_no_mcp_entry(self):
        import installer as _installer
        res = _installer.register_swda_mcp("pi")
        self.assertFalse(res["registered"])
        self.assertIn("no MCP client", res["reason"])
        self.assertFalse(os.path.exists(os.path.join(self.pi, "mcp.json")))

    def test_stale_pi_mcp_entry_removed_on_install(self):
        import installer as _installer
        import json as _json
        os.makedirs(self.pi, exist_ok=True)
        stale = os.path.join(self.pi, "mcp.json")
        with open(stale, "w", encoding="utf-8") as f:
            _json.dump({"mcpServers": {"swda-mcp": {
                "command": "/nonexistent/python",
                "args": ["-m", "swda_mcp.server"],
                "cwd": "/x", "env": {}}}}, f)
        with open(os.path.join(self.pi, "APPEND_SYSTEM.md"), "w", encoding="utf-8") as f:
            f.write("# 1. 系統定位\nt\n")
        r = self._run("install", "--type", "pi", "-y")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertIn("removed stale Pi swda-mcp entry", r.stdout)
        self.assertFalse(os.path.exists(stale))

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
