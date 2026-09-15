"""
SWDA Continual Harness: Self-Improving Operational Scaffolding and Anti-Pattern Storage.
Integrates Prime Agent's /refine methodology with SWDA L2 Memory Palace.
"""

import os
import glob
from datetime import datetime
from typing import Dict, List, Optional, Any


class ContinualHarness:
    """
    Maintains durable harness state across sessions.
    Allows evidence-backed refinement of operating rules, skills, and anti-patterns.
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self.anti_patterns_dir = os.path.join(self.workspace_root, "docs", "anti-patterns")
        os.makedirs(self.anti_patterns_dir, exist_ok=True)

    def record_anti_pattern(
        self,
        name: str,
        trigger_vector: str,
        failure_reason: str,
        corrective_rule: str,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Extracts a failure pattern from Crucible or TDD test runs and persists it as a YAML file.
        """
        filename = f"{name.lower().replace(' ', '_').replace('/', '_')}.yaml"
        target_path = os.path.join(self.anti_patterns_dir, filename)

        content = (
            f"# SWDA Continual Harness Anti-Pattern\n"
            f"name: \"{name}\"\n"
            f"recorded_at: \"{datetime.now().isoformat()}\"\n"
            f"tags: {tags or []}\n"
            f"trigger_vector: |\n  {trigger_vector.strip()}\n"
            f"failure_reason: |\n  {failure_reason.strip()}\n"
            f"corrective_rule: |\n  {corrective_rule.strip()}\n"
        )

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        return target_path

    def refine(self, trajectory_summary: str, failure_signal: str) -> Optional[Dict[str, str]]:
        """
        Reviews a failed trajectory and synthesizes an evidence-backed anti-pattern record.
        """
        pattern_name = f"refine_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = self.record_anti_pattern(
            name=pattern_name,
            trigger_vector=trajectory_summary[:300],
            failure_reason=failure_signal[:300],
            corrective_rule="Prioritize surgical AST verification before modifying dependent call sites.",
            tags=["auto-refine", "crucible-failure"]
        )
        return {"name": pattern_name, "path": path}

    def list_anti_patterns(self) -> List[Dict[str, Any]]:
        """Lists all registered anti-patterns in the workspace."""
        patterns = []
        for file in glob.glob(os.path.join(self.anti_patterns_dir, "*.yaml")):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    meta = {}
                    for line in lines:
                        if line.startswith("name:"):
                            meta["name"] = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith("recorded_at:"):
                            meta["recorded_at"] = line.split(":", 1)[1].strip().strip('"\'')
                    meta["file"] = os.path.basename(file)
                    patterns.append(meta)
            except Exception:
                continue
        return patterns

    def format_focal_context(self, max_items: int = 5) -> str:
        """
        Formats top anti-patterns for Arachne focal positioning (placed at front and rear of context).
        """
        patterns = self.list_anti_patterns()[:max_items]
        if not patterns:
            return ""

        formatted = ["<ANCHORED_ANTI_PATTERNS>"]
        for p in patterns:
            formatted.append(f"  - Pattern: {p.get('name')} (File: {p.get('file')})")
        formatted.append("</ANCHORED_ANTI_PATTERNS>")
        return "\n".join(formatted)
