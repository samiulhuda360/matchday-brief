"""Preview and recap writers.

`TemplateWriter` builds sentences straight from fact values, so it is grounded by construction.
`LLMWriter` asks a model for livelier prose. `GroundedWriter` runs the model, checks every number,
gives the model one retry with the unsupported numbers listed, and falls back to the template if
the text still is not grounded. Nothing ungrounded is ever stored or sent.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from .facts import FactSheet
from .grounding import Report, check

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You write short football match {kind}s for a fan newsletter. Use only the facts provided. "
    "Every number you write (scores, points, positions, dates, times, counts) must appear in the facts "
    "exactly as given; do not calculate new numbers such as differences or averages, and do not "
    "mention any team other than the two in the fixture. No betting advice, no predictions of an "
    "exact score, no links. You do not need every fact: pick the ones that tell the story, and write "
    "like a sports writer rather than a list. 70 to 110 words of plain prose, one or two paragraphs, no headings."
)


class Model(Protocol):
    def complete(self, system: str, user: str, temperature: float = 0.4) -> str: ...


@dataclass
class Summary:
    text: str
    source: str  # "template", "model" or "model-retry"
    report: Report
    attempts: int
    first_report: Report | None = None  # the model's first draft, before any retry
    first_text: str = ""


def _lead(value: str) -> str:
    """First clause of a fact value, e.g. '15 from 8 matches' -> '15'."""
    return value.split(" from ")[0].split(" (")[0]


class TemplateWriter:
    def write(self, sheet: FactSheet) -> str:
        return self._preview(sheet) if sheet.kind == "preview" else self._recap(sheet)

    def _preview(self, s: FactSheet) -> str:
        home, away = s.home, s.away
        parts = [
            f"{home} host {away} on {s.get('kickoff')} ({s.get('competition').split(', ')[-1]}).",
            f"{home} are {_lead(s.get('home_position'))} with {_lead(s.get('home_points'))} points "
            f"({s.get('home_record')}), and {away} are {_lead(s.get('away_position'))} with "
            f"{_lead(s.get('away_points'))} points ({s.get('away_record')}).",
            f"Points gap: {s.get('points_gap')}.",
            f"Recent form reads {s.get('home_form').split(' (')[0]} for {home} and "
            f"{s.get('away_form').split(' (')[0]} for {away}.",
            f"At home {home} have {s.get('home_venue')}; on the road {away} have {s.get('away_venue')}.",
            f"Last meeting this season: {s.get('last_meeting')}.",
        ]
        return " ".join(parts)

    def _recap(self, s: FactSheet) -> str:
        parts = [f"{s.get('final_score')} ({s.get('competition').split(', ')[-1]}, {s.get('date')})."]
        if s.has("half_time"):
            parts.append(
                f"It was {s.get('half_time').replace(s.home + ' ', '').replace(' ' + s.away, '')} at half-time."
            )
        if s.has("comeback"):
            parts.append(f"{s.get('comeback')}.")
        parts.append(
            f"{s.home} are now {s.get('home_position')} on {_lead(s.get('home_points'))} points; "
            f"{s.away} are {s.get('away_position')} on {_lead(s.get('away_points'))} points."
        )
        for side, team in (("home", s.home), ("away", s.away)):
            if s.has(f"{side}_unbeaten"):
                parts.append(f"{team} are unbeaten in {s.get(f'{side}_unbeaten')}.")
        return " ".join(parts)


class LLMWriter:
    def __init__(self, model: Model) -> None:
        self.model = model

    def write(self, sheet: FactSheet, feedback: Iterable[str] = ()) -> str:
        user = f"Facts:\n{sheet.text()}\n\nWrite the {sheet.kind}."
        bad = list(feedback)
        if bad:
            user += (
                "\n\nYour previous draft used these numbers or teams that are not in the facts: "
                + ", ".join(bad)
                + ". Rewrite it using only values that appear in the facts."
            )
        text = self.model.complete(SYSTEM_PROMPT.format(kind=sheet.kind), user)
        return re.sub(r"\s+\n", "\n", text).strip()


class GroundedWriter:
    def __init__(self, model: Model | None, league_teams: Iterable[str] = (), retries: int = 1) -> None:
        self.llm = LLMWriter(model) if model is not None else None
        self.template = TemplateWriter()
        self.league_teams = set(league_teams)
        self.retries = retries

    def write(self, sheet: FactSheet) -> Summary:
        first: Report | None = None
        first_text = ""
        attempts = 0
        if self.llm is not None:
            feedback: list[str] = []
            for attempt in range(1 + self.retries):
                attempts += 1
                try:
                    text = self.llm.write(sheet, feedback)
                except Exception as exc:  # network or quota errors fall back to the template
                    log.warning("model call failed (%s); using the template", type(exc).__name__)
                    break
                report = check(text, sheet, self.league_teams)
                if first is None:
                    first, first_text = report, text
                if text and report.grounded:
                    source = "model" if attempt == 0 else "model-retry"
                    return Summary(text, source, report, attempts, first, first_text)
                feedback = report.unsupported + report.stray_teams
        text = self.template.write(sheet)
        return Summary(text, "template", check(text, sheet, self.league_teams), attempts, first, first_text)
