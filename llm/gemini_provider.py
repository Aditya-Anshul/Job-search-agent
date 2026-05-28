"""GeminiLLM provider — Google Gemini 1.5 Flash (free cloud tier).

To enable: set LLM_PROVIDER=gemini and GEMINI_API_KEY in .env
Get a free API key at https://aistudio.google.com
"""

import warnings
from typing import Optional
from google import genai
from google.genai import types

# Suppress google-genai warning about non-text parts (thought_signature)
warnings.filterwarnings("ignore", message=".*non-text parts.*")

from config.settings import settings
from llm.base import BaseLLM, LLMResponse
from utils.logger import logger


class GeminiLLM(BaseLLM):
    """LLM provider using Google Gemini 1.5/2.0 Flash via new google-genai SDK."""

    def __init__(self) -> None:
        self._model_name: str = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)
        logger.info(f"GeminiLLM initialised: model={self._model_name}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        try:
            async with self._client.aio as aclient:
                response = await aclient.models.generate_content(
                    model=self._model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        max_output_tokens=1000,
                        temperature=0.7,
                    ),
                )
            content = response.text
            tokens_used: Optional[int] = None
            try:
                tokens_used = response.usage_metadata.total_token_count
            except AttributeError:
                pass
            logger.debug(f"GeminiLLM response: {len(content)} chars, tokens={tokens_used}")
            return LLMResponse(content=content, model=self._model_name, tokens_used=tokens_used)
        except Exception as e:
            logger.error(f"GeminiLLM request failed: {e}")
            return LLMResponse(content="", model=self._model_name)

    def is_available(self) -> bool:
        return bool(settings.gemini_api_key)
