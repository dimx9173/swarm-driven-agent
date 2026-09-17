"""
SWDA Core Blackboard: Structured Shared State with Role-Based Access Control (RBAC).
Eliminates unstructured peer-to-peer chat context noise by maintaining an isolated,
type-safe state store for all SWDD agents.
"""

from enum import Enum
import json
import copy
from typing import Any, Dict, List, Optional


class AgentRole(str, Enum):
    ALPHA = "alpha"
    BETA = "beta"
    GAMMA = "gamma"
    BUILDER = "builder"
    DESTROYER = "destroyer"
    REFEREE = "referee"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    SYSTEM = "system"


class BlackboardState:
    """Internal container for the shared blackboard state."""
    def __init__(self, task_id: str = "default"):
        self.task_id = task_id
        self.phase: str = "INTENT_GATE"
        self.intent_data: Optional[Dict[str, Any]] = None
        self.gathered_context: Dict[str, Any] = {}
        self.active_proposal: Optional[Dict[str, Any]] = None
        self.crucible_critiques: List[Dict[str, Any]] = []
        self.crucible_verdict: Optional[Dict[str, Any]] = None
        self.synthesis_blueprint: Optional[Dict[str, Any]] = None
        self.verification_results: List[Dict[str, Any]] = []
        self.artifacts: Dict[str, Any] = {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase": self.phase,
            "intent_data": self.intent_data,
            "gathered_context": self.gathered_context,
            "active_proposal": self.active_proposal,
            "crucible_critiques": self.crucible_critiques,
            "crucible_verdict": self.crucible_verdict,
            "synthesis_blueprint": self.synthesis_blueprint,
            "verification_results": self.verification_results,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlackboardState":
        state = cls(task_id=data.get("task_id", "default"))
        state.phase = data.get("phase", "INTENT_GATE")
        state.intent_data = data.get("intent_data")
        state.gathered_context = data.get("gathered_context", {})
        state.active_proposal = data.get("active_proposal")
        state.crucible_critiques = data.get("crucible_critiques", [])
        state.crucible_verdict = data.get("crucible_verdict")
        state.synthesis_blueprint = data.get("synthesis_blueprint")
        state.verification_results = data.get("verification_results", [])
        state.artifacts = data.get("artifacts", {})
        return state


class Blackboard:
    """
    Type-Safe Central Shared State with Role-Based Access Control (RBAC).
    Guarantees clean, standardized state flow and prevents hallucination cross-contamination.
    """
    
    # Strict RBAC permission matrix for write operations
    WRITE_PERMISSIONS: Dict[str, List[AgentRole]] = {
        "phase": [AgentRole.SYSTEM],
        "intent_data": [AgentRole.SYSTEM, AgentRole.ALPHA, AgentRole.BETA, AgentRole.GAMMA],
        "gathered_context": [AgentRole.ALPHA, AgentRole.BETA, AgentRole.GAMMA, AgentRole.SYSTEM],
        "active_proposal": [AgentRole.BUILDER, AgentRole.SYSTEM],
        "crucible_critiques": [AgentRole.DESTROYER, AgentRole.SYSTEM],
        "crucible_verdict": [AgentRole.REFEREE, AgentRole.SYSTEM],
        "synthesis_blueprint": [AgentRole.BUILDER, AgentRole.REFEREE, AgentRole.SYSTEM],
        "verification_results": [AgentRole.DEVELOPER, AgentRole.REVIEWER, AgentRole.SYSTEM],
        "artifacts": [AgentRole.DEVELOPER, AgentRole.SYSTEM],
    }

    def __init__(self, task_id: str = "default", state_file: Optional[str] = None):
        self._state = BlackboardState(task_id=task_id)
        self._state_file = state_file
        if state_file:
            self.load(state_file)

    def read(self, key: str) -> Any:
        """Reads a value from shared state by key."""
        if hasattr(self._state, key):
            return copy.deepcopy(getattr(self._state, key))
        raise KeyError(f"Invalid blackboard key: '{key}'")

    def write(self, role: AgentRole, key: str, value: Any) -> None:
        """
        Writes a value to shared state, strictly validating the agent's role permissions.
        Raises PermissionError if the role lacks write authorization for the key.
        """
        if not hasattr(self._state, key):
            raise KeyError(f"Cannot write to non-existent blackboard key: '{key}'")

        allowed_roles = self.WRITE_PERMISSIONS.get(key, [AgentRole.SYSTEM])
        if role not in allowed_roles:
            raise PermissionError(
                f"RBAC Violation: Role '{role.value}' is not authorized to write to '{key}'. "
                f"Allowed roles: {[r.value for r in allowed_roles]}"
            )

        setattr(self._state, key, copy.deepcopy(value))
        if self._state_file:
            self.save(self._state_file)

    def as_role(self, role: AgentRole) -> "RoleHandle":
        """Returns a role-bound handle; no role argument to forget or index."""
        return RoleHandle(self, role)
    def append_list(self, role: AgentRole, key: str, item: Any) -> None:
        """Appends an item to a list attribute with RBAC validation."""
        current_list = self.read(key)
        if not isinstance(current_list, list):
            raise TypeError(f"Key '{key}' is not a list; cannot append.")
        current_list.append(item)
        self.write(role, key, current_list)

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns an isolated dictionary snapshot of current state."""
        return self._state.to_dict()

    def save(self, file_path: str) -> None:
        """Serializes current state to a JSON file."""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.get_snapshot(), f, indent=2, ensure_ascii=False)

    def load(self, file_path: str) -> None:
        """Loads state from a JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._state = BlackboardState.from_dict(data)
        except FileNotFoundError:
            pass


class RoleHandle:
    """Role-bound Blackboard writer: the role is fixed at construction."""

    def __init__(self, board: Blackboard, role: AgentRole):
        self._board = board
        self.role = role

    def write(self, key: str, value: Any) -> None:
        self._board.write(self.role, key, value)

    def append_list(self, key: str, item: Any) -> None:
        self._board.append_list(self.role, key, item)

    def read(self, key: str) -> Any:
        return self._board.read(key)
