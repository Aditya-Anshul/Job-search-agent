"""BaseLLM abstract class and LLMResponse dataclass."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    """Structured response returned by every LLM provider."""

    content: str
    model: str
    tokens_used: Optional[int] = field(default=None)


class BaseLLM(ABC):
    """Abstract base class that every LLM provider must implement."""

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
    ) -> LLMResponse:
        """Send a prompt to the LLM and return a structured response."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this provider is properly configured."""
        ...
