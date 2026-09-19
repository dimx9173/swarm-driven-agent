"""
SWDA Continual Harness: versioned supplemental-state store, primed with the
prime-agent harness contract.

Design (prime-agent `prime-agent-runtime/src/rlm/harness.py`, adapted in-process):
  * kinds: prompt | memory | skill | subagent (each versioned, small-step edits)
  * refinements recorded as {trigger, changes, evidence, outcome}; snapshots
    support rollback; the base system prompt is never touched.
  * local (workspace) vs global (~/.swda/harness) scoping; loads re-read the
    on-disk mtime so external writers are not clobbered.
  * `refine()` keeps the legacy anti-pattern YAML behaviour (Crucible/TDD
    failures) while also recording a refinement event in the store.
"""
import os
import copy
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

KINDS = ("prompt", "memory", "skill", "subagent")

_ENTRY_FIELDS = {"id", "kind", "title", "content", "path", "scope",
                 "reference", "arguments", "metadata", "source",
                 "created_at", "updated_at", "version"}
_REFINEMENT_FIELDS = {"id", "trigger", "changes", "evidence", "outcome", "created_at"}


def _now() -> str:
    return datetime.now().isoformat()


def _slug(raw: str, fallback: str) -> str:
    out = "".join(c if c.isalnum() or c in "-_" else "-" for c in (raw or "").strip().lower())
    out = out.strip("-")
    return out or fallback


