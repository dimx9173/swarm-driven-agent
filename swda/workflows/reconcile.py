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
    def verify_file(cls, file_path: str, workspace_root: str, anchors: Any = None) -> Dict[str, Any]:
        """
        Parses the Python file at file_path and checks import validity and syntax.

        Beyond module-level checks, also verifies from-imported symbols and
        attribute accesses on imported modules, catching hallucinated APIs
        such as ``from os import hallucinated_func`` or ``json.nope()``.

        Tristate verdict (``valid`` / ``unverifiable`` / ``invalid``):
          * ``invalid`` (errors non-empty): positive evidence of hallucination.
          * ``unverifiable`` (warnings non-empty, errors empty): the symbol
            could not be grounded — unknown call receiver (``x = get(); x.y``),
            relative/star/dynamic import, import failure, or workspace
            re-export. Gate policy: zero ``invalid`` AND human-confirmed
            ``unverifiable`` before delivery.
          * ``valid``: every checked symbol grounded, nothing left unknown.

        ``anchors`` (optional hashline list [{file, line, id?}]): findings whose
        line matches an anchor cite it (``@anchor <id|file:line>``); without
        anchors the verdict is unchanged (full-file mode).
        """
        if not os.path.exists(file_path):
            return {"valid": False, "verdict": "invalid", "errors": [f"File does not exist: {file_path}"], "warnings": []}

        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            return {"valid": False, "verdict": "invalid", "errors": [f"SyntaxError: {e}"], "warnings": []}

        errors: List[str] = []
        warnings: List[str] = []
        imported_modules: Set[str] = set()
        guarded_imports: Set[str] = set()
        alias_to_module: Dict[str, str] = {}
        from_imports: List[Tuple[str, str, int]] = []
        star_imports: List[Tuple[str, int]] = []
        dynamic_loads: List[Tuple[str, int]] = []
        raw_chains: List[Tuple[int, Tuple[str, List[str], int]]] = []
        unknown_receivers: List[Tuple[str, str, int]] = []
        call_assigned: Set[str] = set()
        local_binds, local_classes, class_bases = cls._collect_local_binds(tree)

        # Optional imports guarded by try/except ImportError are warnings,
        # never errors (e.g. IPython with a stdlib fallback).
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                handlers_guard = any(
                    isinstance(h.type, ast.Name) and h.type.id == "ImportError"
                    or isinstance(h.type, ast.Tuple)
                    and any(isinstance(e, ast.Name) and e.id == "ImportError" for e in h.type.elts)
                    or h.type is None
                    for h in node.handlers
                )
                if handlers_guard:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Import):
                            for alias in sub.names:
                                guarded_imports.add(alias.name.split(".")[0])
                        elif isinstance(sub, ast.ImportFrom) and sub.module:
                            guarded_imports.add(sub.module.split(".")[0])
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
                    if node.level != 0:
                        warnings.append(
                            f"Unverifiable relative import from '{node.module}' (line {node.lineno}): symbols not checked"
                        )
                    elif any(alias.name == "*" for alias in node.names):
                        star_imports.append((node.module, node.lineno))
                    else:
                        for alias in node.names:
                            from_imports.append((node.module, alias.name, node.lineno))
                            # `from os import path` binds `path` -> `os.path`, so
                            # later `path.join` resolves instead of going unknown.
                            alias_to_module.setdefault(alias.name, f"{node.module}.{alias.name}")
                elif node.level != 0:
                    warnings.append(
                        f"Unverifiable relative import (line {node.lineno}): symbols not checked"
                    )
                elif any(alias.name == "*" for alias in node.names):
                    warnings.append(f"Unverifiable star import (line {node.lineno}): symbols not checked")
            elif isinstance(node, ast.Attribute):
                chain = cls._attribute_chain(node)
                if chain is not None:
                    raw_chains.append((id(node), chain))
            elif isinstance(node, ast.Assign):
                # Lightweight assignment tracking: `x = <call>` marks `x.y` as
                # unknown-receiver (verdict: unverifiable, never valid-clean).
                if isinstance(node.value, ast.Call):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            call_assigned.add(target.id)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in ("getattr", "__import__", "eval", "exec"):
                    if func.id == "getattr" and len(node.args) >= 2:
                        second = node.args[1]
                        if isinstance(second, ast.Constant) and isinstance(second.value, str):
                            pass  # getattr(x, "name") grounds the name literally: not dynamic
                        else:
                            dynamic_loads.append((func.id, node.lineno))
                    else:
                        dynamic_loads.append((func.id, node.lineno))
        # Keep only outermost chains: drop nodes nested inside another attribute.
        nested_ids: Set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                nested_ids.add(id(node.value))
        attr_accesses = [chain for node_id, chain in raw_chains if node_id not in nested_ids]

        # Map each attribute-use line to its enclosing class so `self`/`cls`
        # resolve against the class member table (positive evidence either way).
        self_owner: Dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id in ("self", "cls"):
                        self_owner[sub.lineno] = node.name

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
            if mod in guarded_imports:
                warnings.append(
                    f"Unverifiable optional dependency '{mod}': guarded by try/except ImportError, not checked"
                )
                continue
            try:
                spec = importlib.util.find_spec(mod)
                if spec is None:
                    errors.append(f"Unresolved / hallucinated dependency module: '{mod}'")
                    unresolved_modules.add(mod)
            except (ValueError, ModuleNotFoundError):
                errors.append(f"Unresolved / hallucinated dependency module: '{mod}'")
                unresolved_modules.add(mod)

        # Symbol-level checks: from-imported names must exist in the source module.
        # Tristate: False (hallucinated) -> errors; None (inconclusive) -> warnings.
        for module, name, lineno in from_imports:
            if module.split(".")[0] in unresolved_modules:
                continue
            outcome = cls._check_symbol(module, name, workspace_root)
            if outcome is False:
                errors.append(
                    f"Hallucinated symbol '{name}' imported from module '{module}' (line {lineno})"
                )
            elif outcome is None:
                warnings.append(
                    f"Unverifiable symbol '{name}' from module '{module}' (line {lineno}): no local or importable evidence"
                )

        for module, lineno in star_imports:
            warnings.append(
                f"Unverifiable star import from '{module}' (line {lineno}): symbols not checked"
            )

        for func, lineno in dynamic_loads:
            warnings.append(
                f"Unverifiable dynamic load via '{func}' (line {lineno}): symbols not checked"
            )

        # Symbol-level checks: dotted attribute chains rooted at a known import.
        # Unknown receivers (`x = get(); x.y`, non-Name roots) are warnings,
        # never silent passes. `self`/`cls` resolve against the enclosing class
        # (hit = silent, miss = error); KIND heuristic hits warn once per
        # receiver; each other receiver warns once no matter how often used.
        warned_receivers: Set[str] = set()
        for base, attrs, lineno in attr_accesses:
            full = alias_to_module.get(base)
            if full is None or full.split(".")[0] in unresolved_modules:
                dotted = base + "." + ".".join(attrs) if attrs else base
                if base in ("self", "cls"):
                    owner = self_owner.get(lineno)
                    if owner is not None and attrs:
                        members = local_classes.get(owner, set())
                        if attrs[0] not in members:
                            if owner in class_bases and class_bases[owner]:
                                # Explicit base classes: may be inherited,
                                # statically unknowable -> warn, never error.
                                warnings.append(
                                    f"Unverifiable method '{attrs[0]}' on '{base}' in class '{owner}' (line {lineno}): may be inherited, needs human confirmation"
                                )
                            else:
                                # No bases: only `object` methods exist, so a
                                # missing member is positive evidence.
                                errors.append(
                                    f"Hallucinated method '{attrs[0]}' on '{base}' in class '{owner}' (line {lineno})"
                                )
                    continue
                kind = local_binds.get(base)
                if kind is not None and attrs and attrs[0] in cls.KIND_METHODS.get(kind, set()):
                    if base not in warned_receivers:
                        warned_receivers.add(base)
                        warnings.append(
                            f"Unverifiable receiver '{base}' for '{dotted}' (line {lineno}): kind '{kind}' is heuristic, needs human confirmation"
                        )
                    continue
                if kind == "file" and attrs:
                    continue  # open() handle: read/write/close are local facts
                if kind is not None and kind.startswith("instance:") and attrs:
                    members = local_classes.get(kind.split(":", 1)[1], set())
                    if attrs[0] in members:
                        continue  # same-file constructor instance: method exists
                if base not in warned_receivers and (
                    base in call_assigned or base in local_binds or full is None
                ):
                    warned_receivers.add(base)
                    unknown_receivers.append((base, dotted, lineno))
                    warnings.append(
                        f"Unverifiable receiver '{base}' for '{dotted}' (line {lineno}): assignment/call result, needs human confirmation"
                    )
                continue
            current = full
            for attr in attrs:
                outcome = cls._check_symbol(current, attr, workspace_root)
                if outcome is False:
                    errors.append(f"Hallucinated API '{current}.{attr}' (line {lineno})")
                    break
                if outcome is None:
                    warnings.append(
                        f"Unverifiable API '{current}.{attr}' (line {lineno}): no evidence, needs human confirmation"
                    )
                    break
                current = f"{current}.{attr}"

        if errors:
            verdict = "invalid"
        elif warnings:
            verdict = "unverifiable"
        else:
            verdict = "valid"
        anchor_hits = cls._match_anchors(file_path, errors + warnings, anchors)
        return {
            "valid": len(errors) == 0,
            "verdict": verdict,
            "imported_modules": list(imported_modules),
            "errors": errors,
            "warnings": warnings,
            "anchor_hits": anchor_hits,
        }

    @staticmethod
    def _match_anchors(file_path: str, findings: List[str], anchors: Any) -> List[Dict[str, Any]]:
        """Matches finding lines against hashline anchors (same file only)."""
        import re as _re
        norm_target = os.path.basename(file_path)
        norm_anchors: List[Dict[str, Any]] = []
        if isinstance(anchors, list):
            for a in anchors[:32]:
                if isinstance(a, dict) and isinstance(a.get("file"), str) and a["file"]:
                    try:
                        line = int(a.get("line", 0))
                    except (TypeError, ValueError):
                        continue
                    if line > 0 and os.path.basename(a["file"]) == norm_target:
                        norm_anchors.append({"file": a["file"], "line": line, "id": a.get("id")})
        hits: List[Dict[str, Any]] = []
        for f in findings:
            m = _re.search(r"\(line (\d+)\)", f)
            if not m:
                continue
            lineno = int(m.group(1))
            for a in norm_anchors:
                if a["line"] == lineno:
                    hits.append({"line": lineno, "anchor": a.get("id") or f"{a['file']}:{lineno}",
                                 "finding": f[:160]})
                    break
        return hits
    #: Attribute allowlist per locally-inferred kind. A hit grounds the access
    #: silently; a miss stays a warning (never an error: kinds are heuristic).
    KIND_METHODS: Dict[str, Set[str]] = {
        "pattern": {"search", "match", "findall", "finditer", "split", "sub", "fullmatch"},
        "match": {"group", "groups", "groupdict", "span", "start", "end", "re"},
        "dict": {"get", "keys", "values", "items", "update", "pop", "setdefault"},
        "list": {"append", "extend", "pop", "remove", "index", "count", "sort", "reverse"},
        "str": {"split", "join", "strip", "format", "startswith", "endswith", "replace", "lower", "upper"},
        "path": {"join", "exists", "dirname", "basename", "abspath", "normpath", "splitext", "split"},
    }

    @staticmethod
    def _annotation_kind(node: Optional[ast.expr]) -> Optional[str]:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            low = node.id.lower()
            if low in ("dict", "dictionary"):
                return "dict"
            if low == "list":
                return "list"
            if low == "str":
                return "str"
            if "pattern" in low:
                return "pattern"
            if "match" in low:
                return "match"
            if "path" in low:
                return "path"
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            return ReverseReconciliation._annotation_kind(node.value)
        elif isinstance(node, ast.Attribute):
            return ReverseReconciliation._annotation_kind(ast.Name(id=node.attr))
        return None

    @classmethod
    def _collect_local_binds(cls, tree: ast.AST) -> Tuple[Dict[str, str], Dict[str, Set[str]], Dict[str, List[str]]]:
        """Infers (name -> kind, class -> members, class -> base names)."""
        binds: Dict[str, str] = {}
        classes: Dict[str, Set[str]] = {}
        bases: Dict[str, List[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = cls._class_members(node)
                bases[node.name] = [cls._base_name(b) for b in node.bases]
        def _call_kind(func: ast.expr) -> Optional[str]:
            if isinstance(func, ast.Name):
                if func.id == "open":
                    return "file"
                if func.id in classes:
                    return f"instance:{func.id}"
            if isinstance(func, ast.Attribute):
                recv = func.value
                if isinstance(recv, ast.Name) and recv.id == "re" and func.attr == "compile":
                    return "pattern"
                if isinstance(recv, ast.Name) and recv.id in binds:
                    # One-hop: pattern.match(s) -> match; dict.get(k, {}) stays dict.
                    if binds[recv.id] == "pattern" and func.attr in ("search", "match"):
                        return "match"
            return None

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in list(node.args.args) + list(node.args.kwonlyargs):
                    kind = cls._annotation_kind(arg.annotation)
                    if kind:
                        binds.setdefault(arg.arg, kind)
                kind = cls._annotation_kind(node.returns)
                if kind and node.name not in binds:
                    binds[node.name] = kind
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                kind = cls._annotation_kind(node.annotation)
                if kind:
                    binds.setdefault(node.target.id, kind)
            elif isinstance(node, ast.Assign):
                kind: Optional[str] = None
                value = node.value
                if isinstance(value, ast.Dict):
                    kind = "dict"
                elif isinstance(value, (ast.List, ast.Tuple)):
                    kind = "list"
                elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                    kind = "str"
                elif isinstance(value, ast.Call):
                    kind = _call_kind(value.func)
                if kind:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            binds.setdefault(target.id, kind)
            elif isinstance(node, ast.For):
                target = node.target
                if isinstance(target, ast.Name):
                    names = [target.id]
                elif isinstance(target, ast.Tuple):
                    names = [e.id for e in target.elts if isinstance(e, ast.Name)]
                for name in names:
                    binds.setdefault(name, "str")
        return binds, classes, bases

    @staticmethod
    def _base_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


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
        defined, _ = cls._workspace_symbols_split(file_path)
        return defined

    @staticmethod
    def _class_members(class_node: ast.ClassDef) -> Set[str]:
        """Collects method, class-attribute, and instance-attribute names."""
        members: Set[str] = set()
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                members.add(node.name)
                # Instance attributes ASSIGNED in methods (`self.x = ...`).
                # Reads (`return self.y`) never define membership.
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id in ("self", "cls") and isinstance(sub.ctx, ast.Store):
                        members.add(sub.attr)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        members.add(target.id)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                members.add(elt.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    members.add(node.target.id)
        return members

    @classmethod
    def _workspace_symbols_split(cls, file_path: str) -> Tuple[Set[str], Set[str]]:
        """Splits workspace top-level names into (locally defined, re-exported imports)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except (OSError, SyntaxError):
            return set(), set()
        defined: Set[str] = set()
        reexported: Set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
                    elif isinstance(target, (ast.Tuple, ast.List)):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                defined.add(elt.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    defined.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    reexported.add(alias.asname or alias.name.split(".")[0])
        return defined, reexported

    @classmethod
    def _local_symbol_outcome(cls, file_path: str, symbol: str) -> Optional[bool]:
        """Local evidence: True (defined) / None (re-exported, needs confirmation) / False (absent)."""
        defined, reexported = cls._workspace_symbols_split(file_path)
        if symbol in defined:
            return True
        if symbol in reexported:
            return None
        return False

    @classmethod
    def _resolve_workspace_path(cls, dotted: str, workspace_root: str) -> Optional[Tuple[str, Optional[str], Tuple[str, ...]]]:
        """Splits a dotted path into (kind, file, rest) against the workspace tree.

        ``kind`` is ``module`` (a ``x/y.py`` file won, ``rest`` = subpath below
        it) or ``package-init`` (only ``x/__init__.py`` exists, ``rest`` = path
        below the package). Returns None when the top-level name is not a
        workspace module at all (caller falls back to installed imports).
        """
        parts = dotted.split(".")
        top = parts[0]
        if cls._workspace_module_file(top, workspace_root) is None:
            return None
        # Longest file-prefix wins: swda.core.fsm > swda > swda/__init__.
        for i in range(len(parts), 0, -1):
            prefix = ".".join(parts[:i])
            target = cls._workspace_module_file(prefix, workspace_root)
            if target is not None:
                kind = "package-init" if target.endswith("__init__.py") else "module"
                return (kind, target, tuple(parts[i:]))
        parent_init = os.path.join(workspace_root, *top.split("."), "__init__.py")
        if os.path.exists(parent_init):
            return ("package-init", parent_init, tuple(parts[1:]))
        return ("module", None, tuple(parts[1:]))

    @classmethod
    def _resolve_member_chain(cls, file_path: str, chain: List[str]) -> Optional[bool]:
        """Walks ClassName.attr... inside one workspace file via AST (no import)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=file_path)
        except (OSError, SyntaxError):
            return None
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        scope: Optional[Set[str]] = set()
        node: Optional[ast.ClassDef] = None
        for depth, name in enumerate(chain):
            if depth == 0:
                if name in classes:
                    node = classes[name]
                    scope = cls._class_members(node)
                    continue
                return cls._local_symbol_outcome(file_path, name)
            assert scope is not None
            if name not in scope:
                # First segment is grounded, deeper is unknown: fail closed
                # only when the receiver is provably a non-class value.
                return False if node is None else None
            # Descend only through nested classes; plain attributes end the
            # statically knowable chain (deeper access needs confirmation).
            child = next((n for n in (node.body if node else []) if isinstance(n, ast.ClassDef) and n.name == name), None)
            if child is None:
                if depth == len(chain) - 1:
                    return True
                return None
            node, scope = child, cls._class_members(child)
        return True

    @classmethod
    def _check_symbol(cls, dotted: str, symbol: str, workspace_root: str) -> Optional[bool]:
        """Tristate: True (grounded) / False (hallucinated) / None (unverifiable)."""
        resolved = cls._resolve_workspace_path(dotted, workspace_root)
        if resolved is not None:
            kind, target, rest = resolved
            # Workspace shadows any installed namesake: only local evidence counts.
            if kind == "module" and target is not None:
                if not rest:
                    return cls._local_symbol_outcome(target, symbol)
                return cls._resolve_member_chain(target, list(rest) + [symbol])
            if kind == "package-init" and target is not None:
                if not rest:
                    return cls._local_symbol_outcome(target, symbol)
                first, tail = rest[0], list(rest[1:]) + [symbol]
                pkg_dir = os.path.dirname(target)
                member_py = os.path.join(pkg_dir, first + ".py")
                member_pkg = os.path.join(pkg_dir, first)
                if os.path.exists(member_py):
                    return cls._resolve_member_chain(member_py, tail)
                if os.path.isdir(member_pkg):
                    init = os.path.join(member_pkg, "__init__.py")
                    if os.path.exists(init):
                        return cls._resolve_member_chain(init, tail)
                return cls._local_symbol_outcome(target, first)
            return None  # inconclusive: needs human confirmation
        try:
            module = importlib.import_module(dotted)
        except Exception:
            module = None
        if module is None:
            # Dotted prefix is not itself a module (e.g. `sys.modules` from a
            # `sys.modules.keys()` chain): resolve progressively from the top
            # so container attrs ground instead of warning.
            try:
                parts = dotted.split(".")
                obj: Any = importlib.import_module(parts[0])
                for part in parts[1:]:
                    obj = obj[part] if isinstance(obj, dict) else getattr(obj, part)
                module = obj
            except Exception:
                return None  # inconclusive: never flag on import failure
        if hasattr(module, symbol):
            return True
        # Submodule case, e.g. ``importlib.util`` used as ``importlib.util``.
        try:
            importlib.import_module(f"{dotted}.{symbol}")
            return True
        except Exception:
            return False
