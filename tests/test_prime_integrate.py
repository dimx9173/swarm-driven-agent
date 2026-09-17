#!/usr/bin/env python3
"""Regression tests for prime-agent integrations: spawn, harness store, compact, goal."""
import os
import shutil
import tempfile
import threading
import time
import unittest

from swda.agents.spawn import ChildRegistry, Inbox, SubagentRunner
from swda.prime.harness import ContinualHarness, HarnessState
from swda.workflows.compact import compact_session_file, render_markdown, summarize_lines
from swda.workflows.goal import GoalStore


class TestAdmissionHandle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.inbox = Inbox()
        self.reg = ChildRegistry(os.path.join(self.tmp, "children"))
        self.runner = SubagentRunner(
            self.reg, self.inbox,
            handler=lambda name, prompt: f"{name}:{prompt[:10]}")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_spawn_returns_handle_without_answer(self):
        h = self.runner.spawn("review the API", name="api")
        self.assertTrue(h.child_id)
        self.assertFalse(hasattr(h, "answer"))
        self.assertEqual(h.depth, 0)

    def test_answer_arrives_via_inbox_only(self):
        self.runner.spawn("review the tests", name="tests")
        msgs = self.inbox.wait(sender_name="tests", timeout=5)
        self.assertEqual(len(msgs), 1)
        self.assertIn("tests", msgs[0]["message"])
        rec = self.reg.get("tests")
        self.assertEqual(rec.status, "completed")

    def test_name_required_and_depth_capped(self):
        with self.assertRaises(ValueError):
            self.runner.spawn("x", name="")
        with self.assertRaises(RuntimeError):
            self.runner.spawn("x", name="g", depth=2)

    def test_registry_lists_and_cancels(self):
        gate = threading.Event()

        def slow(name, prompt):
            gate.wait(timeout=5)
            return "slow-done"

        slow_runner = SubagentRunner(self.reg, self.inbox, handler=slow)
        h = slow_runner.spawn("slow audit", name="audit")
        self.assertEqual(self.reg.get(h.child_id).status, "running")
        self.reg.cancel(h.child_id)
        gate.set()
        self.assertEqual(self.reg.get(h.child_id).status, "cancelled")

class TestHarnessStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upsert_versions_and_reloads(self):
        st = HarnessState(state_path=os.path.join(self.tmp, "h.json"))
        e1 = st.upsert(kind="prompt", id_="p1", title="t", content="c")
        self.assertEqual(e1["version"], 1)
        e2 = st.upsert(kind="prompt", id_="p1", title="t2", content="c2")
        self.assertEqual(e2["version"], 2)
        st2 = HarnessState(state_path=os.path.join(self.tmp, "h.json"))
        self.assertEqual(st2.get("prompt", "p1")["title"], "t2")

    def test_unknown_kind_rejected(self):
        st = HarnessState(in_memory=True)
        with self.assertRaises(ValueError):
            st.upsert(kind="nope", id_="x", title="t", content="c")

    def test_refinement_and_snapshot_rollback(self):
        st = HarnessState(in_memory=True)
        ev = st.record_refinement(trigger="t", changes=["memory:x +created"], evidence="e")
        self.assertEqual(ev["trigger"], "t")
        snap = st.snapshot()
        st.upsert(kind="memory", id_="m", title="t", content="c")
        st.restore(snap)
        self.assertIsNone(st.get("memory", "m"))

    def test_corrupt_disk_keeps_memory(self):
        path = os.path.join(self.tmp, "h.json")
        st = HarnessState(state_path=path)
        st.upsert(kind="memory", id_="m", title="t", content="c")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{broken")
        st2 = HarnessState(state_path=path)
        self.assertEqual(st2.list(), [])

    def test_refine_keeps_yaml_and_records_event(self):
        h = ContinualHarness(workspace_root=self.tmp)
        res = h.refine("hallucinated import", "from os import nope_xyz")
        self.assertTrue(os.path.exists(res["path"]))
        self.assertEqual(len(h.state.refinements), 1)
        self.assertTrue(h.format_focal_context())


class TestCompact(unittest.TestCase):
    def test_summarize_and_render(self):
        lines = [
            '{"message": {"role": "assistant", "content": [{"type": "text", "text": "<SYSTEM_SPECIFICATION>\\nX\\n</SYSTEM_SPECIFICATION>\\n[NEXT_STATE: Y]"}]}}',
            '{"type": "custom", "customType": "tool_execution_start", "data": {"toolName": "edit", "args": {"path": "a.py"}}}',
        ]
        s = summarize_lines(lines)
        self.assertEqual(s["tags"].get("SYSTEM_SPECIFICATION"), 1)
        md = render_markdown(s, goal="ship it")
        for section in ("## Goal", "## Progress", "## Next Steps", "<read-files>", "<modified-files>"):
            self.assertIn(section, md)

    def test_compact_session_file(self):
        import tempfile as _t
        d = _t.mkdtemp()
        try:
            p = os.path.join(d, "s.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write('{"a": 1}\n')
                f.write('{"message": {"role": "assistant", "content": "hi <TASK_SUMMARY_REPORT> done </TASK_SUMMARY_REPORT>"}}\n')
            s = compact_session_file(p, goal="g")
            self.assertIn("markdown", s)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestGoalStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = GoalStore(workspace_root=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_get_note_complete(self):
        g = self.store.create("ship the release", token_budget=1000)
        self.assertEqual(g["status"], "active")
        self.assertEqual(self.store.get()["objective"], "ship the release")
        n = self.store.note("did step 1", tokens_used=10)
        self.assertEqual(n["continuations"], 1)
        self.assertEqual(n["tokens_used"], 10)
        done = self.store.complete()
        self.assertEqual(done["status"], "completed")
        self.assertIsNone(self.store.get())

    def test_pause_resume_clear(self):
        self.store.create("goal a")
        self.store.pause()
        self.assertIsNone(self.store.get())
        self.store.resume()
        self.assertIsNotNone(self.store.get())
        self.store.complete()
        self.store.clear()
        self.assertEqual(self.store._read_all(), [])


if __name__ == "__main__":
    unittest.main()
