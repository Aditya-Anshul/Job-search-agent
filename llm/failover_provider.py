"""Failover LLM Provider — Chains OpenAI -> Gemini -> Hugging Face."""

from typing import Optional, List
from .base import BaseLLM, LLMResponse
from utils.logger import logger


class FailoverLLM(BaseLLM):
    """LLM provider that automatically handles credit exhaustion, rate limits, and API failures

    by trying providers in sequence: OpenAI (ChatGPT) -> Google Gemini -> Hugging Face (Free Tier).
    """

    def __init__(self) -> None:
        self._providers: List[tuple[str, BaseLLM]] = []
        self._setup_providers()

    def _setup_providers(self) -> None:
        # 1. Gemini (Primary)
        try:
            from llm.gemini_provider import GeminiLLM
            gemini_prov = GeminiLLM()
            if gemini_prov.is_available():
                self._providers.append(("gemini", gemini_prov))
        except Exception as e:
            logger.warning(f"Could not initialize Gemini provider: {e}")

        # 2. Hugging Face (Secondary / Failover)
        try:
            from llm.huggingface_provider import HuggingFaceLLM
            hf_prov = HuggingFaceLLM()
            if hf_prov.is_available():
                self._providers.append(("huggingface", hf_prov))
        except Exception as e:
            logger.warning(f"Could not initialize Hugging Face provider: {e}")

        # Fallback to Placeholder if no cloud keys are configured
        if not self._providers:
            from llm.placeholder import PlaceholderLLM
            logger.warning("No cloud keys configured. Defaulting to PlaceholderLLM.")
            self._providers.append(("placeholder", PlaceholderLLM()))

        active_chain = " -> ".join([name for name, _ in self._providers])
        logger.info(f"FailoverLLM chain setup complete: {active_chain}")

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        last_error = None
        for name, provider in self._providers:
            try:
                logger.info(f"Attempting completion with LLM provider: {name}")
                response = await provider.complete(prompt, system)
                # If response has valid content, return it
                if response and response.content.strip():
                    logger.success(f"LLM completion succeeded with provider: {name}")
                    return response
                else:
                    logger.warning(f"LLM provider {name} returned empty content, trying next provider.")
            except Exception as e:
                logger.error(f"LLM provider {name} failed: {e}. Trying next provider in failover chain.")
                last_error = e

        # If all failed, fall back to PlaceholderLLM as a last resort
        logger.critical("All configured LLM providers in the failover chain failed!")
        try:
            from llm.placeholder import PlaceholderLLM
            placeholder = PlaceholderLLM()
            logger.info("Falling back to last-resort PlaceholderLLM to preserve master loop safety.")
            return await placeholder.complete(prompt, system)
        except Exception as e:
            if last_error:
                raise last_error
            raise e

    def is_available(self) -> bool:
        return any(provider.is_available() for _, provider in self._providers)
