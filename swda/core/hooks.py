"""
SWDA Execution Hooks: deterministic enforcement around tool execution.

Mirrors the Claude Code / Codex hook shape in-process:
  * PreToolUse  -- runs before a tool executes; a hook returning
    ``{"decision": "block", "reason": ...}`` aborts the call.
  * PostToolUse -- runs after a tool finishes; observes the result.
  * Stop        -- delivery gate before a phase completes; a block
    verdict returns the task to rework instead of delivering.

Hooks are plain callables ``fn(event) -> Optional[dict]`` where event is a
dict with at least ``{"tool": str, "args": dict}``. Returning None (or a dict
without ``decision == "block"``) allows the execution to proceed.
"""
from typing import Any, Callable, Dict, List, Optional

HookFn = Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]

PRE_TOOL_USE = "PreToolUse"
POST_TOOL_USE = "PostToolUse"
STOP = "Stop"

_EVENTS = (PRE_TOOL_USE, POST_TOOL_USE, STOP)


class HookBlocked(Exception):
    """Raised when a PreToolUse/Stop hook blocks an execution."""

    def __init__(self, tool: str, reason: str):
        self.tool = tool
        self.reason = reason
        super().__init__(f"[hook-blocked:{tool}] {reason}")


class HookRegistry:
    """Ordered hook lists per lifecycle event (stdlib only)."""

    def __init__(self):
        self._hooks: Dict[str, List[HookFn]] = {e: [] for e in _EVENTS}

    def register(self, event: str, fn: HookFn) -> HookFn:
        if event not in _EVENTS:
            raise ValueError(f"Unknown hook event: {event!r} (want one of {_EVENTS})")
        self._hooks[event].append(fn)
        return fn

    def unregister(self, event: str, fn: HookFn) -> None:
        try:
            self._hooks[event].remove(fn)
        except (KeyError, ValueError):
            pass

    def clear(self, event: Optional[str] = None) -> None:
        if event is None:
            for e in _EVENTS:
                self._hooks[e] = []
        elif event in _EVENTS:
            self._hooks[event] = []

    def run_pre(self, tool: str, args: Optional[Dict[str, Any]] = None) -> None:
        """Runs PreToolUse hooks; raises HookBlocked on the first block."""
        event = {"tool": tool, "args": dict(args or {})}
        for fn in list(self._hooks[PRE_TOOL_USE]):
            verdict = fn(event) or {}
            if isinstance(verdict, dict) and verdict.get("decision") == "block":
                raise HookBlocked(tool, str(verdict.get("reason", "blocked by PreToolUse hook")))

    def run_post(self, tool: str, args: Optional[Dict[str, Any]] = None,
                 result: Optional[Dict[str, Any]] = None) -> None:
        """Runs PostToolUse hooks (observational; blocks are ignored)."""
        event = {"tool": tool, "args": dict(args or {}), "result": result or {}}
        for fn in list(self._hooks[POST_TOOL_USE]):
            try:
                fn(event)
            except Exception:
                continue

    def run_stop(self, tool: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Runs Stop-gate hooks; raises HookBlocked to force rework."""
        event = {"tool": tool, "context": dict(context or {})}
        for fn in list(self._hooks[STOP]):
            verdict = fn(event) or {}
            if isinstance(verdict, dict) and verdict.get("decision") == "block":
                raise HookBlocked(tool, str(verdict.get("reason", "blocked by Stop gate")))
