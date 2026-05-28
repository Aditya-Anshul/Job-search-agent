"""GroqLLM provider — free cloud inference via the official Groq SDK.

To enable: set LLM_PROVIDER=groq and GROQ_API_KEY in .env
Get a free API key at https://console.groq.com (~14,400 req/day free)
"""

from typing import Optional
from groq import AsyncGroq

from config.settings import settings
from llm.base import BaseLLM, LLMResponse
from utils.logger import logger


class GroqLLM(BaseLLM):
    """LLM provider using Groq's free cloud inference API (Llama 3 70B)."""

    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._model: str = settings.groq_model
        logger.info(f"GroqLLM initialised: model={self._model}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=1000,
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            tokens_used = response.usage.total_tokens if response.usage else None
            logger.debug(f"GroqLLM response: {len(content)} chars, tokens={tokens_used}")
            return LLMResponse(content=content, model=self._model, tokens_used=tokens_used)
        except Exception as e:
            logger.error(f"GroqLLM request failed: {e}")
            return LLMResponse(content="", model=self._model)

    def is_available(self) -> bool:
        return bool(settings.groq_api_key)
