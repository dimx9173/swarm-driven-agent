#!/usr/bin/env python3
"""Regression tests for telemetry credibility: mock/real split summaries."""
import os
import shutil
import tempfile
import unittest

from swda.telemetry import TelemetryLogger


class TestTelemetrySplits(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_mock_and_real_spans_split(self):
        log = TelemetryLogger(workspace_root=self.temp_dir)
        log.start_span("full_run")
        log.end_span("full_run", success=True, metadata={"mock": True, "model": "mock"})
        log.start_span("full_run")
        log.end_span("full_run", success=True, metadata={"mock": False, "model": "openrouter/free"})
        log.start_span("full_run")
        log.end_span("full_run", success=False, metadata={"mock": False, "model": "openrouter/free"})

        summary = log.get_summary()
        self.assertEqual(summary["total_calls"], 3)
        self.assertEqual(summary["successful_calls"], 2)
        self.assertEqual(summary["mock"]["total_calls"], 1)
        self.assertEqual(summary["real"]["total_calls"], 2)
        self.assertEqual(summary["real"]["successful_calls"], 1)

    def test_legacy_spans_without_metadata_still_summarized(self):
        log = TelemetryLogger(workspace_root=self.temp_dir)
        log.start_span("full_run")
        log.end_span("full_run", success=True)
        summary = log.get_summary()
        self.assertEqual(summary["total_calls"], 1)
        self.assertIn("mock", summary)
        self.assertIn("real", summary)

    def test_repo_root_resolution_prefers_env(self):
        os.environ["SWDA_REPO"] = self.temp_dir
        try:
            log = TelemetryLogger()
            self.assertEqual(log.workspace_root, self.temp_dir)
        finally:
            del os.environ["SWDA_REPO"]


if __name__ == "__main__":
    unittest.main()
