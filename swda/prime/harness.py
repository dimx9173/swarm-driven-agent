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
import re
import copy
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

KINDS = ("prompt", "memory", "skill", "subagent", "script", "hook")

# Harness² component cost hierarchy: cheapest runtime context impact first,
# always-on prose ("memory", "prompt") last.
COMPONENT_COST_ORDER = ("script", "hook", "skill", "subagent", "memory", "prompt")

_GRADER_LEAK_PATTERNS = (
    "the grader expects",
    "what the grader wants",
    "grading rubric",
    "answer key",
)


def has_experience(experience: Optional[Dict[str, Any]]) -> bool:
    """Harness² experience contract: cue, lesson, and evidence must all be non-empty strings."""
    return isinstance(experience, dict) and all(
        isinstance(experience.get(k), str) and experience[k].strip()
        for k in ("cue", "lesson", "evidence")
    )


def normalize_rel(rel: str) -> str:
    """Normalizes a harness-relative path, rejecting empty, absolute, drive-prefixed, or '..' escapes."""
    r = str(rel or "").strip().replace("\\", "/")
    if not r or r.startswith("/") or re.match(r"^[a-zA-Z]:", r):
        raise ValueError(f"path escapes the harness: {rel!r}")
    parts = [p for p in r.split("/") if p and p != "."]
    if not parts or ".." in parts:
        raise ValueError(f"path escapes the harness: {rel!r}")
    return "/".join(parts)


