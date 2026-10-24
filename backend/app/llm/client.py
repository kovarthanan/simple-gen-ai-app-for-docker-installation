"""LLM provider wrapper: Anthropic (Claude), OpenAI-compatible APIs, or a local Ollama model."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.core.exceptions import LLMError


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(ABC):
    model: str

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse: ...

    def is_configured(self) -> bool:
        return True


class AnthropicLLM(LLMClient):
    def __init__(self, api_key: str | None, model: str, max_tokens: int, temperature: float | None, timeout: float):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout) if api_key else None
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def is_configured(self) -> bool:
        return self._client is not None

    def complete(self, prompt, system=None, max_tokens=None, temperature=None) -> LLMResponse:
        if self._client is None:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        temp = temperature if temperature is not None else self.temperature
        if temp is not None:
            kwargs["temperature"] = temp
        try:
            resp = self._client.messages.create(**kwargs)
        except self._anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            model=resp.model,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


class OpenAICompatibleLLM(LLMClient):
    """Works with OpenAI and any OpenAI-compatible endpoint (Groq, Together, vLLM, LM Studio...)."""

    def __init__(self, api_key: str | None, base_url: str, model: str, max_tokens: int,
                 temperature: float | None, timeout: float):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(self, prompt, system=None, max_tokens=None, temperature=None) -> LLMResponse:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is not set")
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens or self.max_tokens,
        }
        temp = temperature if temperature is not None else self.temperature
        if temp is not None:
            body["temperature"] = temp
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI-compatible API error: {exc}") from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            text=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


class OllamaLLM(LLMClient):
    def __init__(self, base_url: str, model: str, max_tokens: int, temperature: float | None, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def complete(self, prompt, system=None, max_tokens=None, temperature=None) -> LLMResponse:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        options: dict[str, Any] = {"num_predict": max_tokens or self.max_tokens}
        temp = temperature if temperature is not None else self.temperature
        if temp is not None:
            options["temperature"] = temp
        try:
            r = httpx.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False, "options": options},
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama error: {exc}") from exc
        return LLMResponse(
            text=data.get("message", {}).get("content", ""),
            model=data.get("model", self.model),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
        )


def build_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.lower()
    common = dict(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
    if provider == "anthropic":
        return AnthropicLLM(api_key=settings.anthropic_api_key, **common)
    if provider == "openai":
        return OpenAICompatibleLLM(api_key=settings.openai_api_key, base_url=settings.openai_base_url, **common)
    if provider == "ollama":
        return OllamaLLM(base_url=settings.ollama_base_url, **common)
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}' (use anthropic | openai | ollama)")


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Parse the first JSON object in an LLM reply (handles ```json fences and chatter)."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("No JSON object found in LLM response")
