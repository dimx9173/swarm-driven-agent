"""
SWDA Prime Jev: optional probabilistic guard backed by TypeSafe Jev
(System One decision model: unstructured state in, typed probabilistic
decisions out).

Enabled by presence of an API key in the environment (first match wins):
  1. JEV_API_KEY          -> custom endpoint (JEV_BASE_URL, JEV_MODEL)
  2. TYPESAFE_API_KEY     -> https://api.typesafe.ai        (model jev-1.13)
  3. OPENROUTER_API_KEY   -> https://openrouter.ai/api/v1   (model typesafe/jev-1.13)
  4. AI_GATEWAY_API_KEY   -> https://ai-gateway.vercel.sh/v1 (model typesafe-ai/jev)

Everything is overridable, so any Jev-compatible endpoint works:
  JEV_BASE_URL / JEV_MODEL / JEV_JUDGE_PATH   global (base URL, model, path)
  <PROVIDER>_BASE_URL / <PROVIDER>_MODEL      per-provider (TYPESAFE_*, ...)
  JEV_CONFIDENCE_THRESHOLD                    confidence gate (default 0.5)

Key principle: zero behavior change when disabled. judge() batches all
questions about one state into a single request and degrades to {} on any
timeout/network/parse failure; it never raises.

Callers wire the PreToolUse gate manually:
  from swda.core.hooks import HookRegistry
  from swda.prime.jev import jev_pre_tool_hook
  registry.register("PreToolUse", jev_pre_tool_hook)
The hook is deny-only: it returns None or {"decision": "block", ...} and
never allows past a deterministic firewall verdict.
"""

import http.client

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

#: Known providers, tried in precedence order. Each entry is
#: (api-key env, base-url env, default base URL, judge path, model env, default model).
#: /judge paths follow jev-use (the reference client): TypeSafe /v1/systemone,
#: OpenRouter /api/alpha/decisions, Vercel /v4/ai/evaluation-model.
#: JEV_JUDGE_PATH overrides whichever path is selected.
_PROVIDERS = (
    ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "https://api.typesafe.ai",
     "/v1/systemone", "TYPESAFE_MODEL", "jev-1.13"),
    ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "https://openrouter.ai",
     "/api/alpha/decisions", "OPENROUTER_MODEL", "typesafe/jev-1.13"),
    ("AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh",
     "/v4/ai/evaluation-model", "AI_GATEWAY_MODEL", "typesafe-ai/jev"),
)

#: Defaults for the fully custom endpoint (JEV_API_KEY + JEV_BASE_URL).
_DEFAULT_BASE_URL = "https://api.typesafe.ai"
_DEFAULT_MODEL = "jev-1.13"

#: Request path appended to the base URL; override with JEV_JUDGE_PATH.
_DEFAULT_JUDGE_PATH = "/v1/systemone"

#: Tools the PreToolUse gate inspects (shell-like execution surfaces only).
#: Matched per dot-segment: event tool "repl.execute" -> {"repl","execute"}.
GATABLE_TOOLS = frozenset({"bash", "shell", "repl", "execute", "tdd", "run_tests"})

#: Single-request timeout in seconds; Jev latency is ~100ms, keep the
#: guard off the critical path when the backend is unreachable.
_TIMEOUT_SECONDS = 5.0

_INTENT_OPTIONS = {
    "implement": "build or change code",
    "investigate": "read, debug, or explain existing behavior",
    "document": "write docs, notes, or reports",
    "unsure": "cannot tell from the request alone",
}


@dataclass
class JevAnswer:
    answer: str                 # pick: option key; rate: rating; check: "0.x" float as str
    confidence: float           # 0.0 - 1.0
    confidence_from: str        # "reported" (provider head) or "estimated" (fallback)
    escalate: bool              # True if Jev recommends human review


def is_enabled() -> bool:
    """True when any Jev provider API key is configured in the environment."""
    return _provider_config() is not None


def _provider_config() -> Optional[tuple]:
    """
    Resolve (base_url, api_key, model, judge_path) for the first configured
    provider, or None when no credentials are present.

    Precedence: JEV_API_KEY (fully custom endpoint) wins; otherwise the first
    known provider with a key set. Every URL and model is overridable:
      JEV_BASE_URL        -> overrides whichever base URL is selected
      JEV_MODEL           -> overrides whichever model is selected
      JEV_JUDGE_PATH      -> request path (per-provider default)
      <PROVIDER>_BASE_URL / <PROVIDER>_MODEL -> per-provider overrides
    """
    custom_key = os.getenv("JEV_API_KEY")
    if custom_key:
        return (
            os.getenv("JEV_BASE_URL") or _DEFAULT_BASE_URL,
            custom_key,
            os.getenv("JEV_MODEL") or _DEFAULT_MODEL,
            os.getenv("JEV_JUDGE_PATH") or _DEFAULT_JUDGE_PATH,
        )

    for env_key, url_env, default_url, default_path, model_env, default_model in _PROVIDERS:
        api_key = os.getenv(env_key)
        if api_key:
            return (
                os.getenv("JEV_BASE_URL") or os.getenv(url_env) or default_url,
                api_key,
                os.getenv("JEV_MODEL") or os.getenv(model_env) or default_model,
                os.getenv("JEV_JUDGE_PATH") or default_path,
            )
    return None


