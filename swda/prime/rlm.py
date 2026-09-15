"""
SWDA Prime RLM: Recursive Language Model Dispatcher.
Treats sub-agents as pure programmatic function calls and context as isolated variables.
"""

import os
import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Type, TypeVar, Callable

T = TypeVar("T")


class RLMDispatcher:
    """
    Spawns subagents programmatically with strict role isolation and schema adherence.
    Subagent internal monologue stays strictly in its own local scope, returning only
    the verified artifact to the parent caller.
    """

    def __init__(
        self,
        default_model: str = "deepseek-chat",
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_handler: Optional[Callable[[str, str], Any]] = None,
    ):
        self.default_model = default_model
        self.api_base = api_base or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "mock-key")
        self.mock_handler = mock_handler

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

        raw_content = self._call_endpoint(payload)

        # 2. Schema Validation & Parsing
        if schema:
            try:
                parsed_json = json.loads(raw_content)
                return self._parse_schema(schema, parsed_json)
            except Exception as e:
                raise ValueError(f"RLM Subagent failed schema validation: {e}\nRaw output: {raw_content}")

        return raw_content

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
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.URLError as err:
            raise RuntimeError(f"RLM Network error connecting to {url}: {err}")

    def _parse_schema(self, schema: Type[T], data: Dict[str, Any]) -> T:
        """Parses data into Pydantic model or dataclass/dict."""
        if hasattr(schema, "model_validate"):
            return schema.model_validate(data)  # Pydantic v2
        elif hasattr(schema, "parse_obj"):
            return schema.parse_obj(data)  # Pydantic v1
        elif callable(schema):
            return schema(**data)  # Dataclass or constructor
        return data  # Fallback dict
