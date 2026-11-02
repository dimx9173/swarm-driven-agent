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
import os
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
                 result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Runs PostToolUse hooks inside the tool loop (Harness² middleware).

        Uncaught exceptions inside individual hook callables are swallowed so a
        buggy observer never crashes the host. Structured return dicts from a
        hook may supply:
          * ``trimmed_stdout`` / ``trimmed_stderr`` -- replace oversized streams
          * ``hint`` -- append a targeted remediation hint to ``hints`` / ``stderr``
          * ``decision == "block"`` + ``reason`` -- flag post-execution block on
            ``result["blocked"]`` and ``result["block_reason"]``
        Mutates ``result`` in place when a dict is passed and returns it.
        """
        target = result if isinstance(result, dict) else {}
        event = {"tool": tool, "args": dict(args or {}), "result": target}
        pending_hints: List[str] = []
        for fn in list(self._hooks[POST_TOOL_USE]):
            try:
                verdict = fn(event)
            except Exception:
                continue
            if not isinstance(verdict, dict):
                continue
            if isinstance(verdict.get("trimmed_stdout"), str):
                target["stdout"] = verdict["trimmed_stdout"]
                target["trimmed"] = True
            if isinstance(verdict.get("trimmed_stderr"), str):
                target["stderr"] = verdict["trimmed_stderr"]
                target["trimmed"] = True
            if isinstance(verdict.get("hint"), str) and verdict["hint"].strip():
                clean_hint = verdict["hint"].strip()
                hints = target.get("hints")
                if not isinstance(hints, list):
                    hints = []
                    target["hints"] = hints
                hints.append(clean_hint)
                pending_hints.append(f"[Harness² Hint] {clean_hint}")
            if verdict.get("decision") == "block":
                reason = str(verdict.get("reason", "blocked by PostToolUse hook"))
                target["blocked"] = True
                target["block_reason"] = reason
                target["passed"] = False
                target["success"] = False
        if pending_hints:
            prev_raw = target.get("stderr")
            prev_err = prev_raw if isinstance(prev_raw, str) else ""
            hint_block = "\n".join(pending_hints)
            target["stderr"] = f"{prev_err}\n{hint_block}" if prev_err else hint_block
        return target

    def run_stop(self, tool: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Runs Stop-gate hooks; raises HookBlocked to force rework."""
        event = {"tool": tool, "context": dict(context or {})}
        for fn in list(self._hooks[STOP]):
            verdict = fn(event) or {}
            if isinstance(verdict, dict) and verdict.get("decision") == "block":
                raise HookBlocked(tool, str(verdict.get("reason", "blocked by Stop gate")))


def _trim_stream(text: Any, max_chars: int) -> Optional[str]:
    if not isinstance(text, str):
        return None
    eff_max = max(int(max_chars), 40)
    if len(text) <= eff_max:
        return None
    half = eff_max // 2
    dropped = len(text) - (half * 2)
    trimmed = f"{text[:half]}\n...[trimmed {dropped} chars by PostToolUse hook]...\n{text[-half:]}"
    return trimmed if len(trimmed) < len(text) else None


def make_output_trimmer_hook(max_chars: int = 8000) -> HookFn:
    """Harness² PostToolUse hook: trims oversized stdout/stderr to protect context budget."""
    def _hook(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        res = event.get("result") or {}
        out: Dict[str, Any] = {}
        t_out = _trim_stream(res.get("stdout", ""), max_chars)
        if t_out is not None:
            out["trimmed_stdout"] = t_out
        t_err = _trim_stream(res.get("stderr", ""), max_chars)
        if t_err is not None:
            out["trimmed_stderr"] = t_err
        return out or None
    return _hook


DEFAULT_ERROR_HINTS: Dict[str, str] = {
    "ModuleNotFoundError": "Verify existing workspace imports before introducing new packages (§2.5).",
    "ImportError": "Run swda reconcile to check whether the imported symbol exists in the target module.",
    "SyntaxError": "Inspect unclosed brackets, indentation, or template braces before retrying.",
}


def make_error_hint_hook(signatures: Optional[Dict[str, str]] = None) -> HookFn:
    """Harness² PostToolUse hook: appends a targeted hint after recurring error signatures."""
    table = dict(DEFAULT_ERROR_HINTS)
    if signatures:
        table.update(signatures)

    def _hook(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        res = event.get("result") or {}
        blob_low = f"{res.get('stderr', '')}\n{res.get('error', '')}".lower()
        for sig, hint in table.items():
            if sig.lower() in blob_low:
                return {"hint": hint}
        return None
    return _hook


def make_post_write_reconcile_hook(workspace_root: str) -> HookFn:
    """Harness² PostToolUse hook: verifies a Python file write immediately via AST reconcile."""
    from swda.workflows.reconcile import ReverseReconciliation
    real_root = os.path.realpath(workspace_root)

    def _hook(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        args = event.get("args") or {}
        target_file = args.get("file") or args.get("path") or args.get("file_path")
        if not isinstance(target_file, str) or not target_file.endswith(".py"):
            return None
        full = target_file if os.path.isabs(target_file) else os.path.join(workspace_root, target_file)
        real_full = os.path.realpath(full)
        if real_full != real_root and not real_full.startswith(real_root + os.sep):
            return {
                "decision": "block",
                "reason": f"Post-write path escapes workspace: {target_file}",
            }
        if not os.path.isfile(real_full):
            return None
        try:
            verdict = ReverseReconciliation.verify_file(real_full, workspace_root)
        except Exception as exc:
            return {
                "decision": "block",
                "reason": f"Post-write reconcile error for {target_file}: {exc}",
            }
        if verdict.get("verdict") == "invalid":
            errs = "; ".join(verdict.get("errors", [])[:3])
            return {"decision": "block", "reason": f"Post-write reconcile failed for {target_file}: {errs}"}
        return None
    return _hook
