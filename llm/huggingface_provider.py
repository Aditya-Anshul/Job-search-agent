"""HuggingFaceLLM provider — Hugging Face Serverless Router API (OpenAI compatibility)."""

import os
from typing import Optional
from openai import AsyncOpenAI

from config.settings import settings
from llm.base import BaseLLM, LLMResponse
from utils.logger import logger

_DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
_FALLBACK_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
]


class HuggingFaceLLM(BaseLLM):
    """LLM provider using the Hugging Face Router API (OpenAI compatible)."""

    def __init__(self) -> None:
        self._api_key = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or settings.huggingface_api_key or ""
        self._model = settings.huggingface_model or _DEFAULT_MODEL
        self._client = None
        if self._api_key:
            self._client = AsyncOpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=self._api_key,
            )
        logger.info(f"HuggingFaceLLM initialised: model={self._model}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        """Send a prompt using the Hugging Face Router API (OpenAI compatible chat model)."""
        if not self._client:
            logger.error("HuggingFaceLLM client not initialized (no api key found)")
            return LLMResponse(content="", model=self._model)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Try primary model then fallbacks
        models_to_try = [self._model] + [m for m in _FALLBACK_MODELS if m != self._model]

        for model in models_to_try:
            try:
                logger.info(f"HuggingFaceLLM trying model: {model}")
                completion = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                )
                content = completion.choices[0].message.content or ""
                logger.info(f"HuggingFaceLLM response from {model}: {len(content)} chars")
                return LLMResponse(content=content, model=model)
            except Exception as e:
                logger.warning(f"HuggingFaceLLM failed for model {model}: {e}")

        logger.error("HuggingFaceLLM all models failed, returning empty response")
        return LLMResponse(content="", model=self._model)

    def is_available(self) -> bool:
        return bool(os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY") or settings.huggingface_api_key)
