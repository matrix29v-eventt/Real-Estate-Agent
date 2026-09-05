"""LLM provider abstraction.

Business logic never imports a vendor SDK directly. It asks this module for a
provider and calls one method: ``complete_json(system, user, schema)``, which
returns a parsed dict validated against a JSON schema by the provider where the
provider supports it, and by Pydantic afterwards in every case.

Three providers ship:

* ``AnthropicProvider`` - cloud, uses the Messages API with structured outputs.
* ``GeminiProvider``    - cloud, uses Google's API with structured outputs.
* ``OllamaProvider``    - optional local fallback for offline demos.

If neither is configured the module raises :class:`LLMUnavailable`. Nothing in
this codebase invents an answer when no model is reachable - the UI shows a
configuration warning instead.
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import config


class LLMUnavailable(RuntimeError):
    """No LLM provider is configured or reachable."""


class LLMCallError(RuntimeError):
    """The provider was reachable but the call failed or returned garbage."""


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Return (usable, human-readable detail)."""

    @abstractmethod
    def complete_json(
        self,
        system: str,
        user: str,
        schema: Dict[str, Any],
        max_tokens: int = 4000,
        effort: str = "medium",
    ) -> Dict[str, Any]:
        """Return a JSON object matching ``schema``."""

    def label(self) -> str:
        return f"{self.name}:{self.model}"


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or config.ANTHROPIC_MODEL
        self._client = None

    def available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "ANTHROPIC_API_KEY is not set."
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False, "The 'anthropic' package is not installed (pip install anthropic)."
        return True, f"Anthropic ready ({self.model})."

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self.api_key, timeout=config.LLM_TIMEOUT_SECONDS
            )
        return self._client

    def complete_json(
        self,
        system: str,
        user: str,
        schema: Dict[str, Any],
        max_tokens: int = 4000,
        effort: str = "medium",
    ) -> Dict[str, Any]:
        usable, detail = self.available()
        if not usable:
            raise LLMUnavailable(detail)
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except Exception as exc:  # SDK raises typed errors; surface them plainly
            raise LLMCallError(f"Anthropic call failed: {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise LLMCallError(
                "The model declined to answer this request "
                f"({getattr(response, 'stop_details', None)})."
            )

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return parse_json_object(text)


# --------------------------------------------------------------------------- #
# Ollama (optional local fallback)
# --------------------------------------------------------------------------- #
class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or config.GEMINI_MODEL

    def available(self) -> tuple[bool, str]:
        if not self.api_key.strip():
            return False, "Set GEMINI_API_KEY in .env using a key from Google AI Studio."
        return True, f"Gemini configured ({self.model}); key is checked on the first call."

    def complete_json(
        self, system: str, user: str, schema: Dict[str, Any],
        max_tokens: int = 4000, effort: str = "medium",
    ) -> Dict[str, Any]:
        import requests

        usable, detail = self.available()
        if not usable:
            raise LLMUnavailable(detail)
        generation = {
            "temperature": 0,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
            "responseJsonSchema": schema,
        }
        if self.model in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            generation["thinkingConfig"] = {"thinkingBudget": 0}
        elif self.model.startswith("gemini-3"):
            generation["thinkingConfig"] = {"thinkingLevel": "low"}
        try:
            response = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": generation,
                },
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
        except requests.Timeout:
            raise LLMCallError("Gemini call timed out. Please try again.") from None
        except requests.RequestException:
            raise LLMCallError("Could not connect to Gemini. Check your internet connection.") from None
        if response.status_code == 429:
            raise LLMCallError(
                "Gemini free-tier quota or rate limit reached. Wait and retry, "
                "or check your quota in Google AI Studio."
            )
        if response.status_code in (400, 401, 403):
            raise LLMCallError(
                "Gemini rejected the request. Check GEMINI_API_KEY, model access "
                "and request configuration."
            )
        if not response.ok:
            raise LLMCallError(f"Gemini request failed (HTTP {response.status_code}).")
        try:
            payload = response.json()
            candidates = payload.get("candidates", [])
            if not candidates:
                raise LLMCallError("Gemini returned no answer; the request may have been blocked.")
            candidate = candidates[0]
            if candidate.get("finishReason") != "STOP":
                raise LLMCallError("Gemini returned an incomplete or blocked answer. Please try again.")
            text = "".join(
                part.get("text", "")
                for part in candidate.get("content", {}).get("parts", [])
                if not part.get("thought")
            )
        except (ValueError, TypeError, AttributeError, KeyError):
            raise LLMCallError("Gemini returned an invalid response.") from None
        return parse_json_object(text)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    def available(self) -> tuple[bool, str]:
        try:
            import requests
        except ImportError:  # pragma: no cover
            return False, "The 'requests' package is not installed."
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            resp.raise_for_status()
        except Exception as exc:
            return False, f"No Ollama server at {self.base_url} ({exc.__class__.__name__})."
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        if names and not any(n.split(":")[0] == self.model.split(":")[0] for n in names):
            return False, f"Ollama is running but '{self.model}' is not pulled."
        return True, f"Ollama ready ({self.model})."

    def complete_json(
        self,
        system: str,
        user: str,
        schema: Dict[str, Any],
        max_tokens: int = 4000,
        effort: str = "medium",
    ) -> Dict[str, Any]:
        import requests

        usable, detail = self.available()
        if not usable:
            raise LLMUnavailable(detail)
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": schema,  # Ollama accepts a JSON schema here
                    # num_ctx must be raised explicitly: Ollama's small default
                    # context silently truncates these prompts mid-answer.
                    "options": {
                        "temperature": 0,
                        "num_predict": max_tokens,
                        "num_ctx": 16384,
                    },
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise LLMCallError(f"Ollama call failed: {exc}") from exc
        content = resp.json().get("message", {}).get("content", "")
        return parse_json_object(content)


# --------------------------------------------------------------------------- #
# JSON recovery
# --------------------------------------------------------------------------- #
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> Dict[str, Any]:
    """Parse a JSON object out of model output, tolerating fences and prose.

    Structured outputs normally make this trivial; the recovery path exists so a
    weaker local model cannot take the whole application down.
    """
    if not text or not text.strip():
        raise LLMCallError("Model returned an empty response.")
    candidates = [text.strip()]
    fenced = _FENCE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMCallError(f"Model output was not valid JSON: {text[:300]}")


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def build_providers() -> list[LLMProvider]:
    choice = os.getenv("LLM_PROVIDER", config.LLM_PROVIDER).strip().lower()
    if choice == "gemini":
        return [GeminiProvider()]
    if choice == "anthropic":
        return [AnthropicProvider()]
    if choice == "ollama":
        return [OllamaProvider()]
    return [GeminiProvider(), AnthropicProvider(), OllamaProvider()]


def get_provider() -> LLMProvider:
    """Return the first usable provider, or raise :class:`LLMUnavailable`."""
    problems = []
    for provider in build_providers():
        usable, detail = provider.available()
        if usable:
            return provider
        problems.append(f"{provider.name}: {detail}")
    raise LLMUnavailable(
        "No LLM provider is configured. " + " | ".join(problems)
    )


def provider_status() -> Dict[str, Any]:
    """Describe LLM configuration for the UI, without raising."""
    details = []
    for provider in build_providers():
        usable, detail = provider.available()
        details.append({"provider": provider.name, "model": provider.model,
                        "usable": usable, "detail": detail})
    active = next((d for d in details if d["usable"]), None)
    return {
        "configured": active is not None,
        "active": active,
        "providers": details,
        "selection": os.getenv("LLM_PROVIDER", config.LLM_PROVIDER),
    }
