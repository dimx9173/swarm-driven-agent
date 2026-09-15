"""
SWDA Prime RLM: Recursive Language Model Dispatcher.
Treats sub-agents as pure programmatic function calls and context as isolated variables.

Configuration resolution order (highest wins):
  1. Explicit constructor args / --model CLI flag
  2. Process environment variables
  3. .env file (repo-root, then cwd; stdlib loader, never overrides env)
  4. Built-in defaults (auto-free model, public OpenAI base)

Supported .env keys:
  OPENAI_BASE_URL, OPENAI_API_KEY, SWDA_MODEL, SWDA_FALLBACK_MODELS
SWDA_FALLBACK_MODELS is a comma-separated list tried in order after the
primary model is rejected with model_not_allowed.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Type, TypeVar, Callable

T = TypeVar("T")


def load_dotenv(search_paths: Optional[List[str]] = None) -> Optional[str]:
    """
    Minimal stdlib .env loader (no third-party dependency).
    Loads KEY=VALUE lines into os.environ without overriding existing vars.
    Searches repo-root .env then cwd .env. Returns the path loaded, if any.
    """
    candidates: List[str] = []
    if search_paths:
        candidates.extend(search_paths)
    here = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    candidates.append(os.path.join(repo_root, ".env"))
    cwd_env = os.path.join(os.getcwd(), ".env")
    if cwd_env not in candidates:
        candidates.append(cwd_env)

    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = value
            return path
        except OSError:
            continue
    return None


class RLMDispatcher:
    """
    Spawns subagents programmatically with strict role isolation and schema adherence.
    Subagent internal monologue stays strictly in its own local scope, returning only
    the verified artifact to the parent caller.
    """

    #: Gateway default when neither --model nor SWDA_MODEL is set.
    AUTO_FREE_MODEL = "auto-free"

    def __init__(
        self,
        default_model: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        mock_handler: Optional[Callable[[str, str], Any]] = None,
    ):
        load_dotenv()
        self.default_model = default_model or os.getenv("SWDA_MODEL", self.AUTO_FREE_MODEL)
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "mock-key")
        self.fallback_models = self._normalize_fallbacks(fallback_models)
        self.mock_handler = mock_handler

    @staticmethod
    def _normalize_fallbacks(explicit: Optional[List[str]] = None) -> List[str]:
        """Merges explicit list with SWDA_FALLBACK_MODELS env; auto-free always last."""
        merged: List[str] = list(explicit) if explicit else []
        for m in RLMDispatcher._env_fallbacks():
            if m not in merged:
                merged.append(m)
        return merged

    @staticmethod
    def _env_fallbacks() -> List[str]:
        """Parses SWDA_FALLBACK_MODELS comma list; always ends with auto-free."""
        raw = os.getenv("SWDA_FALLBACK_MODELS", "")
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if RLMDispatcher.AUTO_FREE_MODEL not in models:
            models.append(RLMDispatcher.AUTO_FREE_MODEL)
        return models

    def spawn(
        self,
        role: str,
        prompt: str,
        schema: Optional[Type[T]] = None,
        model: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Synchronously or asynchronously dispatches a subagent call.
        Returns validated schema instance or parsed JSON/text.
        """
        target_model = model or self.default_model

        # 1. Deterministic Mock / Replay Support
        if self.mock_handler:
            mock_res = self.mock_handler(role, prompt)
            if schema and isinstance(mock_res, dict):
                return self._parse_schema(schema, mock_res)
            return mock_res

        system_instruction = (
            f"You are an isolated SWDD {role.upper()} subagent. "
            "Maintain extreme epistemic humility, objectivity, and format compliance. "
            "Output valid JSON only when requested."
        )

        messages = [{"role": "system", "content": system_instruction}]
        if context:
            messages.append({"role": "system", "content": f"Context Anchors: {json.dumps(context)}"})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.2,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}

        attempted = [target_model]
        try:
            raw_content = self._call_endpoint(payload)
        except RuntimeError as err:
            # Gateway rejected the model id -> walk the fallback chain once each.
            if "model_not_allowed" not in str(err):
                raise
            fallback_err: Optional[RuntimeError] = err
            raw_content = None
            for fallback in self.fallback_models:
                if fallback in attempted:
                    continue
                attempted.append(fallback)
                payload["model"] = fallback
                try:
                    raw_content = self._call_endpoint(payload)
                    fallback_err = None
                    break
                except RuntimeError as ferr:
                    if "model_not_allowed" not in str(ferr):
                        raise
                    fallback_err = ferr
            if raw_content is None:
                raise RuntimeError(
                    f"RLM models rejected {attempted} ({fallback_err}); "
                    f"check SWDA_MODEL/SWDA_FALLBACK_MODELS or 'swda models' output"
                )

        # 2. Schema Validation & Parsing
        if schema:
            try:
                parsed_json = json.loads(raw_content)
                return self._parse_schema(schema, parsed_json)
            except Exception as e:
                raise ValueError(f"RLM Subagent failed schema validation: {e}\nRaw output: {raw_content}")

        return raw_content

    def list_models(self, timeout: int = 15) -> List[str]:
        """Fetches live model ids from the OpenAI-compatible /models endpoint."""
        url = f"{self.api_base.rstrip('/')}/models"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except TimeoutError as err:
            raise RuntimeError(f"RLM Timeout listing models at {url} after {timeout}s: {err}")
        except urllib.error.URLError as err:
            raise RuntimeError(f"RLM Network error listing models at {url}: {err}")
        models = data.get("data", []) if isinstance(data, dict) else []
        return [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]

    def _call_endpoint(self, payload: Dict[str, Any]) -> str:
        """Calls OpenAI-compatible LLM endpoint using standard library urllib."""
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except TimeoutError as err:
            raise RuntimeError(f"RLM Timeout connecting to {url} after 120s: {err}")
        except urllib.error.URLError as err:
            raise RuntimeError(f"RLM Network error connecting to {url}: {err}")

    def _parse_schema(self, schema: Type[T], data: Dict[str, Any]) -> T:
        """Parses data into Pydantic model or dataclass/dict."""
        if hasattr(schema, "model_validate"):
            return schema.model_validate(data)  # Pydantic v2
        elif hasattr(schema, "parse_obj"):
            return schema.parse_obj(data)  # Pydantic v1
        elif hasattr(schema, "__dataclass_fields__"):
            return schema(**data)  # Dataclass or constructor
        return data  # Fallback dict
