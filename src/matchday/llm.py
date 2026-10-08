"""OpenAI-compatible chat client with a disk cache and a minimum gap between calls.

Configured from the environment:
    AI_API_KEY   key for the provider (required to use a model; without it the app uses templates)
    AI_BASE_URL  OpenAI-compatible endpoint (default: the Gemini endpoint below)
    AI_MODEL     model name (default: gemini-flash-lite-latest)
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_MODEL = "gemini-flash-lite-latest"


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        cache_dir: str | Path = ".matchday/llm-cache",
        min_interval: float = 2.5,
    ) -> None:
        from openai import OpenAI  # imported lazily so the app runs without a model

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=2)
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
        self.calls = 0
        self.cache_hits = 0

    @classmethod
    def from_env(cls, cache_dir: str | Path = ".matchday/llm-cache") -> LLMClient | None:
        key = os.environ.get("AI_API_KEY", "").strip()
        if not key:
            return None
        return cls(
            key,
            base_url=os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL),
            model=os.environ.get("AI_MODEL", DEFAULT_MODEL),
            cache_dir=cache_dir,
        )

    def _cache_path(self, payload: dict[str, object]) -> Path:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def complete(self, system: str, user: str, temperature: float = 0.4) -> str:
        payload: dict[str, object] = {"model": self.model, "system": system, "user": user, "temperature": temperature}
        path = self._cache_path(payload)
        if path.exists():
            self.cache_hits += 1
            cached: str = json.loads(path.read_text(encoding="utf-8"))["text"]
            return cached
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                )
            finally:
                self._last_call = time.monotonic()
        self.calls += 1
        text = (response.choices[0].message.content or "").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"text": text}), encoding="utf-8")
        return text
