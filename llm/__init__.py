"""LLM factory — get_llm() returns the configured provider instance.

Supported LLM_PROVIDER values:
  placeholder  -> No API key needed (mock responses, for testing)
  huggingface  -> Free HuggingFace Inference API (Mistral-7B, Llama3)
  ollama       -> Local Llama 3 via Ollama (100% private)
  groq         -> Groq free cloud (~14,400 req/day)
  gemini       -> Google Gemini 1.5 Flash (free tier)
  deepseek     -> DeepSeek cloud (needs balance)
"""

from config.settings import settings
from llm.base import BaseLLM
from utils.logger import logger


def get_llm() -> BaseLLM:
    """Factory: read LLM_PROVIDER from config and return provider instance.

    Supported values for LLM_PROVIDER:
        placeholder  -> PlaceholderLLM (no API key, mock responses, always works)
        ollama       -> OllamaLLM (local Llama 3 via Ollama)
        groq         -> GroqLLM (free cloud, ~14,400 req/day free)
        gemini       -> GeminiLLM (free cloud, Google Gemini 1.5 Flash)
        deepseek     -> DeepSeekLLM (free cloud, strong reasoning)
    """
    provider = settings.llm_provider.lower().strip()
    logger.info(f"LLM Factory selected provider: {provider}")

    # ── Placeholder (default — no API key needed) ─────────────────
    if provider in ("placeholder", "mock", "test"):
        from llm.placeholder import PlaceholderLLM
        return PlaceholderLLM()

    # ── Resilient Failover Chain (OpenAI -> Gemini -> HuggingFace) ──
    elif provider in ("openai", "gemini", "huggingface", "hf", "failover", "hybrid"):
        from llm.failover_provider import FailoverLLM
        return FailoverLLM()

    # ── Ollama — local Llama 3 ────────────────────────────────────
    # To enable: LLM_PROVIDER=ollama in .env + ollama pull llama3
    elif provider == "ollama":
        from llm.ollama_provider import OllamaLLM
        return OllamaLLM()

    # ── Groq — free cloud Llama 3 70B ────────────────────────────
    # To enable: LLM_PROVIDER=groq and GROQ_API_KEY in .env
    elif provider == "groq":
        from llm.groq_provider import GroqLLM
        return GroqLLM()

    # ── DeepSeek — free cloud, strong reasoning ───────────────────
    # To enable: LLM_PROVIDER=deepseek and DEEPSEEK_API_KEY in .env
    elif provider == "deepseek":
        from llm.deepseek_provider import DeepSeekLLM
        return DeepSeekLLM()

    else:
        logger.warning(
            f"LLM Factory unknown provider '{provider}'. "
            "Falling back to PlaceholderLLM. "
            "Valid options: placeholder | ollama | groq | gemini | deepseek"
        )
        from llm.placeholder import PlaceholderLLM
        return PlaceholderLLM()
