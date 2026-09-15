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
        self.workspace_root = workspace_root or os.getcwd()
        self.log_dir = os.path.join(self.workspace_root, ".swda")
        self.log_file = os.path.join(self.log_dir, "metrics.jsonl")
        os.makedirs(self.log_dir, exist_ok=True)
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

        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "span_name": span_name,
            "duration_ms": duration_ms,
            "success": success,
            "tokens_used": tokens_used,
            "metadata": metadata or {},
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def get_summary(self) -> Dict[str, Any]:
        """Aggregates metrics across all recorded spans."""
        if not os.path.exists(self.log_file):
            return {"total_calls": 0, "successful_calls": 0, "success_rate": 1.0, "total_tokens": 0, "avg_duration_ms": 0}

        records: List[Dict[str, Any]] = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        if not records:
            return {"total_calls": 0, "successful_calls": 0, "success_rate": 1.0, "total_tokens": 0, "avg_duration_ms": 0}

        total_calls = len(records)
        successful = sum(1 for r in records if r.get("success", False))
        total_tokens = sum(r.get("tokens_used", 0) for r in records)
        total_duration = sum(r.get("duration_ms", 0.0) for r in records)

        return {
            "total_calls": total_calls,
            "successful_calls": successful,
            "success_rate": round(successful / total_calls, 4) if total_calls > 0 else 1.0,
            "total_tokens": total_tokens,
            "avg_duration_ms": round(total_duration / total_calls, 2) if total_calls > 0 else 0.0,
        }
