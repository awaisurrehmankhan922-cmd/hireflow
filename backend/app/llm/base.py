from abc import ABC, abstractmethod


class LLMUnavailable(Exception):
    """Raised when the inference service is down/timeouts. Callers keep work queued."""


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        """Return the raw text completion."""

    def health(self) -> bool:
        try:
            self.complete("Reply with OK.", "ping")
            return True
        except LLMUnavailable:
            return False
