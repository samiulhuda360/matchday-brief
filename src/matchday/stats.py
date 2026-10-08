"""League table, form and records, computed from match results up to a point in time."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from .models import Match


@dataclass
class Record:
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    scored: int = 0
    conceded: int = 0

    @property
    def points(self) -> int:
        return 3 * self.won + self.drawn

    @property
    def goal_difference(self) -> int:
        return self.scored - self.conceded

    def add(self, match: Match, team: str) -> None:
        scored, conceded = match.goals_for(team)
        self.played += 1
        self.scored += scored
        self.conceded += conceded
        outcome = match.outcome_for(team)
        if outcome == "W":
            self.won += 1
        elif outcome == "D":
            self.drawn += 1
        else:
            self.lost += 1


@dataclass
class Row(Record):
    team: str = ""
    position: int = 0
    form: list[str] = field(default_factory=list)  # oldest first, last five


def played_before(matches: Iterable[Match], cutoff: datetime | None, inclusive: bool = False) -> list[Match]:
    """Played matches with kickoff before (or at, if inclusive) the cutoff, oldest first."""
    out = [
        m for m in matches if m.played and (cutoff is None or m.kickoff < cutoff or (inclusive and m.kickoff == cutoff))
    ]
    return sorted(out, key=lambda m: m.kickoff)


def standings(matches: Iterable[Match], cutoff: datetime | None = None, inclusive: bool = False) -> list[Row]:
    """The table: points, then goal difference, then goals scored, then name."""
    all_matches = list(matches)
    rows: dict[str, Row] = {}
    for m in all_matches:
        for team in (m.home, m.away):
            rows.setdefault(team, Row(team=team))
    for m in played_before(all_matches, cutoff, inclusive):
        for team in (m.home, m.away):
            row = rows[team]
            row.add(m, team)
            row.form = [*row.form, m.outcome_for(team)][-5:]
    table = sorted(rows.values(), key=lambda r: (-r.points, -r.goal_difference, -r.scored, r.team))
    for i, row in enumerate(table, start=1):
        row.position = i
    return table


def row_for(table: list[Row], team: str) -> Row:
    return next(r for r in table if r.team == team)


def venue_record(matches: Iterable[Match], team: str, at_home: bool, cutoff: datetime | None) -> Record:
    record = Record()
    for m in played_before(matches, cutoff):
        if (at_home and m.home == team) or (not at_home and m.away == team):
            record.add(m, team)
    return record


def meetings(matches: Iterable[Match], a: str, b: str, cutoff: datetime | None) -> list[Match]:
    return [m for m in played_before(matches, cutoff) if {m.home, m.away} == {a, b}]


def unbeaten_run(matches: Iterable[Match], team: str, cutoff: datetime | None, inclusive: bool = False) -> int:
    """Consecutive matches without defeat, counting back from the most recent."""
    run = 0
    for m in reversed([m for m in played_before(matches, cutoff, inclusive) if m.involves(team)]):
        if m.outcome_for(team) == "L":
            break
        run += 1
    return run


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
