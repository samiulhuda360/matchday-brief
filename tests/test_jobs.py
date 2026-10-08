import json
from datetime import timedelta

import pytest

from matchday.jobs import Settings, opening, tick, watch
from matchday.notify import OutboxNotifier, build_notifiers
from matchday.store import Store

from .conftest import DEMO_NOW, SAMPLE, FakeNotifier


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def test_first_tick_writes_and_notifies(store):
    notifier = FakeNotifier()
    counts = tick(store, SAMPLE, DEMO_NOW, [notifier])
    assert counts == {"matches": 56, "new_results": 32, "previews": 4, "recaps": 32, "reminders": 3, "alerts": 4}
    titles = [t for t, _ in notifier.sent]
    assert sum(t.startswith("Reminder:") for t in titles) == 3
    assert "Full time: Westmere Albion 5-1 Harbourside FC" in titles
    assert all(json.loads(s["report"])["grounded"] for s in store.summaries())
    assert len(store.runs()) == 1


def test_second_tick_sends_nothing_new(store):
    tick(store, SAMPLE, DEMO_NOW, [FakeNotifier()])
    notifier = FakeNotifier()
    counts = tick(store, SAMPLE, DEMO_NOW, [notifier])
    assert notifier.sent == []
    assert counts["recaps"] == counts["previews"] == counts["reminders"] == counts["alerts"] == 0


def test_followed_team_filter(store):
    notifier = FakeNotifier()
    tick(store, SAMPLE, DEMO_NOW, [notifier], settings=Settings(teams={"Northfield Rovers"}))
    assert [t for t, _ in notifier.sent] == [
        "Full time: Larchmont Wanderers 1-2 Northfield Rovers",
        "Reminder: Northfield Rovers vs Westmere Albion, Sat 10 Oct, 15:00",
    ]


def test_reminder_window(store):
    counts = tick(store, SAMPLE, DEMO_NOW - timedelta(days=1), [FakeNotifier()], settings=Settings(remind_hours=24))
    assert counts["reminders"] == 0


def test_failing_channel_does_not_stop_others(store):
    class Broken:
        name = "broken"

        def send(self, title, body):
            raise OSError("down")

    good = FakeNotifier()
    counts = tick(store, SAMPLE, DEMO_NOW, [Broken(), good])
    assert len(good.sent) == counts["reminders"] + counts["alerts"] > 0


def test_outbox_and_channel_config(tmp_path, monkeypatch):
    path = tmp_path / "out.jsonl"
    OutboxNotifier(path).send("t", "b")
    assert json.loads(path.read_text()) == {"title": "t", "body": "b"}
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        build_notifiers("telegram")
    with pytest.raises(SystemExit):
        build_notifiers("pigeon")
    assert [n.name for n in build_notifiers("console,outbox", outbox=path)] == ["console", "outbox"]


def test_opening_and_watch():
    assert opening("One. Two. Three.") == "One. Two."
    runs: list[int] = []

    def once() -> dict[str, int]:
        runs.append(1)
        return {}

    watch(once, every_seconds=0, max_runs=3)
    assert len(runs) == 3
