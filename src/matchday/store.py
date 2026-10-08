"""SQLite storage for matches, written summaries, sent notifications and job runs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from .facts import FactSheet
from .models import Match
from .writer import Summary

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY, league TEXT, round TEXT, kickoff TEXT, home TEXT, away TEXT,
    ft_home INTEGER, ft_away INTEGER, ht_home INTEGER, ht_away INTEGER
);
CREATE TABLE IF NOT EXISTS summaries (
    match_id TEXT, kind TEXT, text TEXT, source TEXT, numbers_total INTEGER, numbers_supported INTEGER,
    report TEXT, facts TEXT, created_at TEXT, PRIMARY KEY (match_id, kind)
);
CREATE TABLE IF NOT EXISTS notifications (
    match_id TEXT, kind TEXT, title TEXT, body TEXT, sent_at TEXT, PRIMARY KEY (match_id, kind)
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT, source TEXT, matches INTEGER, new_results INTEGER,
    previews INTEGER, recaps INTEGER, reminders INTEGER, alerts INTEGER
);
"""


def _pair(a: Any, b: Any) -> tuple[int, int] | None:
    return None if a is None else (int(a), int(b))


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    # matches
    def upsert_matches(self, matches: Iterable[Match]) -> int:
        """Insert or update matches; returns how many gained a result they did not have before."""
        new_results = 0
        for m in matches:
            old = self.db.execute("SELECT ft_home FROM matches WHERE id = ?", (m.id,)).fetchone()
            if m.played and (old is None or old["ft_home"] is None):
                new_results += 1
            self.db.execute(
                "INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    m.id, m.league, m.round, m.kickoff.isoformat(), m.home, m.away,
                    *(m.ft or (None, None)), *(m.ht or (None, None)),
                ),
            )  # fmt: skip
        self.db.commit()
        return new_results

    def matches(self) -> list[Match]:
        rows = self.db.execute("SELECT * FROM matches ORDER BY kickoff, home").fetchall()
        return [
            Match(
                r["league"], r["round"], datetime.fromisoformat(r["kickoff"]), r["home"], r["away"],
                _pair(r["ft_home"], r["ft_away"]), _pair(r["ht_home"], r["ht_away"]),
            )
            for r in rows
        ]  # fmt: skip

    def match(self, match_id: str) -> Match | None:
        return next((m for m in self.matches() if m.id == match_id), None)

    # summaries
    def save_summary(self, sheet: FactSheet, summary: Summary, now: datetime, commit: bool = True) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO summaries VALUES (?,?,?,?,?,?,?,?,?)",
            (
                sheet.match_id, sheet.kind, summary.text, summary.source, summary.report.total,
                summary.report.supported, json.dumps(summary.report.to_dict()), json.dumps(sheet.to_dict()),
                now.isoformat(timespec="seconds"),
            ),
        )  # fmt: skip
        if commit:
            self.db.commit()

    def summary(self, match_id: str, kind: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM summaries WHERE match_id = ? AND kind = ?", (match_id, kind)).fetchone()
        return dict(row) if row else None

    def summaries(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM summaries ORDER BY created_at DESC")]

    def has_summary(self, match_id: str, kind: str) -> bool:
        return self.summary(match_id, kind) is not None

    # notifications
    def was_notified(self, match_id: str, kind: str) -> bool:
        q = "SELECT 1 FROM notifications WHERE match_id = ? AND kind = ?"
        return self.db.execute(q, (match_id, kind)).fetchone() is not None

    def record_notification(self, match_id: str, kind: str, title: str, body: str, now: datetime) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO notifications VALUES (?,?,?,?,?)",
            (match_id, kind, title, body, now.isoformat(timespec="seconds")),
        )
        self.db.commit()

    def notifications(self, limit: int = 20) -> list[dict[str, Any]]:
        q = "SELECT * FROM notifications ORDER BY sent_at DESC, match_id LIMIT ?"
        return [dict(r) for r in self.db.execute(q, (limit,))]

    # job runs
    def record_run(self, ran_at: datetime, source: str, counts: dict[str, int]) -> None:
        self.db.execute(
            "INSERT INTO job_runs (ran_at, source, matches, new_results, previews, recaps, reminders, alerts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                ran_at.isoformat(timespec="seconds"), source, counts["matches"], counts["new_results"],
                counts["previews"], counts["recaps"], counts["reminders"], counts["alerts"],
            ),
        )  # fmt: skip
        self.db.commit()

    def runs(self, limit: int = 10) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT ?", (limit,))]
