"""
SWDA Telemetry & Observability:
Tracks per-phase execution latency (ms), token consumption, and tool success rate.
Enables data-driven architecture optimization instead of blind parameter tuning.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional


class TelemetryLogger:
    """
    Records execution metrics to local jsonl storage for monitoring and analysis.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        root = workspace_root or os.environ.get("SWDA_REPO") or os.getcwd()
        self.workspace_root = root
        self.log_dir = os.path.join(self.workspace_root, ".swda")
        self.log_file = os.path.join(self.log_dir, "metrics.jsonl")
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except OSError:
            pass  # read-only contexts (e.g. MCP stats) must not crash
        self._active_spans: Dict[str, float] = {}

    def start_span(self, span_name: str) -> None:
        """Starts timing a phase or tool call."""
        self._active_spans[span_name] = time.time()

    def end_span(
        self,
        span_name: str,
        success: bool = True,
        tokens_used: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ends timing and writes the recorded event to the log file."""
        start_time = self._active_spans.pop(span_name, time.time())
        duration_ms = round((time.time() - start_time) * 1000, 2)
        meta = dict(metadata or {})
        meta.setdefault("repo", os.path.basename(os.path.abspath(self.workspace_root)))

        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "span_name": span_name,
            "duration_ms": duration_ms,
            "success": success,
            "tokens_used": tokens_used,
            "metadata": meta,
        }
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            record["metadata"] = {**meta, "persisted": False}

        return record

    def get_summary(self) -> Dict[str, Any]:
        """Aggregates metrics across all recorded spans (mock and real split)."""
        empty = {"total_calls": 0, "successful_calls": 0, "success_rate": 1.0,
                 "total_tokens": 0, "avg_duration_ms": 0}
        if not os.path.exists(self.log_file):
            return {**empty, "mock": dict(empty), "real": dict(empty)}

        records: List[Dict[str, Any]] = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        def _summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not rows:
                return dict(empty)
            total = len(rows)
            ok = sum(1 for r in rows if r.get("success", False))
            return {
                "total_calls": total,
                "successful_calls": ok,
                "success_rate": round(ok / total, 4),
                "total_tokens": sum(r.get("tokens_used", 0) for r in rows),
                "avg_duration_ms": round(sum(r.get("duration_ms", 0.0) for r in rows) / total, 2),
            }

        def _is_mock(r: Dict[str, Any]) -> bool:
            meta = r.get("metadata", {})
            if isinstance(meta, dict) and "mock" in meta:
                return bool(meta["mock"])
            # Legacy heuristic for pre-tag spans: offline mock spans finish in
            # well under a second. Buckets holding such rows are estimates.
            return (r.get("duration_ms", 0.0) or 0.0) < 1000.0

        summary = _summarize(records)
        mock_rows = [r for r in records if _is_mock(r)]
        real_rows = [r for r in records if not _is_mock(r)]
        legacy = [r for r in records if not (isinstance(r.get("metadata"), dict) and "mock" in r["metadata"])]
        summary["mock"] = _summarize(mock_rows)
        summary["real"] = _summarize(real_rows)
        summary["legacy_heuristic_rows"] = len(legacy)
        return summary
