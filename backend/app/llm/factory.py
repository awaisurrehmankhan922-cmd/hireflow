from ..config import get_settings
from .base import LLMProvider
from .providers import AnthropicProvider, MockProvider, OllamaProvider

_override: LLMProvider | None = None


def set_provider(provider: LLMProvider | None) -> None:
    """Used by tests to inject a provider."""
    global _override
    _override = provider


def get_provider() -> LLMProvider:
    if _override is not None:
        return _override
    s = get_settings()
    if s.llm_provider == "anthropic":
        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.llm_timeout_seconds)
    if s.llm_provider == "mock":
        return MockProvider()
    return OllamaProvider(s.ollama_url, s.ollama_model, s.llm_timeout_seconds)
