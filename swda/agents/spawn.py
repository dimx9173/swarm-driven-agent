"""
SWDA Agent Spawn: admission-handle subagent semantics (from prime-agent).

``swda.spawn(prompt, name=...)`` admits a child task and returns a handle
immediately; it never waits for or returns the child's answer. The answer
arrives only through the parent inbox (``agent_message``) or via files.

In-process design (single stdlib process, no daemon): the runner executes
admitted children in background threads and posts replies into the parent's
:class:`Inbox`.
"""
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from swda.core.hooks import HookRegistry


@dataclass
class SpawnHandle:
    """Admission handle: confirms admission only, never contains the answer."""

    child_id: str
    name: str
    artifact_dir: str
    model: Optional[str] = None
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"child_id": self.child_id, "name": self.name,
                "artifact_dir": self.artifact_dir, "model": self.model, "depth": self.depth}


@dataclass
class ChildRecord:
    """Registry entry: survives in-process compaction/restart of state."""

    handle: SpawnHandle
    status: str = "running"  # running | completed | failed | cancelled
    answer: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None


class Inbox:
    """Parent-scoped child-message inbox."""

    def __init__(self, parent_name: str = "parent"):
        self.parent_name = parent_name
        self._lock = threading.Lock()
        self._messages: List[Dict[str, Any]] = []
        self._waits: List[threading.Condition] = []

    def send(self, sender_role: str, sender_name: str, message: Any,
             receiver_name: Optional[str] = None) -> Dict[str, Any]:
        """Delivers a reply; returns a delivery receipt."""
        receipt = {
            "sender_role": sender_role,
            "sender_name": sender_name,
            "receiver": receiver_name or self.parent_name,
            "delivered": True,
            "timestamp": time.time(),
        }
        with self._lock:
            self._messages.append({"receipt": receipt, "message": message})
            waiters = list(self._waits)
        # Notify outside _lock: wait() holds its cond while reading _lock,
        # so acquiring conds under _lock risks an ABBA deadlock.
        for cond in waiters:
            with cond:
                cond.notify_all()
        return receipt

    def read(self, sender_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns (and drains) messages, filtered by sender when given."""
        with self._lock:
            taken = [m for m in self._messages
                     if sender_name is None or m["receipt"]["sender_name"] == sender_name]
            for m in taken:
                self._messages.remove(m)
        return taken

    def wait(self, sender_name: Optional[str] = None, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        """Blocks until at least one matching message arrives, then reads."""
        def _ready() -> bool:
            with self._lock:
                return any(m for m in self._messages
                           if sender_name is None or m["receipt"]["sender_name"] == sender_name)
        cond = threading.Condition()
        deadline = None if timeout is None else time.time() + timeout
        with cond:
            self._waits.append(cond)
            try:
                while not _ready():
                    remaining = None if deadline is None else deadline - time.time()
                    if remaining is not None and remaining <= 0:
                        return []
                    cond.wait(timeout=remaining if remaining is not None else 5.0)
            finally:
                self._waits.remove(cond)
        return self.read(sender_name=sender_name)


class ChildRegistry:
    """Parent-scoped registry: admission through completion, requeryable."""

    def __init__(self, artifact_root: str):
        self.artifact_root = artifact_root
        self._lock = threading.Lock()
        self._children: Dict[str, ChildRecord] = {}
        os.makedirs(artifact_root, exist_ok=True)

    def admit(self, name: str, prompt: str, model: Optional[str] = None, depth: int = 0) -> SpawnHandle:
        child_id = uuid.uuid4().hex[:12]
        artifact_dir = os.path.join(self.artifact_root, f"sub-{child_id}")
        os.makedirs(artifact_dir, exist_ok=True)
        # Focused-context contract: only the prompt rides with the child.
        with open(os.path.join(artifact_dir, "prompt.json"), "w", encoding="utf-8") as f:
            json.dump({"name": name, "prompt": prompt, "model": model, "depth": depth},
                      f, ensure_ascii=False, indent=2)
        handle = SpawnHandle(child_id=child_id, name=name,
                             artifact_dir=artifact_dir, model=model, depth=depth)
        with self._lock:
            self._children[child_id] = ChildRecord(handle=handle)
        return handle

    def complete(self, child_id: str, answer: Any) -> None:
        with self._lock:
            rec = self._children.get(child_id)
            if rec:
                rec.status = "completed"
                rec.answer = answer
                rec.finished_at = time.time()

    def fail(self, child_id: str, error: str) -> None:
        with self._lock:
            rec = self._children.get(child_id)
            if rec:
                rec.status = "failed"
                rec.error = error
                rec.finished_at = time.time()

    def cancel(self, child_id: str) -> None:
        with self._lock:
            rec = self._children.get(child_id)
            if rec and rec.status == "running":
                rec.status = "cancelled"
                rec.finished_at = time.time()

    def get(self, selector: str) -> Optional[ChildRecord]:
        with self._lock:
            rec = self._children.get(selector)
            if rec:
                return rec
            for c in self._children.values():
                if c.handle.name == selector:
                    return c
            return None

    def list(self, status: Optional[str] = None) -> List[ChildRecord]:
        with self._lock:
            return [c for c in self._children.values()
                    if status is None or c.status == status]


DEFAULT_MAX_DEPTH = 2


class SubagentRunner:
    """Executes admitted children in background threads; posts replies to the inbox."""

    def __init__(self, registry: ChildRegistry, inbox: Inbox,
                 handler: Callable[[str, str], Any],
                 hooks: Optional[HookRegistry] = None,
                 max_depth: int = DEFAULT_MAX_DEPTH):
        self.registry = registry
        self.inbox = inbox
        self.handler = handler
        self.hooks = hooks
        self.max_depth = max_depth

    def spawn(self, prompt: str, name: str, model: Optional[str] = None, depth: int = 0) -> SpawnHandle:
        if not name or not str(name).strip():
            raise ValueError("rlm.spawn requires a non-empty name")
        if depth >= self.max_depth:
            raise RuntimeError(f"RLM depth limit reached ({depth}/{self.max_depth}); child not admitted")
        if self.hooks is not None:
            self.hooks.run_pre("rlm.spawn", {"prompt": prompt, "name": name, "depth": depth})
        handle = self.registry.admit(name=name, prompt=prompt, model=model, depth=depth)
        t = threading.Thread(target=self._run_child, args=(handle, prompt), daemon=True)
        t.start()
        return handle

    def _run_child(self, handle: SpawnHandle, prompt: str) -> None:
        try:
            if self.hooks is not None:
                self.hooks.run_post("rlm.child.start",
                                    {"child_id": handle.child_id, "name": handle.name}, {})
            answer = self.handler(handle.name, prompt)
            self.registry.complete(handle.child_id, answer)
            self.inbox.send(sender_role="child", sender_name=handle.name, message=answer,
                            receiver_name="parent")
        except Exception as e:
            self.registry.fail(handle.child_id, str(e))
            self.inbox.send(sender_role="child", sender_name=handle.name,
                            message=None, receiver_name="parent")
