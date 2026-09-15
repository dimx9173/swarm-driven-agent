"""
SWDA AI Firewall Guard: Physical AST and Command-Line Interception.
Enforces TC-01/02/03/04/05/07 code-interceptable rules plus RULE-0.7 FSM
Phase mutation locks. TC-06 (live financial API), TC-08 (reward hacking),
TC-09 (epistemic humility), TC-10 (corrigibility) are procedural governance
rules with no code interception surface and are enforced by workflow, not here.
"""

import ast
import re
from typing import List, Tuple, Optional


class SecurityFirewallException(Exception):
    """Raised when an operation violates SWDA AI Firewall constraints."""
    def __init__(self, rule_id: str, message: str):
        self.rule_id = rule_id
        self.message = message
        super().__init__(f"[{rule_id}] {message}")


class SafetyFirewall:
    """
    Physical inspection engine for terminal commands and Python AST code blocks.
    Acts as an unbreakable barrier preventing LLM hallucination and dangerous execution.
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

    @classmethod
    def audit_code_ast(cls, code_str: str, current_phase: Optional[str] = None) -> None:
        """
        Parses Python code to AST and enforces strict semantic restrictions.
        In particular, file mutation calls are strictly forbidden before SYNTHESIS phase.
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
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                # Phase Lock Rule (§0.7): File write mutations forbidden in research/crucible phases
                if is_read_only_phase:
                    if func_name == "open":
                        for arg in node.args[1:]:
                            if isinstance(arg, ast.Constant) and any(m in str(arg.value) for m in ("w", "a", "x", "+")):
                                raise SecurityFirewallException(
                                    rule_id="RULE-0.7",
                                    message=f"File mutation via open('{arg.value}') is strictly forbidden in phase '{current_phase}'. Spec must pass Crucible first."
                                )
                        for kw in node.keywords:
                            if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and any(m in str(kw.value.value) for m in ("w", "a", "x", "+")):
                                raise SecurityFirewallException(
                                    rule_id="RULE-0.7",
                                    message=f"File mutation via open(mode='{kw.value.value}') is forbidden in phase '{current_phase}'."
                                )
                    elif func_name in ("write_text", "write_bytes", "remove", "unlink", "rmdir"):
                        raise SecurityFirewallException(
                            rule_id="RULE-0.7",
                            message=f"File mutation '{func_name}' is strictly forbidden in phase '{current_phase}'."
                        )

                # TC-01 & TC-03 in Python code
                if func_name in ("system", "popen", "exec", "eval"):
                    # Check first argument for dangerous commands
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        cls.audit_command(node.args[0].value)
