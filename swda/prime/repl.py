"""
SWDA Prime REPL: Persistent Stateful Execution Runtime.
Provides a long-lived Python/IPython environment where context is treated as variables
and sub-agents as function calls, guarded by SWDA AI Firewall hooks.
"""

import sys
import io
import ast
import traceback
from typing import Any, Dict, Optional
from swda.core.blackboard import Blackboard
from swda.core.firewall import SafetyFirewall, SecurityFirewallException

try:
    from IPython.core.interactiveshell import InteractiveShell
    HAS_IPYTHON = True
except ImportError:
    import code
    HAS_IPYTHON = False


class PrimeREPL:
    """
    Persistent stateful execution environment with SWDA safety hooks.
    Retains namespace and variable state across multi-turn interactions.
    """

    def __init__(self, blackboard: Blackboard, initial_namespace: Optional[Dict[str, Any]] = None):
        self.blackboard = blackboard
        self.namespace: Dict[str, Any] = {
            "blackboard": self.blackboard,
            "__name__": "__main__",
        }
        if initial_namespace:
            self.namespace.update(initial_namespace)

        if HAS_IPYTHON:
            self.shell = InteractiveShell.instance()
            self.shell.user_ns.update(self.namespace)
        else:
            self.interpreter = code.InteractiveInterpreter(self.namespace)

    def execute(self, code_str: str) -> Dict[str, Any]:
        """
        Executes Python code inside the persistent environment after AST firewall verification.
        Returns a dictionary with 'stdout', 'stderr', 'result', and 'success'.
        """
        current_phase = self.blackboard.read("phase")
        
        # 1. Physical AST and Security Audit
        SafetyFirewall.audit_code_ast(code_str, current_phase)

        # 2. Redirect standard streams for capture
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_stdout = io.StringIO()
        redirected_stderr = io.StringIO()

        sys.stdout = redirected_stdout
        sys.stderr = redirected_stderr

        result_val = None
        success = True
        error_msg = None

        try:
            if HAS_IPYTHON:
                # Sync namespace
                self.shell.user_ns["blackboard"] = self.blackboard
                exec_res = self.shell.run_cell(code_str)
                if exec_res.error_in_exec:
                    success = False
                    error_msg = str(exec_res.error_in_exec)
                else:
                    result_val = exec_res.result
            else:
                # Fallback to standard Python exec with persistent locals
                tree = ast.parse(code_str)
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    last_expr = tree.body.pop()
                    if tree.body:
                        stmt_mod = ast.Module(body=tree.body, type_ignores=[])
                        exec(compile(stmt_mod, "<repl>", "exec"), self.namespace)
                    expr_mod = ast.Expression(body=last_expr.value)
                    result_val = eval(compile(expr_mod, "<repl>", "eval"), self.namespace)
                else:
                    exec(compile(tree, "<repl>", "exec"), self.namespace)
                    result_val = None
        except Exception as e:
            success = False
            error_msg = traceback.format_exc()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return {
            "success": success,
            "stdout": redirected_stdout.getvalue(),
            "stderr": redirected_stderr.getvalue(),
            "result": result_val,
            "error": error_msg,
        }

    def set_variable(self, name: str, value: Any) -> None:
        """Injects a variable directly into the persistent REPL environment."""
        self.namespace[name] = value
        if HAS_IPYTHON:
            self.shell.user_ns[name] = value

    def get_variable(self, name: str) -> Any:
        """Retrieves a variable from the persistent REPL environment."""
        if HAS_IPYTHON:
            return self.shell.user_ns.get(name)
        return self.namespace.get(name)
