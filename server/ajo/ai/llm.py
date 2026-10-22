"""Optional model access. Every call returns parsed JSON or None; it never raises, so the deterministic fallback always runs.
The model is only ever asked to interpret text. Its output is validated by code before anything depends on it."""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import replace
from typing import Protocol

import httpx

from ..config import Settings


class LLM(Protocol):
    name: str
    def json(self, system: str, user: str) -> dict | None: ...


def _extract_json(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        v = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except ValueError:
            return None
    return v if isinstance(v, dict) else None


class OpenAICompatLLM:
    """Works with any OpenAI-compatible chat endpoint, including Nebius Token Factory."""
    name = "openai_compat"

    def __init__(self, s: Settings):
        self.s = s
        self.http = httpx.Client(timeout=45)

    def json(self, system, user):
        try:
            r = self.http.post(self.s.llm_base_url.rstrip("/") + "/chat/completions", headers={"Authorization": f"Bearer {self.s.llm_api_key}"},
                               json={"model": self.s.llm_model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            return _extract_json(r.json()["choices"][0]["message"]["content"]) if r.status_code == 200 else None
        except Exception:
            return None


class AnthropicLLM:
    name = "anthropic"

    def __init__(self, s: Settings):
        self.s = s
        self.http = httpx.Client(timeout=45)

    def json(self, system, user):
        try:
            r = self.http.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": self.s.llm_api_key, "anthropic-version": "2023-06-01"},
                               json={"model": self.s.llm_model, "max_tokens": 1200, "temperature": 0, "system": system, "messages": [{"role": "user", "content": user}]})
            return _extract_json(r.json()["content"][0]["text"]) if r.status_code == 200 else None
        except Exception:
            return None


OLLAMA_PREFERENCE = ["llama3.2:3b", "llama3.1:8b", "qwen3:8b"]     # fastest first: a chat reply should not take a minute on a laptop
THINKERS = ("qwen3", "deepseek-r1", "gpt-oss")


def list_ollama(base_url: str) -> list[dict]:
    """Chat models installed in a local Ollama (embedding models are left out). Empty when Ollama is not running."""
    try:
        r = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=1.5)
        return [{"name": m["name"], "sizeGb": round(m.get("size", 0) / 1e9, 1), "params": (m.get("details") or {}).get("parameter_size", "")}
                for m in r.json().get("models", []) if "embed" not in m["name"]] if r.status_code == 200 else []
    except Exception:
        return []


class OllamaLLM:
    """A model running on this machine through Ollama. No key, nothing leaves the computer."""

    def __init__(self, base_url: str, model: str):
        self.base, self.model = base_url.rstrip("/"), model
        self.name = f"ollama:{model}"
        self.http = httpx.Client(timeout=httpx.Timeout(35, connect=3))      # a slow or swapped-out model must never hang the chat: time out, and the rules reader answers

    def json(self, system, user):
        body = {"model": self.model, "stream": False, "format": "json", "keep_alive": "30m", "options": {"temperature": 0, "num_predict": 200, "num_ctx": 2048},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.model.startswith(THINKERS):
            body["think"] = False           # reasoning models would otherwise spend a minute thinking before a one-line answer
        try:
            r = self.http.post(self.base + "/api/chat", json=body)
            return _extract_json(r.json()["message"]["content"]) if r.status_code == 200 else None
        except Exception:
            return None

    def warm(self) -> None:
        threading.Thread(target=lambda: self.json("Reply with {}", "ok"), daemon=True).start()     # load the model now, so the first chat is not a 45 second wait


class AutoLLM:
    """The default: use a local Ollama if one is running, otherwise nothing (the chat then says it is rules-based). Re-checks, so starting Ollama later just works."""

    def __init__(self, s: Settings):
        self.s, self.inner, self.checked = s, None, 0.0

    def _resolve(self):
        if self.inner is None and time.time() - self.checked > 15:
            self.checked = time.time()
            have = [m["name"] for m in list_ollama(self.s.ollama_url)]
            pick = self.s.llm_model if self.s.llm_model in have else next((m for m in OLLAMA_PREFERENCE if m in have), have[0] if have else None)
            if pick:
                self.inner = OllamaLLM(self.s.ollama_url, pick); self.inner.warm()
        return self.inner

    @property
    def name(self) -> str:
        i = self._resolve()
        return i.name if i else "none"

    def json(self, system, user):
        i = self._resolve()
        return i.json(system, user) if i else None


def build_llm(provider: str, base_url: str, model: str, key: str, s: Settings) -> LLM | None:
    if provider == "ollama":
        return OllamaLLM(base_url or s.ollama_url, model)
    if provider == "openai_compat" and key:
        return OpenAICompatLLM(replace(s, llm="openai_compat", llm_base_url=base_url, llm_api_key=key, llm_model=model))
    if provider == "anthropic" and key:
        return AnthropicLLM(replace(s, llm="anthropic", llm_api_key=key, llm_model=model))
    return None


def make_llm(s: Settings) -> LLM | None:
    if s.llm == "auto":
        return AutoLLM(s)
    if s.llm == "ollama":
        o = OllamaLLM(s.ollama_url, s.llm_model or next((m["name"] for m in list_ollama(s.ollama_url)), "llama3.2:3b")); o.warm(); return o
    if s.llm == "openai_compat" and s.llm_api_key and s.llm_model:
        return OpenAICompatLLM(s)
    if s.llm == "anthropic" and s.llm_api_key and s.llm_model:
        return AnthropicLLM(s)
    return None
