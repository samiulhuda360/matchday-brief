"""Grounding check: every number in a summary must come from its fact sheet.

The checker pulls numeric claims out of the summary (digits, decimals, percentages, ordinals such
as "3rd", clock times, scorelines such as "2-1", and number words from "two" to "twenty") and looks
each one up in the numbers found in the fact sheet by the same extractor. A scoreline must match a
scoreline in the sheet as a pair, so "5-0" is flagged even if 5 and 0 appear separately. Any team
from the league that is not part of this fixture is flagged too.

Claims are typed where the wording allows it: a position ("4th", "third", "second place") must match
a league position in the sheet, and a number followed by "points" must match a points total or gap,
so a wrong value that happens to appear elsewhere in the sheet is still caught. "one" is not treated
as a number, and "first" and "second" count only next to a place word, because in match reports they
are nearly always ordinary words ("one of the best", "the first half").
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .facts import FactSheet

WORDS = {
    "zero": 0, "nil": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}  # fmt: skip
WORD_ORDINALS = {
    "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
}  # fmt: skip

_WORD_ALT = "|".join(sorted([*WORDS, *WORD_ORDINALS], key=len, reverse=True))
TOKEN = re.compile(
    r"(?P<date>\b\d{4}-\d{2}-\d{2}\b)"
    r"|(?P<time>\b\d{1,2}:\d{2}\b)"
    r"|(?P<score>(?<![\d.])\d{1,2}\s?[-\u2013]\s?\d{1,2}(?![\d:]|\.\d))"
    r"|(?P<ordinal>\b\d+(?:st|nd|rd|th)\b)"
    r"|(?P<number>(?<![\w.])[+\-\u2212]?\d+(?:[.,]\d+)?%?)"
    rf"|(?P<word>\b(?:{_WORD_ALT})\b)",
    re.IGNORECASE,
)


MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
POINTS_AFTER = re.compile(r"[\s-]*(?:points?|pts)\b", re.IGNORECASE)
MONTH_AFTER = re.compile(rf"\s*(?:of\s+)?(?:{MONTHS})\b", re.IGNORECASE)
COUNT_AFTER = re.compile(
    r"\s+(?:(?:straight|consecutive|successive|league|home|away)\s+)?"
    r"(?:defeats?|loss(?:es)?|wins?|victor(?:y|ies)|draws?|games?|matches|clean sheets?|in a row)\b",
    re.IGNORECASE,
)
PLACE_WORD = re.compile(r"\b(first|second)(?=\s+(?:place|position|spot|in the table)\b)", re.IGNORECASE)


@dataclass(frozen=True)
class Claim:
    text: str
    kind: str  # number, ordinal, word, score, time, date
    values: tuple[float, ...]
    start: int
    end: int
    unit: str = ""  # "position" for ordinals, "points" for a number followed by "points"


@dataclass
class CheckedClaim:
    claim: Claim
    grounded: bool


@dataclass
class Report:
    claims: list[CheckedClaim] = field(default_factory=list)
    stray_teams: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.claims)

    @property
    def supported(self) -> int:
        return sum(c.grounded for c in self.claims)

    @property
    def unsupported(self) -> list[str]:
        return [c.claim.text for c in self.claims if not c.grounded]

    @property
    def grounded(self) -> bool:
        return not self.unsupported and not self.stray_teams

    def to_dict(self) -> dict[str, object]:
        return {
            "grounded": self.grounded,
            "numbers_total": self.total,
            "numbers_supported": self.supported,
            "unsupported": self.unsupported,
            "stray_teams": self.stray_teams,
        }


def _num(text: str) -> float:
    """Absolute value of a numeric token; a sign is wording ("+8", "-3"), not a different number."""
    return float(text.strip("+-\u2212%").replace(",", ""))


def extract(text: str) -> list[Claim]:
    claims: list[Claim] = []
    for m in TOKEN.finditer(text):
        kind = m.lastgroup or "number"
        raw = m.group(0)
        if kind == "date":
            values: tuple[float, ...] = tuple(float(p) for p in raw.split("-"))
        elif kind == "time":
            values = tuple(float(p) for p in raw.split(":"))
        elif kind == "score":
            a, b = re.split(r"\s?[-\u2013]\s?", raw)
            values = (float(a), float(b))
        elif kind == "ordinal":
            values = (float(re.match(r"\d+", raw).group(0)),)  # type: ignore[union-attr]
        elif kind == "word":
            word = raw.lower()
            values = (float(WORDS.get(word, WORD_ORDINALS.get(word, 0))),)
        else:
            values = (_num(raw),)
        after = text[m.end() : m.end() + 24]
        unit = ""
        if kind == "ordinal" or (kind == "word" and raw.lower() in WORD_ORDINALS):
            # "3rd October" is a date and "fourth defeat" is a count, not a league position
            unit = "" if MONTH_AFTER.match(after) or COUNT_AFTER.match(after) else "position"
        elif kind in ("number", "word") and POINTS_AFTER.match(after):
            unit = "points"
        claims.append(Claim(raw, kind, values, m.start(), m.end(), unit))
    for m in PLACE_WORD.finditer(text):  # "second place": only counted as a number next to a place word
        claims.append(
            Claim(m.group(0), "word", (1.0 if m.group(0).lower() == "first" else 2.0,), m.start(), m.end(), "position")
        )
    return sorted(claims, key=lambda c: c.start)


class Evidence:
    """The numbers, scorelines and times a fact sheet supports."""

    def __init__(self, sheet: FactSheet) -> None:
        self.numbers: set[float] = set()
        self.scores: set[tuple[float, float]] = set()
        self.times: set[tuple[float, ...]] = set()
        self.typed: dict[str, set[float]] = {"position": set(), "points": set()}
        for fact in sheet.facts:
            lead = extract(fact.value)
            if fact.key.endswith("_points") and lead:
                self.typed["points"].add(lead[0].values[0])
        for claim in extract(sheet.text()):
            self.numbers.update(claim.values)
            if claim.unit:
                self.typed[claim.unit].update(claim.values)
            if claim.kind == "score":
                self.scores.add((min(claim.values), max(claim.values)))
            if claim.kind == "time":
                self.times.add(claim.values)

    def has_number(self, value: float) -> bool:
        return any(math.isclose(value, n, abs_tol=1e-9) for n in self.numbers)

    def supports(self, claim: Claim) -> bool:
        if claim.kind == "score":
            return (min(claim.values), max(claim.values)) in self.scores
        if claim.kind == "time":
            return claim.values in self.times
        if claim.unit:
            return all(any(math.isclose(v, n) for n in self.typed[claim.unit]) for v in claim.values)
        return all(self.has_number(v) for v in claim.values)


def check(summary: str, sheet: FactSheet, league_teams: Iterable[str] = ()) -> Report:
    evidence = Evidence(sheet)
    report = Report([CheckedClaim(c, evidence.supports(c)) for c in extract(summary)])
    lowered = summary.lower()
    report.stray_teams = sorted(
        t for t in set(league_teams) - sheet.teams if re.search(rf"\b{re.escape(t.lower())}\b", lowered)
    )
    return report


def highlight(summary: str, report: Report) -> str:
    """HTML with each numeric claim wrapped in a span marked supported or unsupported."""
    out: list[str] = []
    cursor = 0
    for checked in sorted(report.claims, key=lambda c: c.claim.start):
        c = checked.claim
        out.append(html.escape(summary[cursor : c.start]))
        css = "ok" if checked.grounded else "bad"
        tip = "found in the fact sheet" if checked.grounded else "not in the fact sheet"
        out.append(f'<mark class="{css}" title="{tip}">{html.escape(c.text)}</mark>')
        cursor = c.end
    out.append(html.escape(summary[cursor:]))
    return "".join(out)
