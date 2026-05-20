"""
Copyright (c) 2026 Damir Dulovic. All rights reserved.
Licensed under the Vigilant ESP Proprietary Software License (see LICENSE).
LLM provider abstraction — one interface, multiple backends.

Customer chooses via env (LLM_PROVIDER + provider-specific config):

  LLM_PROVIDER=openai          # default; covers OpenAI, Azure, vLLM, Ollama,
                               # Mistral, anything speaking OpenAI's
                               # Chat-Completions HTTP schema.
  LLM_PROVIDER=anthropic       # Claude via messages API
  LLM_PROVIDER=local           # local Qwen via llama-cpp-python

Each provider exposes the same `chat(system, user, ...)` method that
returns the assistant response as a string (caller parses JSON).
"""
from __future__ import annotations
import os
import time
import json
from typing import Any, Dict, Optional, Protocol, runtime_checkable

import requests


class QuotaExhausted(RuntimeError):
    """Raised when an LLM provider reports insufficient quota — retry futile."""


@runtime_checkable
class LLMProvider(Protocol):
    """Common contract: returns assistant content string (caller parses JSON if needed)."""

    def chat(self, system: str, user: str, *,
             max_tokens: int = 1500,
             temperature: float = 0.1,
             response_format_json: bool = True,
             max_retries: int = 3) -> str:
        ...

    @property
    def label(self) -> str:
        """Short human-readable identifier for logging / /api/health."""
        ...


# ─── OpenAI-compatible (OpenAI, Azure, vLLM, Ollama, Mistral, …) ────────
class OpenAICompatibleProvider:
    """One implementation covers any endpoint that follows the OpenAI Chat
    Completions schema. Tested against:
      - api.openai.com
      - Azure OpenAI (set base_url to your deployment + use `api-version`)
      - vLLM with `--api-key` and OpenAI-compatible mode
      - Ollama with /v1 path
      - Mistral La Plateforme (api.mistral.ai/v1)
    """

    def __init__(self, *, api_key: str, base_url: str, model: str,
                 is_new_model: Optional[bool] = None,
                 extra_headers: Optional[Dict[str, str]] = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.is_new_model = (self._infer_new_model(model)
                             if is_new_model is None else bool(is_new_model))
        self.extra_headers = extra_headers or {}

    @staticmethod
    def _infer_new_model(name: str) -> bool:
        # GPT-5 / o-series accept `max_completion_tokens`, reject custom temperature
        return ("gpt-5" in name) or name.startswith(("o3", "o4", "o1"))

    @property
    def label(self) -> str:
        return f"openai-compat:{self.model}"

    def chat(self, system: str, user: str, *,
             max_tokens: int = 1500,
             temperature: float = 0.1,
             response_format_json: bool = True,
             max_retries: int = 3) -> str:
        if not self.api_key:
            raise RuntimeError("OpenAICompatibleProvider: api_key is empty (set OPENAI_API_KEY or LLM_API_KEY)")
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            ("max_completion_tokens" if self.is_new_model else "max_tokens"): max_tokens,
        }
        if response_format_json:
            body["response_format"] = {"type": "json_object"}
        if not self.is_new_model:
            body["temperature"] = temperature

        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json", **self.extra_headers}
        url = f"{self.base_url}/chat/completions"

        last_err = "unknown"
        for attempt in range(max_retries):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=120)
                if r.status_code == 429:
                    try:
                        err = r.json().get("error", {})
                        err_type = err.get("type", "")
                        err_code = err.get("code", "") or ""
                    except Exception:
                        err_type, err_code = "", ""
                    if err_type == "insufficient_quota" or "quota" in err_code:
                        raise QuotaExhausted(
                            f"{self.label}: insufficient quota (type={err_type}, code={err_code})")
                    wait = int(r.headers.get("Retry-After", "0")) or (2 ** attempt + 3)
                    last_err = f"429 rate-limit (attempt {attempt+1}/{max_retries})"
                    time.sleep(min(wait, 60))
                    continue
                if r.status_code in (500, 502, 503, 504):
                    last_err = f"server {r.status_code}"
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except QuotaExhausted:
                raise
            except requests.exceptions.RequestException as e:
                last_err = f"request: {e}"
                time.sleep(2 ** attempt)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(1 + attempt)
        raise RuntimeError(f"{self.label} failed after {max_retries} retries: {last_err}")


