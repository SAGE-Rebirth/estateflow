from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import ChatProvider


@lru_cache
def get_chat_provider() -> ChatProvider:
    s = get_settings()
    if s.llm_provider == "anthropic":
        from app.services.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=s.anthropic_api_key, model=s.anthropic_model, effort=s.anthropic_effort
        )
    from app.services.llm.gemini_provider import GeminiProvider

    return GeminiProvider(
        model=s.gemini_llm_model,
        max_tokens=s.llm_max_tokens,
        thinking_level=s.gemini_thinking_level,
    )