def _yaml_block(text: str) -> str:
    """Indents every line of a block scalar by two spaces for safe multi-line YAML."""
    cleaned = (text or "").strip()
    return "\n".join(f"  {line}" for line in cleaned.splitlines()) if cleaned else "  "

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
        *,
        domain: str = "general",
        target_kind: str = "memory",
        cue: Optional[str] = None,
        lesson: Optional[str] = None,
        evidence: Optional[str] = None,
    ) -> str:
        """
        Extracts a failure pattern from Crucible or TDD test runs, validates the
        Harness² (cue, lesson, evidence) experience triple, persists it as a YAML
        file, and rebuilds the lightweight domain INDEX.md.
        """
        exp = {
            "cue": (cue if cue is not None else trigger_vector).strip(),
            "lesson": (lesson if lesson is not None else corrective_rule).strip(),
            "evidence": (evidence if evidence is not None else failure_reason).strip(),
        }
        if not has_experience(exp):
            raise ValueError("Harness² experience requires non-empty cue, lesson, and evidence")
        low_blob = f"{exp['cue']}\n{exp['lesson']}\n{exp['evidence']}".lower()
        for leak in _GRADER_LEAK_PATTERNS:
            if leak in low_blob:
                raise ValueError(f"Answer-free violation: experience contains grader leak {leak!r}")

        base_slug = _slug(name, "pattern")
        filename = f"{base_slug}.yaml"
        target_path = os.path.join(self.anti_patterns_dir, filename)
        dom = _slug(domain, "general")
        kind_val = target_kind if target_kind in KINDS else "memory"

        content = (
            f"# SWDA Continual Harness Anti-Pattern\n"
            f"name: {json.dumps(str(name), ensure_ascii=False)}\n"
            f"domain: \"{dom}\"\n"
            f"target_kind: \"{kind_val}\"\n"
            f"recorded_at: \"{datetime.now().isoformat()}\"\n"
            f"tags: {json.dumps(list(tags or []), ensure_ascii=False)}\n"
            f"cue: |\n{_yaml_block(exp['cue'])}\n"
            f"lesson: |\n{_yaml_block(exp['lesson'])}\n"
            f"evidence: |\n{_yaml_block(exp['evidence'])}\n"
            f"trigger_vector: |\n{_yaml_block(trigger_vector)}\n"
            f"failure_reason: |\n{_yaml_block(failure_reason)}\n"
            f"corrective_rule: |\n{_yaml_block(corrective_rule)}\n"
        )

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        self.rebuild_index()
        return target_path

    # Keyword-driven rule & cheapest-lever derivation (Harness² cost hierarchy):
    # (keywords, target_kind, rule)
    LEVER_DERIVATIONS: tuple = (
        (("hallucinat", "phantom", "unresolved", "no such", "undefined"),
         "hook",
         "Run reverse reconciliation on the diff and ground every new symbol in workspace AST before commit."),
        (("format", "schema", "csv", "json", "yaml", "regex", "parse", "calculate"),
         "script",
         "Extract deterministic validation or calculation into a standalone scripts/<name>.py helper."),
        (("leak", "pool", "connection", "timeout", "resource"),
         "skill",
         "Enforce resource lifecycle guards: pool timeouts, explicit release, and soak verification before merge."),
        (("race", "deadlock", "concurrent", "thread"),
         "skill",
         "Serialize shared-state access and add a deterministic concurrency regression test."),
        (("permission", "rbac", "unauthorized", "forbidden"),
         "hook",
         "Recheck Blackboard WRITE_PERMISSIONS for the failing role before widening access."),
        (("large log", "context overflow", "trace timeout", "oversized"),
         "subagent",
         "Delegate bounded high-input/small-answer investigation to an isolated subagent."),
        (("test failed", "assertion", "red state", "tdd"),
         "memory",
         "Keep the failing test untouched; shrink the fix to minimal production code until green."),
    )

    RULE_DERIVATIONS: tuple = tuple((kw, rule) for kw, _kind, rule in LEVER_DERIVATIONS)

    @staticmethod
    def _matches_keyword(text_low: str, kw: str) -> bool:
        """Matches keyword at word/prefix boundary so 'format'/'parse' never hit 'information'/'sparse'."""
        if " " in kw:
            return kw in text_low
        if kw in ("csv", "json", "yaml", "rbac", "tdd", "pool", "race", "parse", "format"):
            return bool(re.search(rf"\b{re.escape(kw)}\b", text_low))
        return bool(re.search(rf"\b{re.escape(kw)}", text_low))

    @classmethod
    def select_cheapest_lever(cls, trajectory_summary: str, failure_signal: str) -> Tuple[str, str]:
        """Selects (target_kind, corrective_rule) preferring cheap on-demand/loop levers over prose."""
        raw = f"{trajectory_summary}\n{failure_signal}".strip()
        low = raw.lower()
        if not raw or low in ("keep_base", "none", "ok"):
            return "keep_base", "KEEP_BASE: evidence does not argue for any harness change."
        for keywords, kind, rule in cls.LEVER_DERIVATIONS:
            if any(cls._matches_keyword(low, k) for k in keywords):
                return kind, rule
        return "script", "Prioritize surgical AST verification before modifying dependent call sites."

    @classmethod
    def derive_rule(cls, trajectory_summary: str, failure_signal: str) -> str:
        """Derives a corrective rule from failure evidence; never returns a blank rule."""
        _kind, rule = cls.select_cheapest_lever(trajectory_summary, failure_signal)
        return rule

    def refine(self, trajectory_summary: str, failure_signal: str,
               domain: str = "general") -> Optional[Dict[str, str]]:
        """
        Reviews a failed trajectory: routes to the cheapest Harness² component lever,
        persists the (cue, lesson, evidence) YAML + INDEX.md, and records a refinement event.
        Returns KEEP_BASE without disk bloat when evidence argues for no change.
        """
        target_kind, rule = self.select_cheapest_lever(trajectory_summary, failure_signal)
        if target_kind == "keep_base":
            return {"name": "KEEP_BASE", "path": "", "target_kind": "keep_base"}
        pattern_name = f"refine_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if os.path.exists(os.path.join(self.anti_patterns_dir, f"{_slug(pattern_name, 'pattern')}.yaml")):
            pattern_name = f"{pattern_name}_{uuid4_hex12()[:6]}"
        path = self.record_anti_pattern(
            name=pattern_name,
            trigger_vector=trajectory_summary[:300],
            failure_reason=failure_signal[:300],
            corrective_rule=rule,
            tags=["auto-refine", "crucible-failure", f"lever:{target_kind}"],
            domain=domain,
            target_kind=target_kind,
        )
        self.state.upsert(
            kind=target_kind, id_=pattern_name, title=pattern_name[:60],
            content=f"{trajectory_summary[:200]} -> {failure_signal[:200]}",
            path=_slug(domain, "general"),
            metadata={"path": path, "domain": domain, "target_kind": target_kind,
                      "cue": trajectory_summary[:160], "lesson": rule,
                      "tags": ["auto-refine", "crucible-failure"]},
        )
        self.state.record_refinement(
            trigger="crucible-failure", changes=[f"{target_kind}:{pattern_name} +created"],
            evidence=f"{trajectory_summary[:200]} | {failure_signal[:200]}",
            outcome=f"auto-refine routed to {target_kind}",
        )
        return {"name": pattern_name, "path": path, "target_kind": target_kind}

    def list_anti_patterns(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all registered anti-patterns in the workspace, optionally filtered by domain."""
        import glob as _glob
        patterns = []
        want_dom = _slug(domain, "") if domain else ""
        for file in sorted(_glob.glob(os.path.join(self.anti_patterns_dir, "*.yaml"))):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    meta: Dict[str, Any] = {"domain": "general", "target_kind": "memory", "cue": ""}
                    for idx, line in enumerate(lines):
                        if line.startswith("name:"):
                            raw_name = line.split(":", 1)[1].strip()
                            try:
                                meta["name"] = str(json.loads(raw_name))
                            except Exception:
                                meta["name"] = raw_name.strip('"\'')
                        elif line.startswith("domain:"):
                            meta["domain"] = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith("target_kind:"):
                            meta["target_kind"] = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith("recorded_at:"):
                            meta["recorded_at"] = line.split(":", 1)[1].strip().strip('"\'')
                        elif line.startswith(("cue:", "trigger_vector:")) and not meta["cue"]:
                            block: List[str] = []
                            j = idx + 1
                            while j < len(lines) and lines[j].startswith("  "):
                                block.append(lines[j][2:].rstrip("\r\n"))
                                j += 1
                            if block:
                                meta["cue"] = " ".join(s.strip() for s in block if s.strip())
                    meta["file"] = os.path.basename(file)
                    if want_dom and meta.get("domain") != want_dom:
                        continue
                    patterns.append(meta)
            except Exception:
                continue
        return patterns

    def rebuild_index(self) -> str:
        """Rebuilds the lightweight INDEX.md table of trigger cues for on-demand loading."""
        # ponytail: full-file rewrite capped at 200 entries; upgrade to incremental index if N > 200
        index_path = os.path.join(self.anti_patterns_dir, "INDEX.md")
        patterns = self.list_anti_patterns()[-200:]
        rows = [
            "# SWDA Experience Library Index (Harness² On-Demand Cues)",
            "",
            "| Pattern | Domain | Lever | Trigger Cue | File |",
            "|---|---|---|---|---|",
        ]
        for p in patterns:
            cue = (p.get("cue") or "").replace("|", "/").replace("\n", " ")[:120]
            rows.append(
                f"| `{p.get('name', '')}` | `{p.get('domain', 'general')}` | "
                f"`{p.get('target_kind', 'memory')}` | {cue} | `{p.get('file', '')}` |"
            )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        return index_path

    def format_focal_context(self, max_items: int = 5, domain: Optional[str] = None) -> str:
        """
        Formats top anti-pattern cues for Arachne focal positioning (on-demand index pointer).
        """
        patterns = self.list_anti_patterns(domain=domain)[:max_items]
        if not patterns:
            return ""

        formatted = ["<ANCHORED_ANTI_PATTERNS>"]
        for p in patterns:
            cue_part = f" | Cue: {p['cue'][:80]}" if p.get("cue") else ""
            formatted.append(
                f"  - Pattern: {p.get('name')} [Lever: {p.get('target_kind', 'memory')}] "
                f"(File: {p.get('file')}{cue_part})"
            )
        formatted.append("</ANCHORED_ANTI_PATTERNS>")
        return "\n".join(formatted)

    @staticmethod
    def validate_surface(workspace_root: str, always_on_text: str = "") -> Dict[str, Any]:
        """
        Validates Harness²'s 3 surface rules across a workspace:
          1. Every skill under skills/<name>/SKILL.md or .agents/skills/<name>/SKILL.md
             must have a description frontmatter and (when always_on_text is supplied)
             a verbatim trigger reference in always_on_text.
          2. Every script referenced as `scripts/<name>.py` in always_on_text must exist.
          3. No grader-verdict / rubric leak phrases appear in always_on_text.
        """
        errors: List[str] = []
        skills_found: List[str] = []
        low_text = (always_on_text or "").lower()
        for leak in _GRADER_LEAK_PATTERNS:
            if leak in low_text:
                errors.append(f"grader-leak: forbidden phrase {leak!r} in always-on text")

        real_root = os.path.realpath(workspace_root)
        for rel_dir in ("skills", os.path.join(".agents", "skills")):
            base = os.path.join(workspace_root, rel_dir)
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base)):
                skill_md = os.path.join(base, entry, "SKILL.md")
                if not os.path.isfile(skill_md):
                    continue
                real_skill = os.path.realpath(skill_md)
                if real_skill != real_root and not real_skill.startswith(real_root + os.sep):
                    errors.append(f"skill-escape: {entry}/SKILL.md resolves outside workspace")
                    continue
                skills_found.append(entry)
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        body = f.read()
                except OSError as exc:
                    errors.append(f"skill-unreadable: {entry} ({exc})")
                    continue
                fm_match = re.match(r"\A---\s*\n(.*?)\n---", body, re.DOTALL)
                fm_text = fm_match.group(1) if fm_match else body
                if not re.search(r"(?m)^\s*description\s*:\s*\S+", fm_text):
                    errors.append(f"skill-frontmatter: {entry}/SKILL.md missing 'description:'")
                if always_on_text and not re.search(
                    rf"(?<![a-zA-Z0-9_-]){re.escape(entry)}(?![a-zA-Z0-9_-])",
                    always_on_text,
                ):
                    errors.append(
                        f"skill-trigger: skill {entry!r} has no trigger line in always-on text"
                    )

        for m in re.finditer(r"\bscripts/([a-zA-Z0-9_.\-/]+\.py)\b", always_on_text or ""):
            rel_script = f"scripts/{m.group(1)}"
            try:
                norm = normalize_rel(rel_script)
            except ValueError as exc:
                errors.append(f"script-escape: {exc}")
                continue
            cand = os.path.join(workspace_root, norm)
            real_cand = os.path.realpath(cand)
            if real_cand != real_root and not real_cand.startswith(real_root + os.sep):
                errors.append(f"script-escape: {norm!r} resolves outside workspace")
                continue
            if not os.path.isfile(cand):
                errors.append(f"script-missing: referenced {norm!r} does not exist")

        return {"ok": not errors, "skills": skills_found, "errors": errors}
