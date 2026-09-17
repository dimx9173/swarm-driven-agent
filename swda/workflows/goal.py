"""
SWDA Goal Store: durable objectives across turns (from prime-agent goals).

A goal stores the objective plus progress state until completed, paused,
budget-limited, errored, or cleared. Single-process JSON persistence;
no daemon required.
"""
import copy
import json
import os
import time
from typing import Any, Dict, List, Optional


class GoalStore:
    """Manages persistent goals in a workspace (stdlib only)."""

    def __init__(self, workspace_root: Optional[str] = None):
        import threading
        self.workspace_root = workspace_root or os.getcwd()
        self.store_path = os.path.join(self.workspace_root, ".swda", "goals.json")
        os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
        self._lock = threading.Lock()

    def _read_all(self) -> List[Dict[str, Any]]:
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write_all(self, goals: List[Dict[str, Any]]) -> None:
        tmp = self.store_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(goals, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.store_path)

    def create(self, objective: str, token_budget: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            goals = self._read_all()
            for g in goals:
                if g.get("status") == "active":
                    g["status"] = "paused"
            goal = {"objective": objective, "status": "active",
                    "progress": [], "token_budget": token_budget,
                    "tokens_used": 0, "continuations": 0,
                    "created_at": time.time(), "updated_at": time.time()}
            goals.append(goal)
            self._write_all(goals)
            return copy.deepcopy(goal)

    def get(self) -> Optional[Dict[str, Any]]:
        for g in reversed(self._read_all()):
            if g.get("status") == "active":
                return copy.deepcopy(g)
        return None

    def note(self, progress: str, tokens_used: int = 0) -> Optional[Dict[str, Any]]:
        with self._lock:
            goals = self._read_all()
            for g in reversed(goals):
                if g.get("status") == "active":
                    g["progress"].append(progress)
                    g["tokens_used"] = int(g.get("tokens_used", 0)) + tokens_used
                    g["continuations"] = int(g.get("continuations", 0)) + 1
                    g["updated_at"] = time.time()
                    self._write_all(goals)
                    return copy.deepcopy(g)
            return None

    def complete(self) -> Optional[Dict[str, Any]]:
        return self._set_status("completed")

    def pause(self) -> Optional[Dict[str, Any]]:
        return self._set_status("paused")

    def resume(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            goals = self._read_all()
            for g in reversed(goals):
                if g.get("status") == "paused":
                    g["status"] = "active"
                    g["updated_at"] = time.time()
                    self._write_all(goals)
                    return copy.deepcopy(g)
            return None

    def clear(self) -> None:
        with self._lock:
            goals = [g for g in self._read_all() if g.get("status") not in ("active", "paused", "completed")]
            self._write_all(goals)

    def _set_status(self, status: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            goals = self._read_all()
            for g in reversed(goals):
                if g.get("status") in ("active", "paused"):
                    g["status"] = status
                    g["updated_at"] = time.time()
                    self._write_all(goals)
                    return copy.deepcopy(g)
            return None
