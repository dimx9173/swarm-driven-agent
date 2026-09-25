#!/usr/bin/env python3
"""Tests for the swda_judge MCP tool (swda-mcp bridge over swda/prime/jev.py).

Standalone unittest (no pytest). Exercises the plain tool function from
swda_mcp.server with swda.prime.jev.judge patched — no MCP transport and no
network.

Import choice (checked against the installed FastMCP before writing these
tests): ``@mcp.tool()`` in this SDK version returns the original function
object unchanged — the decorated name in ``swda_mcp.server`` IS the plain
callable (``type(...) is function``, there is no ``.fn`` wrapper attribute,
signature preserved). So ``from swda_mcp.server import swda_judge`` imports
the callable directly; no ``.fn`` indirection is needed. The mcp SDK itself
is imported at module level by server.py, so it must be importable (it is in
the project venv); what these tests do NOT need is a running MCP transport.
"""
import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch

_REPO = os.environ.get("SWDA_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
# Make `import swda_mcp` work regardless of the invoking cwd (covers running
# from the repo root; `cd swda-mcp && python -m unittest ...` covers itself).
_SWDA_MCP = os.path.join(_REPO, "swda-mcp")
if _SWDA_MCP not in sys.path:
    sys.path.insert(0, _SWDA_MCP)

from swda.prime.jev import JevAnswer  # noqa: E402
from swda_mcp.server import swda_judge  # noqa: E402

_JEV_KEYS = ("JEV_API_KEY", "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "AI_GATEWAY_API_KEY")


@contextmanager
def jev_env(**overrides):
    """Set Jev keys (+ overrides); every other Jev env var is cleared.
    (Copied from tests/test_jev.py.)"""
    unset = [k for k in _JEV_KEYS if k not in overrides]
    unset += [
        v for v in (
            "JEV_BASE_URL", "JEV_MODEL", "JEV_JUDGE_PATH", "JEV_CONFIDENCE_THRESHOLD",
            "TYPESAFE_BASE_URL", "TYPESAFE_MODEL",
            "OPENROUTER_BASE_URL", "OPENROUTER_MODEL",
            "AI_GATEWAY_BASE_URL", "AI_GATEWAY_MODEL",
        ) if v not in overrides
    ]
    saved = {k: os.environ[k] for k in list(unset) + list(overrides) if k in os.environ}
    for k in unset:
        os.environ.pop(k, None)
    for k, v in overrides.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k in list(unset) + list(overrides):
            os.environ.pop(k, None)
        for k, v in saved.items():
            os.environ[k] = v


class TestSwdaJudge(unittest.TestCase):
    def test_judge_disabled_degrades_unverifiable(self):
        with jev_env():
            res = swda_judge({"evidence": "x"},
                             {"pass": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertEqual(res["action"], "abstain")
        self.assertEqual(res["answers"], {})
        self.assertIn("no Jev API key", res["error"] or "")

    def test_judge_success_auto(self):
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"pass": JevAnswer("yes", 0.9, "reported", False)}):
            res = swda_judge({"evidence": "x"},
                             {"pass": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "valid")
        self.assertEqual(res["action"], "auto")
        self.assertEqual(res["confidence"], 0.9)
        self.assertEqual(res["answers"]["pass"]["action"], "support")
        self.assertEqual(res["answers"]["pass"]["reason"], "choice_yes")
        self.assertIsNone(res["error"])

    def test_judge_contest_escalates_invalid(self):
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"pass": JevAnswer("0.1", 0.9, "reported", False)}):
            res = swda_judge({"evidence": "x"},
                             {"pass": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "invalid")
        self.assertEqual(res["action"], "escalate")
        self.assertEqual(res["answers"]["pass"]["action"], "contest")

    def test_judge_abstain_answer_unverifiable(self):
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"pass": JevAnswer("banana", 0.9, "reported", False)}):
            res = swda_judge({"evidence": "x"},
                             {"pass": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertEqual(res["action"], "abstain")
        self.assertEqual(res["answers"]["pass"]["reason"], "malformed_answer")

    def test_judge_degraded_judge_unverifiable_with_error(self):
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge", return_value={}), \
                patch("swda.prime.jev.last_error", return_value="degrade reason text"):
            res = swda_judge({"evidence": "x"},
                             {"pass": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertEqual(res["action"], "abstain")
        self.assertEqual(res["answers"], {})
        self.assertEqual(res["error"], "degrade reason text")

    def test_judge_never_raises_on_garbage_arguments(self):
        with jev_env(TYPESAFE_API_KEY="test-key"):
            res = swda_judge(state=None, questions=None,
                             question_specs={"q": "not-a-dict"})
        self.assertIsInstance(res, dict)
        self.assertIn(res["verdict"], ("invalid", "unverifiable"))  # fail-closed set
        self.assertIn(res["action"], ("escalate", "abstain"))
        self.assertTrue(res["error"])

    def test_noul_spec_building_from_questions(self):
        captured = {}

        def fake_judge(state, specs):
            captured["state"] = state
            captured["specs"] = specs
            return {"q": JevAnswer("0.9", 0.8, "estimated", False)}

        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge", side_effect=fake_judge):
            res = swda_judge({"evidence": "x"},
                             {"q": "Does the evidence support this?"})
        self.assertEqual(res["verdict"], "valid")
        spec = captured["specs"]["q"]
        self.assertEqual(spec["type"], "noul")
        self.assertIn("Does the evidence support this?", spec["instructions"])

    def test_tool_name_registered_in_harness_scanner(self):
        from swda.workflows.harness_walk import SWDA_TOOL_NAMES
        self.assertIn("swda_judge", SWDA_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
