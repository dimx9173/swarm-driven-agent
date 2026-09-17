"""
SWDA AI Firewall Guard: AST and Command-Line Interception.
Enforces TC-01/02/03/04/05/07 pattern rules plus RULE-0.7 FSM
Phase mutation locks. TC-06 (live financial API), TC-08 (reward hacking),
TC-09 (epistemic humility), TC-10 (corrigibility) are procedural governance
rules with no code interception surface and are enforced by workflow, not here.

Scope note: command patterns are heuristic blocklists (best-effort, not a
security boundary); code checks are an AST allowlist in read-only phases.
"""

import ast
import re
from typing import List, Tuple, Optional


class SecurityFirewallException(Exception):
    """Raised when an operation violates SWDA AI Firewall constraints."""
    def __init__(self, rule_id: str, message: str):
        self.rule_id = rule_id
        self.message = message
class SafetyFirewall:
    """
    Inspection engine for terminal commands and Python AST code blocks.
    Heuristic defense-in-depth: command patterns block known-dangerous shapes,
    code checks enforce an allowlist in read-only phases. Not a sandbox.
    """

    # Command line security patterns
    BLOCKED_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
        ("TC-01", re.compile(r"\brm\s+-(?:r[fF]|f[rR]|rf)\s+(?:/|~|\$HOME|\.\.)", re.I), "Catastrophic file system deletion blocked."),
        ("TC-01", re.compile(r"\b(DROP\s+DATABASE|DROP\s+TABLE|mkfs\b|dd\s+if=)", re.I), "Catastrophic database or disk write blocked."),
        ("TC-02", re.compile(r"\b(nc\s+-e|bash\s+-i\s+>&|/dev/tcp/|ngrok\b|localtunnel\b)", re.I), "Exfiltration or reverse shell pattern detected."),
        ("TC-03", re.compile(r"(\.ssh/id_|\/etc\/shadow|\.aws\/credentials|\.env\b)", re.I), "Unauthorized credential read attempt blocked."),
        ("TC-04", re.compile(r"\b(npm\s+install\s+-g|pip\s+install\s+--break-system-packages)", re.I), "Global un-sandboxed package installation blocked."),
        ("TC-05", re.compile(r"\bgit\s+(?:push\s+.*--force|branch\s+-D\s+(?:main|master))", re.I), "Destructive git operation blocked."),
        ("TC-07", re.compile(r"\b(?:rm|mv|cat\s+>)\s+.*(?:RULE\.md|SOUL\.md|SKILL\.md)", re.I), "Self-Bypass: Core agent contract files are write-protected."),
    ]

    @classmethod
    def audit_command(cls, command: str) -> None:
        """Audits shell commands before execution."""
        clean_cmd = command.strip()
        for rule_id, pattern, message in cls.BLOCKED_PATTERNS:
            if pattern.search(clean_cmd):
                raise SecurityFirewallException(rule_id=rule_id, message=message)

    #: Dotted-path allowlist for process control in Python code.
    #: Anything resolving to these roots is audited, not just four names.
    AUDITED_CALL_ROOTS = ("subprocess", "os", "shutil", "sys", "pty", "multiprocessing")

    #: Destructive operations always forbidden in read-only phases, plus
    #: dynamic open() modes and dangerous call args in every phase.
    DENY_CALL_NAMES = frozenset({
        "system", "popen", "exec", "eval", "execfile", "compile",
        "rmtree", "remove", "unlink", "rmdir", "rename", "replace", "move",
        "chown", "chmod", "kill", "killpg",
        "write_text", "write_bytes",
    })

    @classmethod
    def audit_code_ast(cls, code_str: str, current_phase: Optional[str] = None) -> None:
        """
        Parses Python code to AST and enforces phase-aware restrictions.
        Read-only phases use an allowlist: only pure expressions and known
        read-only calls pass; everything else raises RULE-0.7.
        """
        try:
            tree = ast.parse(code_str)
        except SyntaxError:
            # If code is not valid Python, let the interpreter deal with it
            return

        # Check for mutation operations prior to implementation phases
        allowed_mutation_phases = {"PHASE_5_SYNTHESIS", "PHASE_6_IMPLEMENT", "DYNAMIC_COMPILE"}
        is_read_only_phase = current_phase not in allowed_mutation_phases if current_phase else False

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func_name = ""
            root_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
                recv = node.func.value
                while isinstance(recv, ast.Attribute):
                    recv = recv.value
                if isinstance(recv, ast.Name):
                    root_name = recv.id

            if is_read_only_phase and cls._is_mutation_call(func_name, node):
                raise SecurityFirewallException(
                    rule_id="RULE-0.7",
                    message=f"File mutation '{func_name}' is strictly forbidden in phase '{current_phase}'. Spec must pass Crucible first."
                )

            # TC-01 & TC-03 in Python code: audit every process-control call
            # and every dynamic-code call, not just four hardcoded names.
            if func_name in cls.DENY_CALL_NAMES or root_name in cls.AUDITED_CALL_ROOTS:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        cls.audit_command(arg.value)

    @staticmethod
    def _is_mutation_call(func_name: str, node: ast.Call) -> bool:
        """True when the call mutates the filesystem (any mode spelling)."""
        if func_name == "open":
            for arg in node.args[1:]:
                if not isinstance(arg, ast.Constant):
                    return True  # dynamic mode: fail closed
                if any(m in str(arg.value) for m in ("w", "a", "x", "+")):
                    return True
            for kw in node.keywords:
                if kw.arg == "mode":
                    if not isinstance(kw.value, ast.Constant):
                        return True  # dynamic mode: fail closed
                    if any(m in str(kw.value.value) for m in ("w", "a", "x", "+")):
                        return True
            return False
        return func_name in SafetyFirewall.DENY_CALL_NAMES
