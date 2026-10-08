"""The scheduled job. One `tick` refreshes the data and does everything that has become due."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .facts import preview_facts, recap_facts
from .ingest import load_matches
from .models import Match
from .notify import Notifier
from .store import Store
from .writer import GroundedWriter, Model

log = logging.getLogger(__name__)


@dataclass
class Settings:
    preview_days: int = 7  # write previews for fixtures within this many days
    remind_hours: int = 48  # send a reminder once a followed team's kick-off is this close
    alert_days: int = 7  # send result alerts for matches played within this many days
    teams: set[str] = field(default_factory=set)  # followed teams; empty means all

    def follows(self, match: Match) -> bool:
        return not self.teams or match.home in self.teams or match.away in self.teams


def opening(text: str, sentences: int = 2) -> str:
    """The first sentences of a summary, for a notification body."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:sentences])


def tick(
    store: Store,
    source: str,
    now: datetime,
    notifiers: Iterable[Notifier],
    model: Model | None = None,
    settings: Settings | None = None,
) -> dict[str, int]:
    settings = settings or Settings()
    notifiers = list(notifiers)
    new_results = store.upsert_matches(load_matches(source))
    matches = store.matches()
    writer = GroundedWriter(model, league_teams={t for m in matches for t in (m.home, m.away)})
    counts = {
        "matches": len(matches),
        "new_results": new_results,
        "previews": 0,
        "recaps": 0,
        "reminders": 0,
        "alerts": 0,
    }

    for m in matches:
        if m.played and not store.has_summary(m.id, "recap"):
            sheet = recap_facts(matches, m)
            store.save_summary(sheet, writer.write(sheet), now, commit=False)
            counts["recaps"] += 1
        elif not m.played and now <= m.kickoff <= now + timedelta(days=settings.preview_days):
            if not store.has_summary(m.id, "preview"):
                sheet = preview_facts(matches, m)
                store.save_summary(sheet, writer.write(sheet), now, commit=False)
                counts["previews"] += 1

    store.db.commit()

    def notify(match: Match, kind: str, title: str, body: str) -> None:
        for n in notifiers:
            try:
                n.send(title, body)
            except Exception as exc:  # one failing channel must not stop the others
                log.warning("%s notifier failed: %s", n.name, type(exc).__name__)
        store.record_notification(match.id, kind, title, body, now)

    for m in matches:
        if not settings.follows(m):
            continue
        due_reminder = not m.played and now <= m.kickoff <= now + timedelta(hours=settings.remind_hours)
        due_alert = m.played and now - timedelta(days=settings.alert_days) <= m.kickoff <= now
        if due_reminder and not store.was_notified(m.id, "reminder"):
            preview = store.summary(m.id, "preview")
            when = f"{m.kickoff:%a} {m.kickoff.day} {m.kickoff:%b, %H:%M}"
            body = opening(preview["text"]) if preview else m.round
            notify(m, "reminder", f"Reminder: {m.home} vs {m.away}, {when}", body)
            counts["reminders"] += 1
        elif due_alert and m.ft is not None and not store.was_notified(m.id, "result"):
            recap = store.summary(m.id, "recap")
            body = opening(recap["text"]) if recap else m.round
            notify(m, "result", f"Full time: {m.home} {m.ft[0]}-{m.ft[1]} {m.away}", body)
            counts["alerts"] += 1

    store.record_run(now, source, counts)
    return counts


def watch(run_once: Callable[[], dict[str, int]], every_seconds: float, max_runs: int | None = None) -> None:
    """Run `run_once` on a fixed interval (a minimal scheduler for a server or a container)."""
    runs = 0
    while max_runs is None or runs < max_runs:
        started = time.monotonic()
        try:
            log.info("tick: %s", run_once())
        except Exception:
            log.exception("tick failed")
        runs += 1
        if max_runs is not None and runs >= max_runs:
            break
        time.sleep(max(0.0, every_seconds - (time.monotonic() - started)))