class HarnessState:
    """CRUD store for reset-free harness refinement state (stdlib only)."""

    def __init__(self, state_path: Optional[str] = None, scope: str = "local",
                 in_memory: bool = False):
        self.scope = scope
        if in_memory or state_path is None:
            self.state_path: Optional[str] = None
        else:
            self.state_path = os.path.abspath(os.path.expanduser(state_path))
        self.entries: Dict[str, Dict[str, Dict[str, Any]]] = {k: {} for k in KINDS}
        self.refinements: List[Dict[str, Any]] = []
        self._loaded_mtime: Optional[int] = None
        if self.state_path:
            self.load()

    # -- disk sync ---------------------------------------------------------
    def _disk_mtime(self) -> Optional[int]:
        if not self.state_path or not os.path.exists(self.state_path):
            return None
        return int(os.stat(self.state_path).st_mtime)

    @staticmethod
    def _default_path(scope: str) -> Optional[str]:
        if scope == "global":
            home = os.path.expanduser("~")
            return os.path.join(home, ".swda", "harness", "harness_state.json")
        if scope == "local":
            return os.path.join(os.getcwd(), ".swda", "harness", "harness_state.json")
        return None

    def load(self) -> "HarnessState":
        if not self.state_path:
            return self
        mtime = self._disk_mtime()
        if mtime is not None and mtime == self._loaded_mtime:
            return self  # on-disk unchanged since last load
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._hydrate(data)
            self._loaded_mtime = mtime
        except OSError:
            pass  # first run: nothing on disk yet
        except ValueError:
            # corrupt store: keep memory, do not silently clobber disk
            self._loaded_mtime = None
        return self

    def load_locked(self) -> "HarnessState":
        """Reloads from disk without the mtime shortcut (call under lock)."""
        if not self.state_path:
            return self
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._hydrate(data)
                self._loaded_mtime = self._disk_mtime()
        except (OSError, ValueError):
            pass
        return self

    def _hydrate(self, data: Dict[str, Any]) -> None:
        self.entries = {k: {} for k in KINDS}
        for kind, rows in (data.get("entries") or {}).items():
            if kind in KINDS and isinstance(rows, dict):
                self.entries[kind] = rows
        self.refinements = [r for r in (data.get("refinements") or [])
                            if isinstance(r, dict) and _REFINEMENT_FIELDS & set(r)]

    def save(self) -> "HarnessState":
        if not self.state_path:
            return self
        from swda.core.flock import locked
        parent = os.path.dirname(self.state_path)
        os.makedirs(parent, exist_ok=True)
        with locked(self.state_path):
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"entries": self.entries, "refinements": self.refinements},
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_path)
            self._loaded_mtime = self._disk_mtime()
        return self

    def _mutate(self):
        """Holds the store file lock and reloads (callers modify then save)."""
        from swda.core.flock import locked
        import contextlib

        @contextlib.contextmanager
        def _h():
            if not self.state_path:
                yield
                return
            parent = os.path.dirname(self.state_path)
            os.makedirs(parent, exist_ok=True)
            with locked(self.state_path):
                self.load_locked()
                yield
        return _h()

    # -- CRUD ---------------------------------------------------------------
    def _entry(self, kind: str, id_: str, title: str, content: str, **extra: Any) -> Dict[str, Any]:
        e = {k: None for k in _ENTRY_FIELDS}
        e.update({"id": id_, "kind": kind, "title": title, "content": content,
                  "path": "general", "scope": self.scope, "reference": {},
                  "arguments": {}, "metadata": {}, "source": "agent",
                  "created_at": _now(), "updated_at": _now(), "version": 1})
        for k, v in extra.items():
            if k in _ENTRY_FIELDS and v is not None:
                e[k] = v
        return e

    def upsert(self, kind: str, id_: str, title: str, content: str, **extra: Any) -> Dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"Unknown harness kind: {kind!r} (want one of {KINDS})")
        with self._mutate():
            existing = self.entries[kind].get(id_)
            if existing:
                updated = {**existing, **{k: v for k, v in {
                    "title": title, "content": content, **extra}.items() if v is not None}}
                updated["version"] = int(existing.get("version", 1)) + 1
                updated["updated_at"] = _now()
                self.entries[kind][id_] = updated
                entry = updated
            else:
                entry = self._entry(kind, id_, title, content, **extra)
                self.entries[kind][id_] = entry
            self.save()
            return copy.deepcopy(entry)

    def get(self, kind: str, id_: str) -> Optional[Dict[str, Any]]:
        self.load()
        row = self.entries.get(kind, {}).get(id_)
        return copy.deepcopy(row) if row else None

    def delete(self, kind: str, id_: str) -> bool:
        with self._mutate():
            if id_ in self.entries.get(kind, {}):
                del self.entries[kind][id_]
                self.save()
                return True
            return False

    def list(self, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        self.load()
        kinds = [kind] if kind else list(KINDS)
        out: List[Dict[str, Any]] = []
        for k in kinds:
            out.extend(copy.deepcopy(v) for v in self.entries.get(k, {}).values())
        return out
    # -- refinements ---------------------------------------------------------
    def record_refinement(self, trigger: str, changes: List[str],
                          evidence: str = "", outcome: str = "") -> Dict[str, Any]:
        with self._mutate():
            event = {"id": uuid4_hex12(), "trigger": trigger, "changes": list(changes),
                     "evidence": evidence[:300], "outcome": outcome,
                     "created_at": _now()}
            for k in list(event):
                if k not in _REFINEMENT_FIELDS:
                    del event[k]
            self.refinements.append(event)
            self.save()
            return copy.deepcopy(event)

    def snapshot(self) -> Dict[str, Any]:
        return {"entries": copy.deepcopy(self.entries),
                "refinements": copy.deepcopy(self.refinements)}

    def restore(self, snapshot: Dict[str, Any]) -> None:
        with self._mutate():
            self._hydrate(snapshot)
            self.save()

def uuid4_hex12() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


class ScopedHarness:
    """Dual-layer view: workspace-local store overlaid on the global store.

    Read rule: local wins on (kind, id) collision; both layers merge.
    Write rule: default target is local; pass ``scope="global"`` to share
    across workspaces. Delete removes from the named layer only.
    """

    def __init__(self, local: HarnessState, global_: Optional[HarnessState] = None):
        self.local = local
        self.global_ = global_ if global_ is not None else HarnessState(in_memory=True)

    def _target(self, scope: str) -> HarnessState:
        if scope == "global":
            return self.global_
        return self.local

    def upsert(self, kind: str, id_: str, title: str, content: str,
               scope: str = "local", **extra: Any) -> Dict[str, Any]:
        if scope not in ("local", "global"):
            raise ValueError(f"Unknown scope: {scope!r} (want 'local' or 'global')")
        return self._target(scope).upsert(kind, id_, title, content,
                                          scope=scope, **extra)

    def get(self, kind: str, id_: str) -> Optional[Dict[str, Any]]:
        hit = self.local.get(kind, id_)
        return hit if hit is not None else self.global_.get(kind, id_)

    def delete(self, kind: str, id_: str, scope: str = "local") -> bool:
        return self._target(scope).delete(kind, id_)

    def list(self, kind: Optional[str] = None, scope: str = "both") -> List[Dict[str, Any]]:
        if scope == "local":
            return self.local.list(kind)
        if scope == "global":
            return self.global_.list(kind)
        merged: Dict[str, Dict[str, Any]] = {}
        for row in self.global_.list(kind):
            merged[f"{row.get('kind')}:{row.get('id')}"] = row
        for row in self.local.list(kind):
            merged[f"{row.get('kind')}:{row.get('id')}"] = row
        return list(merged.values())

    def record_refinement(self, trigger: str, changes: List[str],
                          evidence: str = "", outcome: str = "",
                          scope: str = "local") -> Dict[str, Any]:
        return self._target(scope).record_refinement(trigger, changes, evidence, outcome)

class ContinualHarness:
    """
    Maintains durable harness state across sessions (versioned supplemental
    store) and the legacy anti-pattern YAML flow used by Crucible/TDD refine.
    """

    def __init__(self, workspace_root: Optional[str] = None,
                 state_path: Optional[str] = None, scope: str = "local",
                 global_path: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self.anti_patterns_dir = os.path.join(self.workspace_root, "docs", "anti-patterns")
        os.makedirs(self.anti_patterns_dir, exist_ok=True)
        if state_path is None:
            state_path = os.path.join(self.workspace_root, ".swda", "harness", "harness_state.json")
        elif os.path.isdir(state_path):
            state_path = os.path.join(state_path, "harness_state.json")
        self.state = HarnessState(state_path=state_path, scope=scope)
        if global_path is None:
            global_path = HarnessState._default_path("global")
        self.scoped = ScopedHarness(
            local=self.state,
            global_=HarnessState(state_path=global_path, scope="global"),
        )

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

    # Keyword-driven rule derivation: map failure evidence to a concrete guard.
    # First match wins; unknown signals fall back to the surgical-AST default.
    RULE_DERIVATIONS: tuple = (
        (("leak", "pool", "connection", "timeout", "resource"), "Enforce resource lifecycle guards: pool timeouts, explicit release, and soak verification before merge."),
        (("hallucinat", "phantom", "unresolved", "no such", "undefined"), "Run reverse reconciliation on the diff and ground every new symbol in workspace AST before commit."),
        (("race", "deadlock", "concurrent", "thread"), "Serialize shared-state access and add a deterministic concurrency regression test."),
        (("permission", "rbac", "unauthorized", "forbidden"), "Recheck Blackboard WRITE_PERMISSIONS for the failing role before widening access."),
        (("test failed", "assertion", "red state", "tdd"), "Keep the failing test untouched; shrink the fix to minimal production code until green."),
    )

    @classmethod
    def derive_rule(cls, trajectory_summary: str, failure_signal: str) -> str:
        """Derives a corrective rule from failure evidence; never returns a blank rule."""
        evidence = f"{trajectory_summary}\n{failure_signal}".lower()
        for keywords, rule in cls.RULE_DERIVATIONS:
            if any(k in evidence for k in keywords):
                return rule
        return "Prioritize surgical AST verification before modifying dependent call sites."

    def refine(self, trajectory_summary: str, failure_signal: str) -> Optional[Dict[str, str]]:
        """
        Reviews a failed trajectory: anti-pattern YAML (legacy) plus a small,
        evidence-backed entry in the supplemental store with a refinement log.
        """
        pattern_name = f"refine_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = self.record_anti_pattern(
            name=pattern_name,
            trigger_vector=trajectory_summary[:300],
            failure_reason=failure_signal[:300],
            corrective_rule=self.derive_rule(trajectory_summary, failure_signal),
            tags=["auto-refine", "crucible-failure"]
        )
        self.state.upsert(
            kind="memory", id_=pattern_name, title=pattern_name[:60],
            content=f"{trajectory_summary[:200]} -> {failure_signal[:200]}",
            metadata={"path": path, "tags": ["auto-refine", "crucible-failure"]},
        )
        self.state.record_refinement(
            trigger="crucible-failure", changes=[f"memory:{pattern_name} +created"],
            evidence=f"{trajectory_summary[:200]} | {failure_signal[:200]}",
            outcome="auto-refine recorded",
        )
        return {"name": pattern_name, "path": path}

    def list_anti_patterns(self) -> List[Dict[str, Any]]:
        """Lists all registered anti-patterns in the workspace."""
        import glob as _glob
        patterns = []
        for file in _glob.glob(os.path.join(self.anti_patterns_dir, "*.yaml")):
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
