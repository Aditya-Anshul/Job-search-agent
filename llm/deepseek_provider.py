"""DeepSeekLLM provider — free-tier cloud inference via OpenAI-compatible API.

To enable: set LLM_PROVIDER=deepseek and DEEPSEEK_API_KEY in .env
Get API key at https://platform.deepseek.com (generous free tier)
"""

from typing import Optional
import httpx

from config.settings import settings
from llm.base import BaseLLM, LLMResponse
from utils.logger import logger

_REQUEST_TIMEOUT = 60.0
_CHAT_ENDPOINT = "/chat/completions"


class DeepSeekLLM(BaseLLM):
    """LLM provider using DeepSeek's OpenAI-compatible API.

    Strong reasoning capabilities with a generous free tier.
    Uses the same /chat/completions endpoint as OpenAI.
    """

    def __init__(self) -> None:
        self._api_key: str = settings.deepseek_api_key or ""
        self._model: str = settings.deepseek_model
        self._base_url: str = settings.deepseek_base_url
        logger.info(f"DeepSeekLLM initialised: model={self._model}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": self._model, "messages": messages, "max_tokens": 1000, "temperature": 0.7}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{self._base_url}{_CHAT_ENDPOINT}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"] or ""
                tokens_used = data.get("usage", {}).get("total_tokens")
                logger.debug(f"DeepSeekLLM response: {len(content)} chars, tokens={tokens_used}")
                return LLMResponse(content=content, model=self._model, tokens_used=tokens_used)
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeekLLM HTTP error {e.response.status_code}: {e}")
            return LLMResponse(content="", model=self._model)
        except Exception as e:
            logger.error(f"DeepSeekLLM request failed: {e}")
            return LLMResponse(content="", model=self._model)

    def is_available(self) -> bool:
        return bool(settings.deepseek_api_key)
