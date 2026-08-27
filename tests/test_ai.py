import pytest
from pathlib import Path

from study_agent.ai.provider import AIProvider
from study_agent.config.settings import Settings
from study_agent.ai.client import OpenAIProvider
from study_agent.core.exceptions import AIProviderError


class FakeProvider(AIProvider):
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return f"reply:{prompt}"

    def generate_structured(self, prompt: str, schema: type, *, system: str | None = None) -> object:
        return schema(prompt=prompt)


def test_learning_code_can_depend_on_provider_contract() -> None:
    provider: AIProvider = FakeProvider()
    assert provider.chat([{"role": "user", "content": "hello"}]) == "reply:user: hello"


def test_openai_adapter_rejects_missing_credentials() -> None:
    settings = Settings(Path("."), Path("profile.yaml"), Path("db.sqlite3"), "openai", "", None, 30)
    with pytest.raises(AIProviderError, match="not configured"):
        OpenAIProvider(settings)
