import json
import re

import httpx

from .base import LLMProvider, LLMUnavailable


class OllamaProvider(LLMProvider):
    """Self-hosted inference via Ollama's /api/chat (e.g. qwen3:8b)."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: int = 60):
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0.2},
        }
        if json_mode:
            body["format"] = "json"
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise LLMUnavailable(f"Ollama unavailable: {exc}") from exc
        text = r.json().get("message", {}).get("content", "")
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # strip Qwen3 reasoning

    def health(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/api/tags", timeout=5).status_code == 200
        except (httpx.HTTPError, OSError):
            return False


class AnthropicProvider(LLMProvider):
    """Claude API via the Messages endpoint. Optional alternative to local inference."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: int = 60):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        if json_mode:
            system += "\nRespond with a single valid JSON object and nothing else."
        try:
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.timeout,
            )
            r.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise LLMUnavailable(f"Claude API unavailable: {exc}") from exc
        return "".join(b.get("text", "") for b in r.json().get("content", []))


class MockProvider(LLMProvider):
    """Deterministic, offline provider for tests and demos. `available` simulates outages."""

    name = "mock"
    available = True

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        if not MockProvider.available:
            raise LLMUnavailable("mock outage")
        p = prompt.lower()
        if "task: classify_application" in p:
            cls = "qualified" if re.search(r"\d+ years", p) else "incomplete"
            pos = prompt.split("Position:")[-1].split("\n")[0].strip() or "the role"
            summary = (f"Applied for {pos}; relevant experience stated in the form." if cls == "qualified"
                       else f"Applied for {pos}; no experience details provided, follow-up needed.")
            return json.dumps({"classification": cls, "summary": summary, "confidence": 0.9})
        if "task: reply" in p:
            msg = p.split("latest message from applicant:")[-1]
            if any(k in msg for k in ("visa", "lawyer", "legal", "salary negotiation", "eligible")):
                return json.dumps({"intent": "eligibility_question", "reply": "", "confidence": 0.3,
                                   "needs_human": True, "reason": "eligibility/legal question"})
            return json.dumps({"intent": "status_question", "confidence": 0.88, "needs_human": False,
                               "reason": "", "reply": "Thanks for your message. Your application is under review "
                               "and our team will contact you within 5 business days."})
        return "OK"
