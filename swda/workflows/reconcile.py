"""
SWDA Reverse Data Reconciliation: AST Symbol Verification at Delivery Gate.
Checks that all symbols, imports, and method invocations in agent-generated diffs
physically exist in the target codebase, stopping hallucinated APIs before commit.
"""

import ast
import importlib
import importlib.util
import os
import sys
from typing import Dict, Any, List, Optional, Set, Tuple


class ReverseReconciliation:
    """
    Examines generated code against the workspace AST to ensure no phantom/hallucinated
    dependencies or functions were invented by the model.
    """

    @classmethod
    def verify_file(cls, file_path: str, workspace_root: str) -> Dict[str, Any]:
        """
        Parses the Python file at file_path and checks import validity and syntax.

        Beyond module-level checks, also verifies from-imported symbols and
        attribute accesses on imported modules, catching hallucinated APIs
        such as ``from os import hallucinated_func`` or ``json.nope()``.
        Checks are conservative: anything inconclusive (unimportable module,
        relative import, star import) is never flagged.
        """
        if not os.path.exists(file_path):
            return {"valid": False, "errors": [f"File does not exist: {file_path}"]}

        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            return {"valid": False, "errors": [f"SyntaxError: {e}"]}

        errors: List[str] = []
        imported_modules: Set[str] = set()
        alias_to_module: Dict[str, str] = {}
        from_imports: List[Tuple[str, str, int]] = []
        raw_chains: List[Tuple[int, Tuple[str, List[str], int]]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    imported_modules.add(top)
                    # `import a.b` binds top-level `a`; only `as` binds the full path.
                    alias_to_module[alias.asname or top] = alias.name if alias.asname else top
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split(".")[0])
                    if node.level == 0:
                        for alias in node.names:
                            if alias.name != "*":
                                from_imports.append((node.module, alias.name, node.lineno))
            elif isinstance(node, ast.Attribute):
                chain = cls._attribute_chain(node)
                if chain is not None:
                    raw_chains.append((id(node), chain))

        # Keep only outermost chains: drop nodes nested inside another attribute.
        nested_ids: Set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                nested_ids.add(id(node.value))
        attr_accesses = [chain for node_id, chain in raw_chains if node_id not in nested_ids]

        # Check if imported modules exist in stdlib, site-packages, or workspace
        builtin_and_installed = set(sys.builtin_module_names) | set(sys.modules.keys())
        unresolved_modules: Set[str] = set()
        for mod in imported_modules:
            if mod in builtin_and_installed:
                continue

            # Check local file or directory
            local_py = os.path.join(workspace_root, f"{mod}.py")
            local_pkg = os.path.join(workspace_root, mod)
            if os.path.exists(local_py) or os.path.isdir(local_pkg):
                continue
            try:
                spec = importlib.util.find_spec(mod)
                if spec is None:
                    errors.append(f"Unresolved / hallucinated dependency module: '{mod}'")
                    unresolved_modules.add(mod)
            except (ValueError, ModuleNotFoundError):
                errors.append(f"Unresolved / hallucinated dependency module: '{mod}'")
                unresolved_modules.add(mod)

        # Symbol-level checks: from-imported names must exist in the source module
        for module, name, lineno in from_imports:
            if module.split(".")[0] in unresolved_modules:
                continue
            if not cls._module_has_symbol(module, name, workspace_root):
                errors.append(
                    f"Hallucinated symbol '{name}' imported from module '{module}' (line {lineno})"
                )

        # Symbol-level checks: dotted attribute chains rooted at a known import
        for base, attrs, lineno in attr_accesses:
            full = alias_to_module.get(base)
            if full is None or full.split(".")[0] in unresolved_modules:
                continue
            current = full
            for attr in attrs:
                if not cls._module_has_symbol(current, attr, workspace_root):
                    errors.append(f"Hallucinated API '{current}.{attr}' (line {lineno})")
                    break
                current = f"{current}.{attr}"

        return {
            "valid": len(errors) == 0,
            "imported_modules": list(imported_modules),
            "errors": errors,
        }

    @staticmethod
    def _attribute_chain(node: ast.Attribute) -> Optional[Tuple[str, List[str], int]]:
        """Flattens a.b.c into (a, [b, c], lineno); None when not rooted at a Name."""
        parts: List[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.reverse()
        return (current.id, parts, node.lineno)

    @staticmethod
    def _workspace_module_file(dotted: str, workspace_root: str) -> Optional[str]:
        """Maps a dotted module name to a workspace .py file, if present."""
        rel = os.path.join(*dotted.split("."))
        candidate = os.path.join(workspace_root, rel + ".py")
        if os.path.exists(candidate):
            return candidate
        pkg_init = os.path.join(workspace_root, rel, "__init__.py")
        if os.path.exists(pkg_init):
            return pkg_init
        return None

    @classmethod
    def _workspace_symbols(cls, file_path: str) -> Set[str]:
        """Collects top-level definable names from a workspace file without importing it."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except (OSError, SyntaxError):
            return set()
        names: Set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                names.add(elt.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
        return names

    @classmethod
    def _module_has_symbol(cls, dotted: str, symbol: str, workspace_root: str) -> bool:
        """Returns True when the symbol plausibly exists; False only on positive evidence."""
        top = dotted.split(".")[0]
        if cls._workspace_module_file(top, workspace_root) is not None:
            # Workspace shadows any installed namesake: only local evidence counts.
            target = cls._workspace_module_file(dotted, workspace_root)
            if target is not None:
                if target.endswith("__init__.py"):
                    pkg_dir = os.path.dirname(target)
                    member_py = os.path.join(pkg_dir, symbol + ".py")
                    member_pkg = os.path.join(pkg_dir, symbol)
                    if os.path.exists(member_py) or os.path.isdir(member_pkg):
                        return True
                return symbol in cls._workspace_symbols(target)
            # e.g. ``from pkg import name`` where name lives in pkg/__init__.py
            parent_init = os.path.join(workspace_root, *top.split("."), "__init__.py")
            if os.path.exists(parent_init):
                return symbol in cls._workspace_symbols(parent_init)
            return True  # inconclusive: never flag
        try:
            module = importlib.import_module(dotted)
        except Exception:
            return True  # inconclusive: never flag on import failure
        if hasattr(module, symbol):
            return True
        # Submodule case, e.g. ``importlib.util`` used as ``importlib.util``.
        try:
            importlib.import_module(f"{dotted}.{symbol}")
            return True
        except Exception:
            return False
