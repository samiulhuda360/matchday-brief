"""Fact sheets: the only material a preview or recap may draw on.

Every number a summary is allowed to use appears in its fact sheet, so the grounding check can
verify a summary against the sheet alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Match
from .stats import Row, meetings, ordinal, row_for, standings, unbeaten_run, venue_record


@dataclass(frozen=True)
class Fact:
    key: str
    label: str
    value: str


@dataclass
class FactSheet:
    kind: str  # "preview" or "recap"
    match_id: str
    league: str
    home: str
    away: str
    facts: list[Fact] = field(default_factory=list)

    def add(self, key: str, label: str, value: object) -> None:
        self.facts.append(Fact(key, label, str(value)))

    def get(self, key: str) -> str:
        return next(f.value for f in self.facts if f.key == key)

    def has(self, key: str) -> bool:
        return any(f.key == key for f in self.facts)

    @property
    def teams(self) -> set[str]:
        return {self.home, self.away}

    def text(self) -> str:
        return "\n".join(f"- {f.label}: {f.value}" for f in self.facts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "match_id": self.match_id,
            "league": self.league,
            "home": self.home,
            "away": self.away,
            "facts": [f.__dict__ for f in self.facts],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactSheet:
        sheet = cls(data["kind"], data["match_id"], data["league"], data["home"], data["away"])
        sheet.facts = [Fact(**f) for f in data["facts"]]
        return sheet


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"


def _form_text(form: list[str]) -> str:
    if not form:
        return "no matches yet"
    wins, draws, losses = form.count("W"), form.count("D"), form.count("L")
    return f"{' '.join(form)} ({_plural(wins, 'win')}, {_plural(draws, 'draw')}, {_plural(losses, 'loss', 'losses')})"


def _signed(n: int) -> str:
    return f"+{n}" if n > 0 else str(n)


def _team_facts(sheet: FactSheet, side: str, row: Row, teams: int) -> None:
    sheet.add(f"{side}_position", f"{row.team} league position", f"{ordinal(row.position)} of {teams}")
    sheet.add(f"{side}_points", f"{row.team} points", f"{row.points} from {_plural(row.played, 'match', 'matches')}")
    sheet.add(f"{side}_record", f"{row.team} record", f"{row.won} won, {row.drawn} drawn, {row.lost} lost")
    sheet.add(
        f"{side}_goals",
        f"{row.team} goals",
        f"{row.scored} scored, {row.conceded} conceded, goal difference {_signed(row.goal_difference)}",
    )
    sheet.add(f"{side}_form", f"{row.team} last five results (oldest first)", _form_text(row.form))


def preview_facts(matches: list[Match], match: Match) -> FactSheet:
    """Facts for an upcoming fixture, using only results before kickoff."""
    sheet = FactSheet("preview", match.id, match.league, match.home, match.away)
    table = standings(matches, cutoff=match.kickoff)
    home, away = row_for(table, match.home), row_for(table, match.away)
    sheet.add("fixture", "Fixture", f"{match.home} (home) vs {match.away} (away)")
    sheet.add("competition", "Competition", f"{match.league}, {match.round}")
    sheet.add("kickoff", "Kick-off", f"{match.kickoff:%A} {match.kickoff.day} {match.kickoff:%B %Y, %H:%M}")
    _team_facts(sheet, "home", home, len(table))
    _team_facts(sheet, "away", away, len(table))
    at_home = venue_record(matches, match.home, True, match.kickoff)
    on_road = venue_record(matches, match.away, False, match.kickoff)
    sheet.add(
        "home_venue", f"{match.home} home record", f"{at_home.won} won, {at_home.drawn} drawn, {at_home.lost} lost"
    )
    sheet.add(
        "away_venue", f"{match.away} away record", f"{on_road.won} won, {on_road.drawn} drawn, {on_road.lost} lost"
    )
    gap = abs(home.points - away.points)
    if gap:
        leader = match.home if home.points > away.points else match.away
        sheet.add("points_gap", "Points gap", f"{leader} lead by {_plural(gap, 'point')}")
    else:
        sheet.add("points_gap", "Points gap", "level on points")
    previous = meetings(matches, match.home, match.away, match.kickoff)
    if previous:
        last = previous[-1]
        assert last.ft is not None
        sheet.add(
            "last_meeting",
            "Last meeting this season",
            f"{last.home} {last.ft[0]}-{last.ft[1]} {last.away} on {last.kickoff.day} {last.kickoff:%B}",
        )
    else:
        sheet.add("last_meeting", "Last meeting this season", "none, this is the first meeting")
    return sheet


def recap_facts(matches: list[Match], match: Match) -> FactSheet:
    """Facts for a played match, with the table as it stood straight after it."""
    assert match.ft is not None
    sheet = FactSheet("recap", match.id, match.league, match.home, match.away)
    h, a = match.ft
    sheet.add("final_score", "Final score", f"{match.home} {h}-{a} {match.away}")
    if match.ht is not None:
        sheet.add("half_time", "Half-time score", f"{match.home} {match.ht[0]}-{match.ht[1]} {match.away}")
        sheet.add(
            "second_half",
            "Second-half goals",
            f"{match.home} {h - match.ht[0]}, {match.away} {a - match.ht[1]}",
        )
    if h == a:
        sheet.add("result", "Result", "draw")
    else:
        winner, loser = (match.home, match.away) if h > a else (match.away, match.home)
        sheet.add("result", "Result", f"{winner} beat {loser}")
        sheet.add("margin", "Winning margin", _plural(abs(h - a), "goal"))
        if match.ht is not None and (match.ht[0] - match.ht[1]) * (h - a) < 0:
            sheet.add("comeback", "Comeback", f"{winner} were behind at half-time and won")
    sheet.add("total_goals", "Total goals", h + a)
    sheet.add("date", "Date", f"{match.kickoff:%A} {match.kickoff.day} {match.kickoff:%B %Y}")
    sheet.add("competition", "Competition", f"{match.league}, {match.round}")
    before = standings(matches, cutoff=match.kickoff)
    after = standings(matches, cutoff=match.kickoff, inclusive=True)
    teams = len(after)
    for side, team in (("home", match.home), ("away", match.away)):
        old, new = row_for(before, team), row_for(after, team)
        move = (
            "no change"
            if old.position == new.position
            else f"{'up' if new.position < old.position else 'down'} from {ordinal(old.position)}"
        )
        sheet.add(
            f"{side}_position",
            f"{team} league position after the match",
            f"{ordinal(new.position)} of {teams} ({move})",
        )
        sheet.add(f"{side}_points", f"{team} points after the match", f"{new.points} from {new.played} matches")
        sheet.add(f"{side}_form", f"{team} last five results (oldest first)", _form_text(new.form))
        run = unbeaten_run(matches, team, match.kickoff, inclusive=True)
        if run >= 3:
            sheet.add(f"{side}_unbeaten", f"{team} unbeaten run", f"{run} matches")
    return sheet
