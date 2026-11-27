"""Pluggable LLM providers. The platform only talks to `LLMProvider`, so the model
backend (self-hosted Ollama, Claude API, or a deterministic mock) is a config switch."""
from .base import LLMProvider, LLMUnavailable
from .factory import get_provider

__all__ = ["LLMProvider", "LLMUnavailable", "get_provider"]
