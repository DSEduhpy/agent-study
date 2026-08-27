"""Provider-neutral interface for text and structured AI generation."""

from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    """Contract implemented by OpenAI, local, or future provider adapters."""

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Generate text from a prompt."""

    @abstractmethod
    def generate_structured(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any:
        """Generate and validate a structured response."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Generate from chat messages using the provider's normal text path."""
        prompt = "\n\n".join(
            f"{message['role']}: {message['content']}" for message in messages)
        return self.generate(prompt)
