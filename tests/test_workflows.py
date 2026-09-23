"""
Unit tests for SWDA Workflows, Prime REPL, and Continual Harness.
"""

import unittest
import json
import os
import tempfile
import shutil
from swda.core.blackboard import Blackboard, AgentRole
from swda.core.circuit_breaker import StepCounter
from swda.core.firewall import SecurityFirewallException
from swda.prime.repl import PrimeREPL
from swda.prime.rlm import RLMDispatcher, load_dotenv
from swda.prime.harness import ContinualHarness
from swda.workflows.crucible import CrucibleWorkflow
from swda.workflows.reconcile import ReverseReconciliation

class TestWorkflows(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_prime_repl_persistent_execution(self):
        bb = Blackboard()
        repl = PrimeREPL(bb)
        # Execute statement 1
        res1 = repl.execute("a = 10")
        self.assertTrue(res1["success"])

        # Execute statement 2 referencing statement 1
        res2 = repl.execute("b = a + 5\nb")
        self.assertTrue(res2["success"])
        self.assertEqual(res2["result"], 15)

    def test_prime_repl_firewall_blocks_mutation_in_gather(self):
        bb = Blackboard()
        bb.as_role(AgentRole.SYSTEM).write("phase", "PHASE_2_GATHER")
        repl = PrimeREPL(bb)

        with self.assertRaises(SecurityFirewallException):
            repl.execute("with open('malicious.py', 'w') as f: f.write('bad')")

    def test_continual_harness_refine_and_persistence(self):
        harness = ContinualHarness(workspace_root=self.temp_dir)
        res = harness.refine(
            trajectory_summary="Builder repeatedly missed Redis connection pool timeout error",
            failure_signal="ResourceLeakError in production redis connector",
        )
        self.assertTrue(os.path.exists(res["path"]))
        patterns = harness.list_anti_patterns()
        self.assertEqual(len(patterns), 1)

    def test_harness_derive_rule_from_failure_signal(self):
        self.assertIn(
            "resource",
            ContinualHarness.derive_rule("Builder missed pool handling", "ResourceLeakError on timeout").lower(),
        )
        self.assertIn(
            "reconciliation",
            ContinualHarness.derive_rule("spec added new API", "hallucinated symbol json.nope").lower(),
        )
        # Unknown signal keeps the surgical-AST default instead of blank
        self.assertIn(
            "surgical ast",
            ContinualHarness.derive_rule("something odd", "mysterious wobble").lower(),
        )
    def test_crucible_workflow_approval(self):
        bb = Blackboard()

        def mock_llm_handler(role: str, prompt: str):
            if role == "builder":
                return {"spec": "Add cache layer", "ttl": 300}
            elif role == "destroyer":
                return {"vector": "Cache stampede under spike load"}
            elif role == "referee":
                return {"passed": True, "score": 9, "reason": "Good specification"}
            return {}

        rlm = RLMDispatcher(mock_handler=mock_llm_handler)
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb, max_rounds=3)
        res = crucible.run_crucible("Optimize database queries")

        self.assertTrue(res.passed)
        self.assertEqual(res.rounds_executed, 1)
        self.assertEqual(bb.read("active_proposal")["spec"], "Add cache layer")

    def test_crucible_role_prompts_are_isolated(self):
        seen = {}

        def spy(role: str, prompt: str):
            seen[role] = prompt
            if role == "builder":
                return {"spec": "S", "secret_builder_note": "B-ONLY"}
            if role == "destroyer":
                return {"vector": "V"}
            return {"passed": True, "score": 9, "reason": "ok"}

        bb = Blackboard()
        rlm = RLMDispatcher(mock_handler=spy)
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb, max_rounds=1)
        crucible.run_crucible("Task T")
        # Builder never sees raw destroyer monologue; destroyer never sees the task.
        self.assertNotIn("B-ONLY", seen.get("destroyer", ""))
        self.assertNotIn("Task T", seen.get("destroyer", ""))
        self.assertIn("Previous round digests", seen.get("builder", ""))
        # Referee gets digest + reconcile re-run, not raw blobs.
        self.assertIn("Critique digest", seen.get("referee", ""))
        self.assertIn("Reconcile re-run", seen.get("referee", ""))

    def test_crucible_anchors_passthrough_and_normalize(self):
        from swda.workflows.crucible import CrucibleWorkflow
        self.assertEqual(CrucibleWorkflow.normalize_anchors("junk"), [])
        self.assertEqual(
            CrucibleWorkflow.normalize_anchors([{"file": "", "line": "x"}, {"file": "a.py", "line": 3}]),
            [{"file": "a.py", "line": 3}],
        )
        brief = CrucibleWorkflow._proposal_brief({"spec": "S", "anchors": [{"file": "a.py", "line": 7, "id": "L7#x"}]})
        self.assertEqual(brief.get("anchors"), [{"file": "a.py", "line": 7, "id": "L7#x"}])
        plain = CrucibleWorkflow._proposal_brief({"spec": "S"})
        self.assertNotIn("anchors", plain)

    def test_reconcile_anchor_hits_cite_lines(self):
        path = os.path.join(self.temp_dir, "anch.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("import json\nx = json.nope_xyz()\n")
        res = ReverseReconciliation.verify_file(path, self.temp_dir,
                                                anchors=[{"file": "anch.py", "line": 2, "id": "L2#abc"}])
        self.assertEqual(res["verdict"], "invalid")
        self.assertEqual(len(res["anchor_hits"]), 1)
        self.assertEqual(res["anchor_hits"][0]["anchor"], "L2#abc")
        res2 = ReverseReconciliation.verify_file(path, self.temp_dir)
        self.assertEqual(res2["verdict"], "invalid")
        self.assertEqual(res2["anchor_hits"], [])

    def test_crucible_string_verdict_parsed_not_auto_passed(self):
        from swda.workflows.crucible import CrucibleWorkflow
        verdict = CrucibleWorkflow._parse_verdict('{"passed": true, "score": 9, "reason": "ok"}', 1)
        self.assertTrue(verdict["passed"])
        self.assertEqual(verdict["score"], 9)

    def test_crucible_garbage_verdict_fails_closed(self):
        from swda.workflows.crucible import CrucibleWorkflow
        from swda.core.circuit_breaker import CircuitBreakerException
        from swda.core.blackboard import Blackboard
        from swda.prime.rlm import RLMDispatcher

        def mock_garbage(role: str, prompt: str):
            if role == "referee":
                return "Some rambling prose without any JSON verdict"
            return {"content": "proposal"}

        bb = Blackboard()
        bb.as_role(AgentRole.BUILDER).write("active_proposal", {"spec": "x", "draft": True})
        rlm = RLMDispatcher(mock_handler=mock_garbage)
        crucible = CrucibleWorkflow(rlm=rlm, blackboard=bb, max_rounds=2)
        with self.assertRaises(CircuitBreakerException):
            crucible.run_crucible("task needing review")
    def test_reverse_reconciliation(self):
        # Create a valid python file
        valid_file = os.path.join(self.temp_dir, "valid_sample.py")
        with open(valid_file, "w", encoding="utf-8") as f:
            f.write("import json\nimport sys\nx = json.dumps({'ok': True})\n")

        res_valid = ReverseReconciliation.verify_file(valid_file, self.temp_dir)
        self.assertTrue(res_valid["valid"])

        # Create an invalid python file importing non-existent module
        invalid_file = os.path.join(self.temp_dir, "invalid_sample.py")
        with open(invalid_file, "w", encoding="utf-8") as f:
            f.write("import phantom_non_existent_module_xyz\n")

        res_invalid = ReverseReconciliation.verify_file(invalid_file, self.temp_dir)
        self.assertFalse(res_invalid["valid"])
        self.assertTrue(any("phantom_non_existent_module_xyz" in err for err in res_invalid["errors"]))

    def test_reverse_reconciliation_hallucinated_from_symbol(self):
        hallu_file = os.path.join(self.temp_dir, "hallu_from.py")
        with open(hallu_file, "w", encoding="utf-8") as f:
            f.write("from os import hallucinated_func_xyz\nprint(hallucinated_func_xyz)\n")

        res = ReverseReconciliation.verify_file(hallu_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("hallucinated_func_xyz" in err for err in res["errors"]))

    def test_reverse_reconciliation_hallucinated_attribute(self):
        hallu_file = os.path.join(self.temp_dir, "hallu_attr.py")
        with open(hallu_file, "w", encoding="utf-8") as f:
            f.write("import json\nx = json.hallucinated_api_xyz()\n")

        res = ReverseReconciliation.verify_file(hallu_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("json.hallucinated_api_xyz" in err for err in res["errors"]))

    def test_reverse_reconciliation_valid_symbols_still_pass(self):
        valid_file = os.path.join(self.temp_dir, "valid_symbols.py")
        with open(valid_file, "w", encoding="utf-8") as f:
            f.write("import json\nfrom os import path\nx = json.dumps({'ok': True})\ny = path.join('a', 'b')\n")

        res = ReverseReconciliation.verify_file(valid_file, self.temp_dir)
        self.assertTrue(res["valid"])
        self.assertEqual(res["verdict"], "valid")
        self.assertEqual(res["warnings"], [])

    def test_reverse_reconciliation_unknown_receiver_is_unverifiable(self):
        recv_file = os.path.join(self.temp_dir, "recv_unknown.py")
        with open(recv_file, "w", encoding="utf-8") as f:
            f.write("import json\ndef get_client():\n    return object()\nclient = get_client()\nclient.made_up_method()\n")

        res = ReverseReconciliation.verify_file(recv_file, self.temp_dir)
        self.assertTrue(res["valid"])
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertTrue(any("client" in w for w in res["warnings"]))

    def test_reverse_reconciliation_star_relative_dynamic_are_unverifiable(self):
        for name, code in [
            ("star_mod.py", "from os import *\nprint(getcwd())\n"),
            ("rel_mod.py", "from . import sibling\nprint(sibling)\n"),
            ("dyn_mod.py", "import importlib\nm = importlib.import_module(x)\ny = getattr(m, name)\n"),
        ]:
            path = os.path.join(self.temp_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            res = ReverseReconciliation.verify_file(path, self.temp_dir)
            self.assertEqual(res["verdict"], "unverifiable", f"{name} should be unverifiable")
            self.assertTrue(res["warnings"], f"{name} should carry warnings")

    def test_reverse_reconciliation_literal_getattr_is_grounded(self):
        path = os.path.join(self.temp_dir, "lit_getattr.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write("import json\nx = getattr(json, 'dumps')\nprint(x({}))\n")
        res = ReverseReconciliation.verify_file(path, self.temp_dir)
        self.assertEqual(res["verdict"], "valid")
        self.assertEqual(res["warnings"], [])

    def test_reverse_reconciliation_deep_chain_is_not_silently_valid(self):
        deep_file = os.path.join(self.temp_dir, "deep_chain.py")
        with open(deep_file, "w", encoding="utf-8") as f:
            f.write("from swda.core.fsm import FSMEngine\nx = FSMEngine.VALID_TRANSITIONS.this_method_does_not_exist()\n")

        res = ReverseReconciliation.verify_file(deep_file, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertNotEqual(res["verdict"], "valid")

    def test_reverse_reconciliation_kind_hint_warns_not_silences(self):
        kind_file = os.path.join(self.temp_dir, "kind_hint.py")
        with open(kind_file, "w", encoding="utf-8") as f:
            f.write("from pathlib import Path\ndef f(p: Path):\n    return p.dirname()\n")

        res = ReverseReconciliation.verify_file(kind_file, self.temp_dir)
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertTrue(res["warnings"])

    def test_reverse_reconciliation_hallucinated_self_method_is_invalid(self):
        self_file = os.path.join(self.temp_dir, "self_hallu.py")
        with open(self_file, "w", encoding="utf-8") as f:
            f.write("class A:\n    def f(self):\n        return self.made_up_xyz()\n")

        res = ReverseReconciliation.verify_file(self_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertEqual(res["verdict"], "invalid")
        self.assertTrue(any("made_up_xyz" in e for e in res["errors"]))

    def test_reverse_reconciliation_real_self_method_stays_quiet(self):
        self_file = os.path.join(self.temp_dir, "self_real.py")
        with open(self_file, "w", encoding="utf-8") as f:
            f.write("class A:\n    def f(self):\n        return 1\n    def g(self):\n        return self.f()\n")

        res = ReverseReconciliation.verify_file(self_file, self.temp_dir)
        self.assertEqual(res["verdict"], "valid")

    def test_reverse_reconciliation_workspace_reexport_is_unverifiable(self):
        with open(os.path.join(self.temp_dir, "reexp.py"), "w", encoding="utf-8") as f:
            f.write("from json import dumps\n")
        use_file = os.path.join(self.temp_dir, "use_reexp.py")
        with open(use_file, "w", encoding="utf-8") as f:
            f.write("from reexp import dumps\nprint(dumps({}))\n")

        res = ReverseReconciliation.verify_file(use_file, self.temp_dir)
        self.assertEqual(res["verdict"], "unverifiable")
        self.assertTrue(any("dumps" in w for w in res["warnings"]))

    def test_reverse_reconciliation_workspace_local_symbol(self):
        pkg_dir = os.path.join(self.temp_dir, "mymod")
        os.makedirs(pkg_dir, exist_ok=True)
        with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
            f.write("def real_fn():\n    return 1\n")

        use_file = os.path.join(self.temp_dir, "use_local.py")
        with open(use_file, "w", encoding="utf-8") as f:
            f.write("from mymod import real_fn\nfrom mymod import fake_fn_xyz\nprint(real_fn())\n")

        res = ReverseReconciliation.verify_file(use_file, self.temp_dir)
        self.assertFalse(res["valid"])
        self.assertTrue(any("fake_fn_xyz" in err for err in res["errors"]))
        self.assertFalse(any("real_fn" in err for err in res["errors"]))

    def test_dotenv_loader_does_not_override_env(self):
        env_file = os.path.join(self.temp_dir, ".env")
        with open(env_file, "w", encoding="utf-8") as f:
            f.write('SWDA_TEST_KEY="from-file"\nSWDA_TEST_OTHER=plain\n# comment\n\n')
        os.environ["SWDA_TEST_KEY"] = "from-env"
        os.environ.pop("SWDA_TEST_OTHER", None)
        try:
            loaded = load_dotenv(search_paths=[env_file])
            self.assertEqual(loaded, env_file)
            self.assertEqual(os.environ["SWDA_TEST_KEY"], "from-env")
            self.assertEqual(os.environ["SWDA_TEST_OTHER"], "plain")
        finally:
            del os.environ["SWDA_TEST_KEY"]
            os.environ.pop("SWDA_TEST_OTHER", None)

    def test_rlm_fallback_chain_always_ends_with_auto_free(self):
        saved = os.environ.get("SWDA_FALLBACK_MODELS")
        os.environ["SWDA_FALLBACK_MODELS"] = ""
        try:
            rlm = RLMDispatcher(default_model="x", fallback_models=["a", "b"])
            self.assertEqual(rlm.fallback_models, ["a", "b", RLMDispatcher.AUTO_FREE_MODEL])
            rlm2 = RLMDispatcher(default_model="x", fallback_models=[])
            self.assertEqual(rlm2.fallback_models, [RLMDispatcher.AUTO_FREE_MODEL])
        finally:
            if saved is None:
                del os.environ["SWDA_FALLBACK_MODELS"]
            else:
                os.environ["SWDA_FALLBACK_MODELS"] = saved

    def test_rlm_category_routing(self):
        self.assertEqual(RLMDispatcher.category_for_role("builder"), "standard")
        self.assertEqual(RLMDispatcher.category_for_role("destroyer"), "deep")
        self.assertEqual(RLMDispatcher.category_for_role("referee"), "deep")
        self.assertEqual(RLMDispatcher.category_for_role("alpha"), "quick")
        self.assertEqual(RLMDispatcher.category_for_role("unknown-role"), "standard")
        saved = os.environ.pop("SWDA_MODEL_DEEP", None)
        os.environ["SWDA_MODEL_DEEP"] = "strong-model"
        try:
            self.assertEqual(RLMDispatcher.model_for_category("deep"), "strong-model")
            self.assertEqual(RLMDispatcher.model_for_category("quick", default="base"), "base")
        finally:
            if saved is None:
                del os.environ["SWDA_MODEL_DEEP"]
            else:
                os.environ["SWDA_MODEL_DEEP"] = saved

    def test_rlm_socket_timeout_wrapped_as_runtime_error(self):
        import socket
        from unittest import mock
        rlm = RLMDispatcher(default_model="x")
        with mock.patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            with self.assertRaisesRegex(RuntimeError, "RLM Timeout"):
                rlm._call_endpoint({"model": "x", "messages": []})
            with self.assertRaisesRegex(RuntimeError, "RLM Timeout"):
                rlm.list_models(timeout=1)

    def test_rlm_http_error_keeps_body_for_fallback(self):
        """A gateway rejection must surface its body: the model fallback chain
        keys on 'model_not_allowed', which only exists in the response text."""
        import io as _io
        import urllib.error
        from unittest import mock

        body = b'{"error":{"code":"model_not_allowed","message":"model \\"x\\" is not allowed"}}'
        err = urllib.error.HTTPError("http://gw/v1/chat/completions", 400,
                                     "Bad Request", None, _io.BytesIO(body))
        rlm = RLMDispatcher(default_model="x", api_base="http://gw/v1")
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(RuntimeError, "model_not_allowed"):
                rlm._call_endpoint({"model": "x", "messages": []})

    def test_rlm_spawn_walks_fallback_on_model_not_allowed(self):
        """spawn() retries the fallback chain when the primary model is rejected."""
        import io as _io
        import urllib.error
        from unittest import mock

        body = b'{"error":{"code":"model_not_allowed"}}'
        calls = []

        def fake_urlopen(req, timeout=None):
            payload = json.loads(req.data.decode())
            calls.append(payload["model"])
            if payload["model"] == "primary":
                raise urllib.error.HTTPError(req.full_url, 400, "Bad Request",
                                             None, _io.BytesIO(body))
            resp = mock.MagicMock()
            resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}).encode()
            resp.__enter__.return_value = resp
            resp.__exit__.return_value = False
            return resp

        rlm = RLMDispatcher(default_model="primary", api_base="http://gw/v1",
                            fallback_models=["backup"])
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            out = rlm.spawn(role="builder", prompt="hi")
        self.assertEqual(out, "ok")
        self.assertEqual(calls, ["primary", "backup"])

if __name__ == "__main__":
    unittest.main()