# ─── Anthropic (Claude) ──────────────────────────────────────────────────
class AnthropicProvider:
    """Anthropic Messages API. Different schema from OpenAI: `system` is
    top-level, messages alternate user/assistant, no `response_format`.
    We inject a JSON instruction into the system prompt when requested.
    """

    def __init__(self, *, api_key: str, model: str = "claude-sonnet-4-5",
                 base_url: str = "https://api.anthropic.com"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @property
    def label(self) -> str:
        return f"anthropic:{self.model}"

    def chat(self, system: str, user: str, *,
             max_tokens: int = 1500,
             temperature: float = 0.1,
             response_format_json: bool = True,
             max_retries: int = 3) -> str:
        if not self.api_key:
            raise RuntimeError("AnthropicProvider: ANTHROPIC_API_KEY empty")
        sys_msg = system
        if response_format_json and "JSON" not in system.upper():
            sys_msg = system + "\n\nReturn STRICT valid JSON only. No markdown fences."
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": sys_msg,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        last_err = "unknown"
        for attempt in range(max_retries):
            try:
                r = requests.post(f"{self.base_url}/v1/messages",
                                  headers=headers, json=body, timeout=120)
                if r.status_code == 429:
                    wait = int(r.headers.get("Retry-After", "0")) or (2 ** attempt + 3)
                    last_err = f"429 rate-limit"
                    time.sleep(min(wait, 60))
                    continue
                if r.status_code in (500, 502, 503, 504, 529):
                    last_err = f"server {r.status_code}"
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                # Anthropic content is a list of content blocks
                blocks = r.json().get("content", [])
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                return text
            except requests.exceptions.RequestException as e:
                last_err = f"request: {e}"
                time.sleep(2 ** attempt)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(1 + attempt)
        raise RuntimeError(f"{self.label} failed after {max_retries} retries: {last_err}")


# ─── Local Qwen via llama-cpp-python (in-process) ────────────────────────
class LocalLlamaCppProvider:
    """Wraps scripts.llm_local.chat_complete (which holds the GGUF model in RAM).
    No HTTP — direct in-process inference. Slowest but free + offline.
    """

    @property
    def label(self) -> str:
        return "local-llama-cpp"

    def chat(self, system: str, user: str, *,
             max_tokens: int = 1500,
             temperature: float = 0.1,
             response_format_json: bool = True,
             max_retries: int = 3) -> str:
        # llama-cpp's response_format json is supported via create_chat_completion
        from scripts.llm_local import chat_complete
        last_err = "unknown"
        for attempt in range(max_retries):
            try:
                return chat_complete(system, user,
                                     max_tokens=max_tokens,
                                     temperature=temperature)
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(0.5)
        raise RuntimeError(f"{self.label} failed after {max_retries} retries: {last_err}")


# ─── Factory ─────────────────────────────────────────────────────────────
def make_provider(env: Optional[Dict[str, str]] = None) -> LLMProvider:
    """Build a provider from env. Falls back to legacy OPENAI_* vars if
    new LLM_* aren't set, so existing deployments don't break.

    Selection priority for `LLM_PROVIDER`:
      explicit env > legacy LOCAL_LLM_ENABLED=1 → 'local' > default 'openai'
    """
    e = env or os.environ
    raw = (e.get("LLM_PROVIDER") or "").strip().lower()
    if not raw:
        # Backward-compat: LOCAL_LLM_ENABLED=1 implies provider=local
        if e.get("LOCAL_LLM_ENABLED") == "1":
            raw = "local"
        else:
            raw = "openai"

    if raw in {"openai", "openai-compat", "openai_compat", "azure",
               "vllm", "ollama", "mistral"}:
        return OpenAICompatibleProvider(
            api_key=(e.get("LLM_API_KEY")
                     or e.get("OPENAI_API_KEY")
                     or ""),
            base_url=(e.get("LLM_BASE_URL")
                      or e.get("OPENAI_BASE_URL")
                      or "https://api.openai.com/v1"),
            # Default matches the pre-refactor extract_dna_v3 default. We've
            # empirically seen `gpt-5-mini` (without the .4) return empty
            # content for our complex DNA-extraction prompt; `gpt-5.4-mini`
            # returns proper JSON.
            model=(e.get("LLM_MODEL")
                   or e.get("OPENAI_MODEL_DNA")
                   or "gpt-5.4-mini"),
        )
    if raw == "anthropic":
        return AnthropicProvider(
            api_key=(e.get("LLM_API_KEY")
                     or e.get("ANTHROPIC_API_KEY")
                     or ""),
            model=(e.get("LLM_MODEL")
                   or e.get("ANTHROPIC_MODEL")
                   or "claude-sonnet-4-5"),
            base_url=e.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
        )
    if raw in {"local", "qwen", "llama-cpp"}:
        return LocalLlamaCppProvider()

    raise ValueError(f"Unknown LLM_PROVIDER={raw!r}. "
                     f"Valid: openai | anthropic | local")
