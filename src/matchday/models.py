"""Plain data types shared by every module."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass(frozen=True)
class Match:
    """One fixture. `ft` and `ht` are (home, away) goals and are None until the match is played."""

    league: str
    round: str
    kickoff: datetime
    home: str
    away: str
    ft: tuple[int, int] | None = None
    ht: tuple[int, int] | None = None

    @property
    def id(self) -> str:
        return f"{self.kickoff:%Y-%m-%d}-{slug(self.home)}-{slug(self.away)}"

    @property
    def played(self) -> bool:
        return self.ft is not None

    def involves(self, team: str) -> bool:
        return team in (self.home, self.away)

    def goals_for(self, team: str) -> tuple[int, int]:
        """(scored, conceded) for `team`. Only valid for a played match."""
        assert self.ft is not None
        home, away = self.ft
        return (home, away) if team == self.home else (away, home)

    def outcome_for(self, team: str) -> str:
        """'W', 'D' or 'L' from `team`'s point of view."""
        scored, conceded = self.goals_for(team)
        return "W" if scored > conceded else "L" if scored < conceded else "D"