def _threshold() -> float:
    try:
        return float(os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


# === Question builders (the three Jev primitives) ===

def pick(question: str, options: Dict[str, str]) -> Dict[str, Any]:
    """Choice primitive: select one option key from {key: description}."""
    return {"type": "choice", "question": str(question), "options": dict(options)}


def rate(question: str, levels: List[str]) -> Dict[str, Any]:
    """Score primitive: rate on an ordered rubric of levels."""
    return {"type": "score", "question": str(question), "levels": list(levels)}


def check(statement: str) -> Dict[str, Any]:
    """Noul primitive: probability the statement is true (0.0 - 1.0)."""
    return {"type": "noul", "question": str(statement)}


def judge(state: Dict[str, Any], questions: Dict[str, Any]) -> Dict[str, JevAnswer]:
    """
    One batched request to Jev for all questions about the same state.

    Returns {} when disabled, on timeout/network failure, or on any shape
    mismatch. Never raises.
    """
    config = _provider_config()
    if not config:
        return {}
    base_url, api_key, model, judge_path = config

    payload = {
        "model": model,
        "state": json.dumps(state, default=str),
        "questions": [
            {"id": qid, **spec}
            for qid, spec in questions.items()
            if isinstance(spec, dict) and spec.get("type") in ("choice", "score", "noul")
        ],
    }
    if not payload["questions"]:
        return {}

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{judge_path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError):
        return {}

    return _parse_answers(body, questions)


def _parse_answers(body: Any, questions: Dict[str, Any]) -> Dict[str, JevAnswer]:
    """Defensive parse of the /v1/judge response; anything unexpected -> {}."""
    rows = body.get("answers") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return {}
    out: Dict[str, JevAnswer] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        qid = row.get("id")
        if qid not in questions or row.get("answer") is None:
            continue
        answer = str(row["answer"])
        confidence, from_head = _confidence(row, answer)
        out[qid] = JevAnswer(
            answer=answer,
            confidence=confidence,
            confidence_from=from_head,
            escalate=answer == "unsure" or confidence < _threshold(),
        )
    return out


def _confidence(row: Dict[str, Any], answer: str) -> tuple:
    """Reported head when present; else estimated from distribution/noul."""
    head = row.get("confidence")
    if isinstance(head, (int, float)) and not isinstance(head, bool):
        return float(head), "reported"
    dist = row.get("distribution")
    values = list(dist.values()) if isinstance(dist, dict) else (dist if isinstance(dist, list) else [])
    probs = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if probs:
        return max(probs), "estimated"
    try:  # noul answers are 0.0-1.0 floats; certainty is distance from 0.5
        return abs(float(answer) - 0.5) * 2, "estimated"
    except ValueError:
        return 0.0, "estimated"


# === PreToolUse gate (deny-only) ===

def jev_pre_tool_hook(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Probabilistic guard before shell-like tool execution.

    Returns None (fall through to the deterministic firewall) or
    {"decision": "block", ...}. NEVER returns an allow verdict and never
    raises into the workflow.
    """
    try:
        if not is_enabled():
            return None
        tool = str(event.get("tool", ""))
        if not _is_gatable(tool):
            return None
        answers = judge(
            {"tool": tool, "args": event.get("args") or {}},
            {"gate": pick(
                "Should this tool action run as-is?",
                {"allow": "safe to execute", "deny": "unsafe action", "ask": "needs human review"},
            )},
        )
        gate = answers.get("gate")
        if gate is None:
            return None
        if gate.answer == "deny":
            return {"decision": "block", "reason": f"Jev denied: {tool} (confidence {gate.confidence:.2f})"}
        if gate.answer == "ask":
            return {"decision": "block", "reason": f"Jev asks for human review: {tool} (confidence {gate.confidence:.2f})"}
        return None
    except Exception:
        return None


def _is_gatable(tool: str) -> bool:
    return any(seg in GATABLE_TOOLS for seg in tool.lower().split("."))


# === Intent pre-classification hint (advisory only) ===

def intent_hint(prompt_text: str) -> Optional[str]:
    """
    Hint for INTENT_GATE consumers: a classification string, "unsure" on
    low confidence, or None when Jev is disabled/unreachable. Hint only -
    it never blocks FSM transitions.
    """
    answers = judge({"prompt": str(prompt_text)}, {"intent": pick("What kind of task is this?", _INTENT_OPTIONS)})
    intent = answers.get("intent")
    if intent is None:
        return None
    if intent.answer not in _INTENT_OPTIONS or intent.answer == "unsure" or intent.confidence < _threshold():
        return "unsure"
    return intent.answer
