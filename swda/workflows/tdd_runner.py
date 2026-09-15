"""
SWDA TDD Runner: Automated Red-Green-Refactor Engine.
Enforces the TDD contract: tests must fail before code implementation,
and minimal code must be written to achieve green status without touching tests.
"""

import subprocess
import os
from typing import Dict, Any, Optional


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
    def run_tests(test_command: str, cwd: Optional[str] = None, timeout: int = 60) -> TestRunResult:
        """Runs a test command in the specified workspace directory."""
        try:
            res = subprocess.run(
                test_command,
                shell=True,
                cwd=cwd or os.getcwd(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return TestRunResult(
                returncode=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                passed=res.returncode == 0,
            )
        except subprocess.TimeoutExpired as e:
            return TestRunResult(
                returncode=124,
                stdout="",
                stderr=f"Test timed out after {timeout} seconds: {e}",
                passed=False,
            )

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
