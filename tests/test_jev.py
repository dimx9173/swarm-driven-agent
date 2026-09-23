#!/usr/bin/env python3
"""Tests for the optional TypeSafe Jev guard (swda/prime/jev.py) and its
crucible arbitration. No real network calls: urlopen / judge are mocked."""
import json
import http.client
import os
import sys
import unittest
import urllib.error
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from swda.prime.jev import (
    JevAnswer,
    check,
    intent_hint,
    is_enabled,
    jev_pre_tool_hook,
    judge,
    pick,
    rate,
)
from swda.workflows.crucible import CrucibleWorkflow, _arbitrate_verdict

_JEV_KEYS = ("JEV_API_KEY", "TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "AI_GATEWAY_API_KEY")


@contextmanager
def jev_env(**overrides):
    """Set Jev keys (+ overrides); every other Jev env var is cleared."""
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


def http_response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


class TestJevDisabled(unittest.TestCase):
    def test_is_enabled_returns_false_when_no_env(self):
        with jev_env():
            self.assertFalse(is_enabled())

    def test_judge_returns_empty_when_disabled(self):
        with jev_env(), patch("swda.prime.jev.urllib.request.urlopen") as mock_urlopen:
            self.assertEqual(judge({}, {"q": check("ok?")}), {})
            mock_urlopen.assert_not_called()

    def test_hook_returns_none_when_disabled(self):
        with jev_env():
            self.assertIsNone(jev_pre_tool_hook({"tool": "repl.execute", "args": {}}))


class TestJevMockBackend(unittest.TestCase):
    def setUp(self):
        self.env = jev_env(TYPESAFE_API_KEY="test-key")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_single_request_for_multiple_questions(self, mock_urlopen):
        mock_urlopen.return_value = http_response({"answers": [
            {"id": "next", "answer": "merge", "confidence": 0.93},
            {"id": "risk", "answer": "routine", "confidence": 0.8},
            {"id": "passed", "answer": 0.9},
        ]})
        answers = judge(
            {"tool": "t"},
            {
                "next": pick("Next action?", {"merge": "m", "hold": "h"}),
                "risk": rate("How risky?", ["routine", "incident"]),
                "passed": check("Did the run succeed?"),
            },
        )
        self.assertEqual(mock_urlopen.call_count, 1)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(len(payload["questions"]), 3)
        self.assertEqual(req.full_url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(req.headers["Authorization"], "Bearer test-key")
        self.assertEqual(set(answers), {"next", "risk", "passed"})

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_parse_choice_answer(self, mock_urlopen):
        mock_urlopen.return_value = http_response(
            {"answers": [{"id": "gate", "answer": "deny", "confidence": 0.87}]}
        )
        answers = judge({}, {"gate": pick("Run?", {"allow": "a", "deny": "d"})})
        gate = answers["gate"]
        self.assertEqual(gate.answer, "deny")
        self.assertEqual(gate.confidence, 0.87)
        self.assertEqual(gate.confidence_from, "reported")
        self.assertFalse(gate.escalate)

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_parse_score_answer(self, mock_urlopen):
        mock_urlopen.return_value = http_response(
            {"answers": [{"id": "risk", "answer": "incident", "distribution": {"routine": 0.1, "incident": 0.6}}]}
        )
        risk = judge({}, {"risk": rate("How risky?", ["routine", "incident"])})["risk"]
        self.assertEqual(risk.answer, "incident")
        self.assertEqual(risk.confidence, 0.6)
        self.assertEqual(risk.confidence_from, "estimated")

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_parse_noul_answer(self, mock_urlopen):
        mock_urlopen.return_value = http_response({"answers": [{"id": "passed", "answer": 0.9}]})
        passed = judge({}, {"passed": check("Did it pass?")})["passed"]
        self.assertEqual(passed.answer, "0.9")
        self.assertAlmostEqual(passed.confidence, 0.8)
        self.assertEqual(passed.confidence_from, "estimated")

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_low_confidence_and_unsure_escalate(self, mock_urlopen):
        mock_urlopen.return_value = http_response({"answers": [
            {"id": "a", "answer": "allow", "confidence": 0.2},
            {"id": "b", "answer": "unsure", "confidence": 0.9},
        ]})
        answers = judge({}, {"a": check("x?"), "b": pick("y?", {"unsure": "u", "implement": "i"})})
        self.assertTrue(answers["a"].escalate)
        self.assertTrue(answers["b"].escalate)

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_shape_mismatch_returns_empty(self, mock_urlopen):
        mock_urlopen.return_value = http_response({"unexpected": "payload"})
        self.assertEqual(judge({}, {"q": check("ok?")}), {})

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_http_exception_returns_empty_dict(self, mock_urlopen):
        mock_urlopen.side_effect = http.client.BadStatusLine("x")
        self.assertEqual(judge({"tool": "test"}, {"q": check("ok?")}), {})


class TestJevTimeoutDegrade(unittest.TestCase):
    def setUp(self):
        self.env = jev_env(TYPESAFE_API_KEY="test-key")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_timeout_returns_empty_dict(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError()
        self.assertEqual(judge({"tool": "test"}, {"q": check("ok?")}), {})

    @patch("swda.prime.jev.urllib.request.urlopen")
    def test_network_error_returns_empty_dict(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        self.assertEqual(judge({"tool": "test"}, {"q": check("ok?")}), {})

    def test_hook_continues_when_jev_unreachable(self):
        with patch("swda.prime.jev.judge", return_value={}):
            self.assertIsNone(jev_pre_tool_hook({"tool": "repl.execute", "args": {}}))

    def test_hook_never_raises(self):
        with patch("swda.prime.jev.judge", side_effect=RuntimeError("boom")):
            self.assertIsNone(jev_pre_tool_hook({"tool": "bash", "args": {}}))
    def test_tdd_run_tests_tool_is_gatable(self):
        with patch("swda.prime.jev.judge") as mock_judge:
            mock_judge.return_value = {"gate": JevAnswer("deny", 0.9, "reported", False)}
            result = jev_pre_tool_hook({"tool": "tdd.run_tests", "args": {}})
            self.assertIsNotNone(result)
            self.assertEqual(result["decision"], "block")



class TestJevCustomEndpoint(unittest.TestCase):
    """Base URL, model, and path are all overridable; JEV_API_KEY is a fully
    custom endpoint."""

    def _request(self, **env):
        with jev_env(**env), patch("swda.prime.jev.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = http_response({"answers": []})
            judge({}, {"q": check("ok?")})
        return mock_urlopen.call_args[0][0]

    def test_global_base_url_and_model_override(self):
        req = self._request(
            TYPESAFE_API_KEY="k",
            JEV_BASE_URL="https://proxy.internal/jev",
            JEV_MODEL="custom-model",
        )
        self.assertEqual(req.full_url, "https://proxy.internal/jev/v1/systemone")
        self.assertEqual(json.loads(req.data)["model"], "custom-model")

    def test_per_provider_base_url_and_model_override(self):
        req = self._request(
            AI_GATEWAY_API_KEY="k",
            AI_GATEWAY_BASE_URL="https://gw.internal/v1/",
            AI_GATEWAY_MODEL="gw-model",
        )
        self.assertEqual(req.full_url, "https://gw.internal/v1/v4/ai/evaluation-model")
        self.assertEqual(json.loads(req.data)["model"], "gw-model")

    def test_custom_judge_path_override(self):
        req = self._request(TYPESAFE_API_KEY="k", JEV_JUDGE_PATH="/decide")
        self.assertEqual(req.full_url, "https://api.typesafe.ai/decide")

    def test_jev_api_key_enables_custom_endpoint(self):
        req = self._request(
            JEV_API_KEY="custom-key",
            JEV_BASE_URL="https://my-jev.example.com",
            JEV_MODEL="my-model",
        )
        self.assertEqual(req.full_url, "https://my-jev.example.com/v1/judge")
        self.assertEqual(req.headers["Authorization"], "Bearer custom-key")
        self.assertEqual(json.loads(req.data)["model"], "my-model")


class TestJevHookInvariant(unittest.TestCase):
    def setUp(self):
        self.env = jev_env(TYPESAFE_API_KEY="test-key")
        self.env.__enter__()

    def tearDown(self):
        self.env.__exit__(None, None, None)

    def test_hook_never_returns_allow(self):
        for answer in ("allow", "deny", "ask", "unsure", "weird"):
            with patch("swda.prime.jev.judge",
                       return_value={"gate": JevAnswer(answer, 0.9, "reported", False)}):
                result = jev_pre_tool_hook({"tool": "repl.execute", "args": {"code": "x"}})
            self.assertTrue(result is None or result.get("decision") == "block")

    def test_hook_returns_none_for_non_gatable_tools(self):
        with patch("swda.prime.jev.judge") as mock_judge:
            self.assertIsNone(jev_pre_tool_hook({"tool": "read_file", "args": {}}))
            self.assertIsNone(jev_pre_tool_hook({"tool": "read_file", "args": {}}))
            mock_judge.assert_not_called()

    @patch("swda.prime.jev.judge")
    def test_hook_returns_block_for_deny_answer(self, mock_judge):
        mock_judge.return_value = {"gate": MagicMock(answer="deny", confidence=0.9)}
        result = jev_pre_tool_hook({"tool": "repl.execute", "args": {}})
        self.assertIsNotNone(result)
        self.assertEqual(result.get("decision"), "block")

    @patch("swda.prime.jev.judge")
    def test_hook_returns_block_for_ask_answer(self, mock_judge):
        mock_judge.return_value = {"gate": MagicMock(answer="ask", confidence=0.6)}
        result = jev_pre_tool_hook({"tool": "repl.execute", "args": {}})
        self.assertIsNotNone(result)
        self.assertEqual(result.get("decision"), "block")

    def test_gatable_tool_names_hit_gate(self):
        for tool in ("bash", "shell", "execute", "repl.execute"):
            with patch("swda.prime.jev.judge", return_value={}) as mock_judge:
                jev_pre_tool_hook({"tool": tool, "args": {}})
                mock_judge.assert_called_once()


class TestJevRefereeArbitration(unittest.TestCase):
    def _answer(self, value):
        return {"pass": JevAnswer(value, 0.9, "reported", False)}

    def test_empty_jev_result_keeps_verdict(self):
        verdict = {"passed": True, "score": 8, "reason": "ok", "round": 1}
        self.assertIs(_arbitrate_verdict(verdict, None), verdict)
        self.assertIs(_arbitrate_verdict(verdict, {}), verdict)

    def test_agree_keep_llm_verdict(self):
        verdict = {"passed": True, "score": 8, "reason": "ok", "round": 1}
        result = _arbitrate_verdict(verdict, self._answer("pass"))
        self.assertTrue(result["passed"])
        self.assertEqual(result["reason"], "ok")

    def test_disagree_fail_closed_llm_re_review(self):
        verdict = {"passed": True, "score": 8, "reason": "ok", "round": 1}
        result = _arbitrate_verdict(verdict, self._answer("fail"))
        self.assertFalse(result["passed"])
        self.assertIn("Jev disagreed", result.get("reason", ""))
        self.assertEqual(verdict["passed"], True)  # original not mutated

    def test_llm_failed_stays_failed(self):
        verdict = {"passed": False, "score": 2, "reason": "weak", "round": 1}
        result = _arbitrate_verdict(verdict, self._answer("pass"))
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "weak")

    def test_noul_float_answer_parsed(self):
        verdict = {"passed": True, "score": 8, "reason": "ok", "round": 1}
        self.assertFalse(_arbitrate_verdict(verdict, self._answer("0.1"))["passed"])
        self.assertTrue(_arbitrate_verdict(verdict, self._answer("0.8"))["passed"])

    @patch("swda.prime.jev.is_enabled", return_value=True)
    @patch("swda.prime.jev.judge")
    def test_failed_verdict_skips_jev_call(self, mock_judge, _enabled):
        """LLM already failed the verdict -> no Jev round-trip at all (the
        arbitration result would be discarded anyway)."""
        from swda.core.blackboard import Blackboard
        from swda.prime.rlm import RLMDispatcher

        def mock_llm(role, prompt):
            if role == "referee":
                return {"passed": False, "score": 2, "reason": "weak"}
            return {"content": "p"}

        crucible = CrucibleWorkflow(rlm=RLMDispatcher(mock_handler=mock_llm),
                                    blackboard=Blackboard(), max_rounds=1)
        with self.assertRaises(Exception):
            crucible.run_crucible("t")
        mock_judge.assert_not_called()

    @patch("swda.prime.jev.is_enabled", return_value=True)
    @patch("swda.prime.jev.judge", return_value={"pass": JevAnswer("fail", 0.9, "reported", False)})
    def test_run_crucible_arbitrates_when_enabled(self, _judge, _enabled):
        from swda.core.blackboard import Blackboard
        from swda.core.circuit_breaker import CircuitBreakerException
        from swda.prime.rlm import RLMDispatcher

        def mock_llm(role, prompt):
            if role == "referee":
                return {"passed": True, "score": 9, "reason": "ok"}
            return {"content": "p"}

        crucible = CrucibleWorkflow(rlm=RLMDispatcher(mock_handler=mock_llm),
                                    blackboard=Blackboard(), max_rounds=1)
        with self.assertRaises(CircuitBreakerException):
            crucible.run_crucible("t")

    def test_run_crucible_unchanged_when_disabled(self):
        # No env keys -> is_enabled() False -> arbitration skipped entirely.
        # urlopen is also patched so a stray .env key could never hit network here.
        with jev_env(), patch("swda.prime.jev.urllib.request.urlopen") as mock_urlopen:
            from swda.core.blackboard import Blackboard
            from swda.prime.rlm import RLMDispatcher

            def mock_llm(role, prompt):
                if role == "referee":
                    return {"passed": True, "score": 9, "reason": "ok"}
                return {"content": "p"}

            bb = Blackboard()
            crucible = CrucibleWorkflow(rlm=RLMDispatcher(mock_handler=mock_llm),
                                        blackboard=bb, max_rounds=1)
            res = crucible.run_crucible("t")
            self.assertTrue(res.passed)
            mock_urlopen.assert_not_called()


class TestJevIntentHint(unittest.TestCase):
    def test_returns_none_when_disabled(self):
        with jev_env(), patch("swda.prime.jev.urllib.request.urlopen") as mock_urlopen:
            self.assertIsNone(intent_hint("do the thing"))
            mock_urlopen.assert_not_called()

    def test_classification_returned_on_high_confidence(self):
        with patch("swda.prime.jev.judge",
                   return_value={"intent": JevAnswer("implement", 0.9, "reported", False)}):
            self.assertEqual(intent_hint("add a feature"), "implement")

    def test_unsure_on_low_confidence_or_unsure_answer(self):
        with patch("swda.prime.jev.judge",
                   return_value={"intent": JevAnswer("implement", 0.2, "estimated", True)}):
            self.assertEqual(intent_hint("maybe"), "unsure")
        with patch("swda.prime.jev.judge",
                   return_value={"intent": JevAnswer("unsure", 0.9, "reported", True)}):
            self.assertEqual(intent_hint("hmm"), "unsure")

    def test_none_when_jev_unreachable(self):
        with patch("swda.prime.jev.judge", return_value={}):
            self.assertIsNone(intent_hint("anything"))

    def test_unknown_answer_maps_to_unsure(self):
        """Server returns a string outside _INTENT_OPTIONS -> treat as unsure,
        not as a classification (arbitrary-string guard)."""
        with patch("swda.prime.jev.judge",
                   return_value={"intent": JevAnswer("rm-rf-the-repo", 0.99, "reported", False)}):
            self.assertEqual(intent_hint("add a feature"), "unsure")


class TestJevCLIGate(unittest.TestCase):
    """--jev-gate flag wires the PreToolUse guard through the real CLI path."""

    def _capture_repl_hooks(self, argv):
        """Run swda.cli.main() for a repl invocation; return the hooks kwarg
        PrimeREPL actually received (REPL loop stubbed via EOFError)."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        import swda.cli
        with patch.object(sys, "argv", argv), \
                patch("builtins.input", side_effect=EOFError), \
                patch.object(swda.cli, "PrimeREPL") as mock_repl, \
                redirect_stdout(io.StringIO()):
            swda.cli.main()
        self.assertEqual(mock_repl.call_count, 1)
        return mock_repl.call_args.kwargs.get("hooks")

    def test_repl_without_jev_gate_passes_no_hooks(self):
        self.assertIsNone(self._capture_repl_hooks(["swda", "repl"]))

    def test_repl_with_jev_gate_passes_registry_with_one_pretooluse_hook(self):
        from swda.core.hooks import PRE_TOOL_USE, HookRegistry
        with jev_env(TYPESAFE_API_KEY="test-key"):
            hooks = self._capture_repl_hooks(["swda", "repl", "--jev-gate"])
        self.assertIsInstance(hooks, HookRegistry)
        self.assertEqual(len(hooks._hooks[PRE_TOOL_USE]), 1)

    def _run_main(self, argv):
        """Run swda.cli.main() for a run invocation with the lifecycle mocked
        out; only the set_default_hooks call is under test."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import MagicMock, patch

        import swda.cli
        with patch.object(sys, "argv", argv), \
                patch.object(swda.cli, "TelemetryLogger", MagicMock()), \
                patch.object(swda.cli, "FSMEngine", MagicMock()), \
                patch.object(swda.cli, "RLMDispatcher", MagicMock()), \
                patch.object(swda.cli, "CrucibleWorkflow", MagicMock()), \
                patch("swda.workflows.tdd_runner.set_default_hooks") as mock_set, \
                redirect_stdout(io.StringIO()):
            swda.cli.main()
        return mock_set

    def test_run_with_jev_gate_calls_set_default_hooks_with_registry(self):
        from swda.core.hooks import PRE_TOOL_USE, HookRegistry
        with jev_env(TYPESAFE_API_KEY="test-key"):
            mock_set = self._run_main(["swda", "run", "some task", "--jev-gate"])
        mock_set.assert_called_once()
        registry = mock_set.call_args.args[0]
        self.assertIsInstance(registry, HookRegistry)
        self.assertEqual(len(registry._hooks[PRE_TOOL_USE]), 1)

    def test_run_without_jev_gate_clears_tdd_hooks(self):
        """No flag -> set_default_hooks(None): the process-wide registry is
        cleared so a previous gated run cannot leak into this one."""
        mock_set = self._run_main(["swda", "run", "some task"])
        mock_set.assert_called_once()
        self.assertIsNone(mock_set.call_args.args[0])

    def test_denied_gate_blocks_run_pre(self):
        """Registry built the same way the CLI builds it raises HookBlocked on deny."""
        from unittest.mock import patch

        import swda.cli
        from swda.core.hooks import HookBlocked
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"gate": JevAnswer("deny", 0.9, "reported", False)}):
            registry = swda.cli._jev_gate_registry(True)
            with self.assertRaises(HookBlocked):
                registry.run_pre("bash", {"command": "rm -rf /"})


class TestJevCLIIntent(unittest.TestCase):
    """`swda jev-intent` prints the hint, 'unsure', or 'none'; never raises."""

    def _jev_intent_stdout(self, request):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        import swda.cli
        buf = io.StringIO()
        with patch.object(sys, "argv", ["swda", "jev-intent", request]), \
                redirect_stdout(buf):
            self.assertIsNone(swda.cli.main())  # exit code 0: no SystemExit
        out = buf.getvalue()
        return out.strip().rsplit("\n", 1)[-1].strip()

    def test_high_confidence_prints_classification(self):
        from unittest.mock import patch
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"intent": JevAnswer("implement", 0.9, "reported", False)}):
            self.assertEqual(self._jev_intent_stdout("add a feature"), "implement")

    def test_unsure_prints_unsure(self):
        from unittest.mock import patch
        with jev_env(TYPESAFE_API_KEY="test-key"), \
                patch("swda.prime.jev.judge",
                      return_value={"intent": JevAnswer("unsure", 0.9, "reported", True)}):
            self.assertEqual(self._jev_intent_stdout("hmm"), "unsure")

    def test_no_jev_key_prints_none(self):
        with jev_env():
            self.assertEqual(self._jev_intent_stdout("add a feature"), "none")

    def test_intent_banner_reports_jev_state(self):
        """jev-intent prints the Jev banner so users see which path runs."""
        import io
        from contextlib import redirect_stdout

        import swda.cli
        buf = io.StringIO()
        with jev_env(), patch.object(sys, "argv", ["swda", "jev-intent", "x"]), \
                redirect_stdout(buf):
            swda.cli.main()
        self.assertIn("Jev: OFF (default agent judgment)", buf.getvalue())

    def test_run_banner_reports_jev_state(self):
        """swda run prints the banner (off without key) before the lifecycle."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch

        import swda.cli
        buf = io.StringIO()
        with jev_env(), patch.object(sys, "argv", ["swda", "run", "t"]), \
                patch("swda.workflows.tdd_runner.set_default_hooks"), \
                patch("swda.cli.CrucibleWorkflow") as mock_crucible, \
                redirect_stdout(buf):
            mock_crucible.return_value.run_crucible.side_effect = SystemExit(3)
            with self.assertRaises(SystemExit):
                swda.cli.main()
        self.assertIn("Jev: OFF (default agent judgment)", buf.getvalue())


class TestJevVerdictParsing(unittest.TestCase):
    def test_parse_verdict_keeps_exact_behavior_without_jev_fields(self):
        verdict = CrucibleWorkflow._parse_verdict({"passed": True, "score": 9, "reason": "ok"}, 2)
        self.assertEqual(verdict["passed"], True)
        self.assertEqual(verdict["score"], 9)
        self.assertEqual(verdict["reason"], "ok")
        self.assertEqual(verdict["round"], 2)
        self.assertIsNone(verdict["jev_score"])
        self.assertIsNone(verdict["jev_confidence"])

    def test_parse_verdict_never_trusts_llm_supplied_jev_fields(self):
        """Referee output cannot fabricate Jev attestation (spoof guard):
        _parse_verdict always defaults the fields; only _arbitrate_verdict
        sets them from a real Jev answer."""
        for src in ({"passed": True, "score": 9, "reason": "ok",
                     "jev_score": 0.82, "jev_confidence": 0.91},  # dict spoof
                    '{"passed": true, "score": 9, "reason": "ok", "jev_score": 0.82}'):  # json spoof
            verdict = CrucibleWorkflow._parse_verdict(src, 1)
            self.assertIsNone(verdict["jev_score"])
            self.assertIsNone(verdict["jev_confidence"])

    def test_parse_verdict_garbage_fails_closed(self):
        verdict = CrucibleWorkflow._parse_verdict("prose, no json", 3)
        self.assertFalse(verdict["passed"])
        self.assertIsNone(verdict["jev_score"])


if __name__ == "__main__":
    unittest.main()
