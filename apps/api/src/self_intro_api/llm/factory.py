from self_intro_api.core.config import Settings
from self_intro_api.llm.base import LLMProvider
from self_intro_api.llm.openai_compatible import OpenAICompatibleLLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    provider_name = settings.llm_provider.lower().strip()
    if provider_name in {"openai-compatible", "openai_compatible", "openai"}:
        api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        return OpenAICompatibleLLMProvider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=api_key,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
