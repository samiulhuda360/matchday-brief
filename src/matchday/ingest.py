"""Load fixtures and results in the openfootball JSON format, from a file or a URL.

openfootball (github.com/openfootball/football.json) publishes free, public-domain fixture and
result files for many leagues; the bundled sample league uses the same shape:

    {"name": "...", "matches": [{"round": "...", "date": "2026-10-10", "time": "15:00",
      "team1": "Home", "team2": "Away", "score": {"ht": [1, 0], "ft": [2, 1]}}]}
"""

from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Match

USER_AGENT = "matchday-brief/1.0 (+fixtures tracker)"


def read_source(source: str, timeout: float = 20.0) -> dict[str, Any]:
    """Read a JSON document from a local path or an http(s) URL."""
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})  # noqa: S310
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - http(s) only
            data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
            return data
    loaded: dict[str, Any] = json.loads(Path(source).read_text(encoding="utf-8"))
    return loaded


def _pair(value: Any) -> tuple[int, int] | None:
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value):
        return (value[0], value[1])
    return None


def _kickoff(raw: dict[str, Any]) -> datetime:
    day = datetime.strptime(str(raw["date"]), "%Y-%m-%d")
    clock = re.match(r"(\d{1,2}):(\d{2})", str(raw.get("time", "")))
    if clock:
        return day.replace(hour=int(clock.group(1)), minute=int(clock.group(2)))
    return day.replace(hour=15)


def parse_openfootball(doc: dict[str, Any], league: str | None = None) -> list[Match]:
    """Turn an openfootball document into Match objects, sorted by kickoff."""
    name = league or str(doc.get("name", "League"))
    matches: list[Match] = []
    for raw in doc.get("matches", []):
        score = raw.get("score") or {}
        ft = _pair(score.get("ft"))
        if ft is None and isinstance(raw.get("score1"), int) and isinstance(raw.get("score2"), int):
            ft = (raw["score1"], raw["score2"])  # older openfootball files
        matches.append(
            Match(
                league=name,
                round=str(raw.get("round", "")),
                kickoff=_kickoff(raw),
                home=str(raw["team1"]),
                away=str(raw["team2"]),
                ft=ft,
                ht=_pair(score.get("ht")) if ft else None,
            )
        )
    return sorted(matches, key=lambda m: (m.kickoff, m.home))


def load_matches(source: str, league: str | None = None) -> list[Match]:
    return parse_openfootball(read_source(source), league)
