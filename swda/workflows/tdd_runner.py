"""
SWDA TDD Runner: Automated Red-Green-Refactor Engine.
Enforces the TDD contract: tests must fail before code implementation,
and minimal code must be written to achieve green status without touching tests.
"""

import subprocess
import os
from typing import Dict, Any, Optional, TYPE_CHECKING

from swda.core.firewall import SafetyFirewall

if TYPE_CHECKING:
    from swda.core.hooks import HookRegistry

_default_hooks: Optional["HookRegistry"] = None


def set_default_hooks(hooks: Optional["HookRegistry"]) -> None:
    """Installs a process-wide hook registry for TDD runs (None to clear)."""
    global _default_hooks
    _default_hooks = hooks

class TestRunResult:
    def __init__(self, returncode: int, stdout: str, stderr: str, passed: bool):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.passed = passed


class TDDRunner:
    """
    Executes automated test runs and validates Red/Green state transitions.
    """

    @staticmethod
    def run_tests(test_command: str, cwd: Optional[str] = None, timeout: int = 60,
                   sandbox_dir: Optional[str] = None,
                   hooks: Optional["HookRegistry"] = None) -> TestRunResult:
        """Runs a test command in the specified workspace directory.

        Firewall-audited before execution; confined to ``sandbox_dir`` when
        given (commands escaping via ``..`` are rejected); Pre/PostToolUse
        hooks observed around the run.
        """
        from swda.core.hooks import HookBlocked
        active = hooks if hooks is not None else _default_hooks
        run_cwd = cwd or sandbox_dir or os.getcwd()
        if sandbox_dir:
            wanted = os.path.abspath(run_cwd)
            root = os.path.abspath(sandbox_dir)
            if wanted != root and not wanted.startswith(root + os.sep):
                return TestRunResult(returncode=126, stdout="",
                                     stderr=f"Sandbox escape rejected: {run_cwd} outside {sandbox_dir}",
                                     passed=False)
        try:
            SafetyFirewall.audit_command(test_command)
        except Exception as e:
            return TestRunResult(returncode=126, stdout="", stderr=f"Firewall blocked: {e}", passed=False)
        if active is not None:
            try:
                active.run_pre("tdd.run_tests", {"command": test_command, "cwd": run_cwd})
            except HookBlocked as blocked:
                return TestRunResult(returncode=126, stdout="", stderr=str(blocked), passed=False)
        try:
            res = subprocess.run(
                test_command,
                shell=True,
                cwd=run_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = TestRunResult(
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                passed=res.returncode == 0,
            )
        except subprocess.TimeoutExpired as e:
            out = TestRunResult(
                returncode=124,
                stdout="",
                stderr=f"Test timed out after {timeout} seconds: {e}",
                passed=False,
            )
        if active is not None:
            active.run_post("tdd.run_tests", {"command": test_command, "cwd": run_cwd},
                            {"returncode": out.returncode, "passed": out.passed})
        return out

    @classmethod
    def verify_red_state(cls, test_command: str, cwd: Optional[str] = None) -> bool:
        """Verifies that the newly authored test fails initially (Red State)."""
        result = cls.run_tests(test_command, cwd=cwd)
        # In TDD, the test MUST fail initially
        return not result.passed

    @classmethod
    def verify_green_state(cls, test_command: str, cwd: Optional[str] = None) -> bool:
        """Verifies that the test suite passes after minimal code implementation (Green State)."""
        result = cls.run_tests(test_command, cwd=cwd)
        return result.passed
