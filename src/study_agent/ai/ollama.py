"""Local Ollama adapter for provider-neutral AI generation."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from study_agent.ai.provider import AIProvider
from study_agent.config.settings import Settings
from study_agent.core.exceptions import AIProviderError


class OllamaProvider(AIProvider):
    """Adapter for a local Ollama HTTP server."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.ai_model or "qwen3:1.7b"
        self._base_url = "http://127.0.0.1:11434"
        self._timeout = settings.ai_timeout_seconds

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }

        if system:
            payload["system"] = system

        data = self._request("/api/generate", payload)
        text = data.get("response")

        if not isinstance(text, str) or not text.strip():
            raise AIProviderError("Ollama returned an empty response")

        return text.strip()

    def generate_structured(
        self,
        prompt: str,
        schema: type[Any],
        *,
        system: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "think": False,
        }

        if system:
            payload["system"] = system

        response = self._request("/api/generate", payload)
        raw = response.get("response")

        if not isinstance(raw, str) or not raw.strip():
            raise AIProviderError(
                "Ollama returned an empty structured response"
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError(
                "Ollama returned invalid structured data"
            ) from exc

        try:
            if hasattr(schema, "model_validate"):
                return schema.model_validate(data)

            if schema is dict:
                return data

            return schema(**data)
        except (TypeError, ValueError, AttributeError) as exc:
            raise AIProviderError(
                "Ollama returned invalid structured data"
            ) from exc

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise AIProviderError("Ollama request failed") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIProviderError("Ollama returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise AIProviderError("Ollama returned an invalid response")

        return data
