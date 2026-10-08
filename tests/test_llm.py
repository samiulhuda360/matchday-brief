from types import SimpleNamespace

from matchday import llm
from matchday.llm import LLMClient


class FakeCompletions:
    def __init__(self) -> None:
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        message = SimpleNamespace(content=f"reply {self.calls}")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make(tmp_path, interval=2.5):
    client = LLMClient("test-key-not-real", cache_dir=tmp_path, min_interval=interval)
    fake = FakeCompletions()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return client, fake


def test_from_env_without_key_returns_none(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert LLMClient.from_env() is None


def test_disk_cache_avoids_second_call(tmp_path):
    client, fake = make(tmp_path, interval=0)
    assert client.complete("sys", "user") == "reply 1"
    assert client.complete("sys", "user") == "reply 1"
    assert fake.calls == 1 and client.cache_hits == 1
    again, fake2 = make(tmp_path, interval=0)
    assert again.complete("sys", "user") == "reply 1" and fake2.calls == 0


def test_calls_are_spaced(tmp_path, monkeypatch):
    clock = {"t": 100.0}
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    client, _ = make(tmp_path)
    client.complete("sys", "one")
    clock["t"] += 1.0
    client.complete("sys", "two")
    assert slept == [1.5]
