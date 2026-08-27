"""Lazy OpenAI adapter that keeps the rest of the application provider-agnostic."""

import json
from typing import Any

from study_agent.ai.provider import AIProvider
from study_agent.core.exceptions import AIProviderError
from study_agent.config.settings import Settings


class OpenAIProvider(AIProvider):
    """Adapter for the OpenAI Responses API, configured entirely at runtime."""

    def __init__(self, settings: Settings) -> None:
        if not settings.ai_api_key:
            raise AIProviderError("AI API key is not configured")
        if not settings.ai_model:
            raise AIProviderError("AI model is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIProviderError("OpenAI dependency is not installed") from exc
        self._model = settings.ai_model
        self._client = OpenAI(api_key=settings.ai_api_key, timeout=settings.ai_timeout_seconds)

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        try:
            response = self._client.responses.create(model=self._model, instructions=system, input=prompt)
            text = getattr(response, "output_text", None)
            if not isinstance(text, str) or not text.strip():
                raise AIProviderError("AI returned an empty response")
            return text
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("AI request failed") from exc

    def generate_structured(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any:
        raw = self.generate(prompt, system=system)
        try:
            data = json.loads(raw)
            return schema.model_validate(data) if hasattr(schema, "model_validate") else schema(**data)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError("AI returned invalid structured data") from exc
