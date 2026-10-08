from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from matchday.ingest import load_matches
from matchday.models import Match

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = str(ROOT / "data" / "acme-valley-league.json")
DEMO_NOW = datetime(2026, 10, 8, 18, 0)


@pytest.fixture(autouse=True)
def no_model_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never call a model."""
    monkeypatch.delenv("AI_API_KEY", raising=False)


@pytest.fixture
def sample() -> list[Match]:
    return load_matches(SAMPLE)


@pytest.fixture
def by_id(sample: list[Match]) -> dict[str, Match]:
    return {m.id: m for m in sample}


class FakeNotifier:
    name = "fake"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, title: str, body: str) -> None:
        self.sent.append((title, body))


class ScriptedModel:
    """Returns queued replies in order; raises if a reply is an exception."""

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, system: str, user: str, temperature: float = 0.4) -> str:
        self.prompts.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
