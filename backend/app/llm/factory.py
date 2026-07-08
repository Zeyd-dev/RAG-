"""
Returns the configured LLMProvider instance. Add new providers by
importing them here and registering a name in PROVIDERS.
"""
from ..config import get_settings
from .base import LLMProvider
from .groq_provider import GroqProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
}


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    provider_cls = PROVIDERS.get(settings.LLM_PROVIDER)
    if not provider_cls:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
    return provider_cls()
