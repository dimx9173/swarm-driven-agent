"""
SWDA Compaction: structured session summaries (from prime-agent).

Template mirrors prime-agent's compaction summary format
(`docs/compaction.md` structured summary): Goal / Constraints / Progress /
Key Decisions / Next Steps / Critical Context, plus cumulative
<read-files> / <modified-files> tracking.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

TAG_RE = re.compile(r"<(INTENT_GATE_RESULT|DESTRUCT_RESULT|GATHER_RESULT|HYPERPLAN_RESULT|SYSTEM_SPECIFICATION|TASK_SUMMARY_REPORT)>")
STATE_RE = re.compile(r"\[NEXT_STATE:\s*([^\]]+)\]")


def summarize_lines(lines: List[str]) -> Dict[str, Any]:
    """Builds a structured summary from session jsonl lines (stdlib only)."""
    tags: Dict[str, int] = {}
    states: List[str] = []
    read_files: List[str] = []
    modified_files: List[str] = []
    texts: List[str] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        blob = json.dumps(obj, ensure_ascii=False)[:4000]
        for tag in TAG_RE.findall(blob):
            tags[tag] = tags.get(tag, 0) + 1
        states.extend(STATE_RE.findall(blob))
        for m in re.finditer(r'"(?:path|file)"\s*:\s*"([^"]+\.py)"', blob):
            read_files.append(os.path.basename(m.group(1)))
        texts.append(blob[:200])
    return {
        "tags": tags,
        "next_states": states[-5:],
        "read_files": sorted(set(read_files)),
        "modified_files": sorted(set(modified_files)),
        "lines_scanned": len(lines),
    }


def render_markdown(summary: Dict[str, Any], goal: str = "") -> str:
    """Renders the structured compaction summary format."""
    tags = ", ".join(f"{k}x{v}" for k, v in summary.get("tags", {}).items()) or "none"
    states = ", ".join(summary.get("next_states", [])[-3:]) or "none"
    reads = "\n".join(summary.get("read_files", [])) or "(none)"
    mods = "\n".join(summary.get("modified_files", [])) or "(none)"
    return (
        "## Goal\n" + (goal or "(not stated)") + "\n\n"
        "## Constraints & Preferences\n- (carried from contract: FSM discipline, delivery-gate)\n\n"
        "## Progress\n### Done\n- FSM tags observed: " + tags + "\n"
        "### In Progress\n- Latest states: " + states + "\n"
        "### Blocked\n- (none recorded)\n\n"
        "## Key Decisions\n- (from crucible verdicts in slice)\n\n"
        "## Next Steps\n1. (continue from latest NEXT_STATE)\n\n"
        "## Critical Context\n- lines scanned: " + str(summary.get("lines_scanned", 0)) + "\n\n"
        "<read-files>\n" + reads + "\n</read-files>\n\n"
        "<modified-files>\n" + mods + "\n</modified-files>\n"
    )


def compact_session_file(path: str, goal: str = "", max_lines: Optional[int] = None) -> Dict[str, Any]:
    """Compacts a session jsonl file into the structured summary format."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    if max_lines is not None:
        lines = lines[-max_lines:]
    summary = summarize_lines(lines)
    summary["markdown"] = render_markdown(summary, goal=goal)
    return summary
