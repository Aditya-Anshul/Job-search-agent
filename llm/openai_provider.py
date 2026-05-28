"""OpenAI LLM Provider."""

from typing import Optional
from openai import AsyncOpenAI
from config.settings import settings
from .base import BaseLLM, LLMResponse
from utils.logger import logger


class OpenAILLM(BaseLLM):
    """OpenAI implementation of BaseLLM using AsyncOpenAI client."""

    def __init__(self) -> None:
        self._api_key: str = settings.openai_api_key or ""
        self._model_name: str = settings.openai_model or "gpt-4o-mini"
        self._client = AsyncOpenAI(api_key=self._api_key)
        logger.info(f"OpenAILLM initialised: model={self._model_name}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )
            content = response.choices[0].message.content or ""
            tokens_used: Optional[int] = None
            if response.usage:
                tokens_used = response.usage.total_tokens
            logger.debug(f"OpenAILLM response: {len(content)} chars, tokens={tokens_used}")
            return LLMResponse(content=content, model=self._model_name, tokens_used=tokens_used)
        except Exception as e:
            logger.error(f"OpenAILLM request failed: {e}")
            raise e

    def is_available(self) -> bool:
        return bool(self._api_key)
