"""OllamaLLM provider — local Llama 3 inference via Ollama HTTP API."""

from typing import Optional
import httpx

from config.settings import settings
from llm.base import BaseLLM, LLMResponse
from utils.logger import logger

_GENERATE_PATH = "/api/generate"
_INFERENCE_TIMEOUT = 120.0


class OllamaLLM(BaseLLM):
    """LLM provider for local Ollama inference (Llama 3 and compatible models).

    To enable: set LLM_PROVIDER=ollama in .env
    Install Ollama from https://ollama.com then run: ollama pull llama3
    """

    def __init__(self) -> None:
        self._base_url: str = settings.ollama_base_url
        self._model: str = settings.ollama_model
        logger.info(f"OllamaLLM initialised: model={self._model} url={self._base_url}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        payload: dict = {"model": self._model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        try:
            async with httpx.AsyncClient(timeout=_INFERENCE_TIMEOUT) as client:
                response = await client.post(f"{self._base_url}{_GENERATE_PATH}", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("response", "")
                tokens_used = data.get("eval_count")
                logger.debug(f"OllamaLLM response: {len(content)} chars, tokens={tokens_used}")
                return LLMResponse(content=content, model=self._model, tokens_used=tokens_used)
        except httpx.ConnectError as e:
            logger.error(f"OllamaLLM cannot connect to {self._base_url}. Is Ollama running? {e}")
            return LLMResponse(content="", model=self._model)
        except Exception as e:
            logger.error(f"OllamaLLM request failed: {e}")
            return LLMResponse(content="", model=self._model)

    def is_available(self) -> bool:
        return True
