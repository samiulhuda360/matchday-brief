"""Generate the bundled sample league: a fictional eight-team season in openfootball JSON format.

The output is deterministic (fixed seed), so tests and screenshots are stable. Rounds dated before
SEASON_CUTOFF get final scores; later rounds are left as upcoming fixtures.

    python tools/make_sample.py data/acme-valley-league.json
"""

from __future__ import annotations

import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

TEAMS = {
    # name: (attack, defence) strength, 1.0 = average
    "Northfield Rovers": (1.35, 0.80),
    "Harbourside FC": (1.25, 0.90),
    "Copperhill Town": (1.10, 0.95),
    "Eastvale United": (1.05, 1.05),
    "Millbrook Athletic": (0.95, 1.00),
    "Stonebridge City": (0.90, 1.10),
    "Westmere Albion": (0.85, 1.15),
    "Larchmont Wanderers": (0.75, 1.25),
}
FIRST_ROUND = date(2026, 8, 15)  # a Saturday
SEASON_CUTOFF = date(2026, 10, 8)  # rounds before this date are played
SEED = 42


def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def round_robin(teams: list[str]) -> list[list[tuple[str, str]]]:
    """Circle method with alternating home sides; the second half reverses every fixture."""
    names = list(teams)
    rounds: list[list[tuple[str, str]]] = []
    for r in range(len(names) - 1):
        pairs = []
        for i in range(len(names) // 2):
            a, b = names[i], names[-1 - i]
            home_first = (r % 2 == 0) if i == 0 else (i % 2 == 1)
            pairs.append((a, b) if home_first else (b, a))
        rounds.append(pairs)
        names = [names[0], names[-1], *names[1:-1]]
    return rounds + [[(b, a) for a, b in rnd] for rnd in rounds]


def build() -> dict[str, object]:
    rng = random.Random(SEED)
    matches: list[dict[str, object]] = []
    for n, pairs in enumerate(round_robin(list(TEAMS)), start=1):
        saturday = FIRST_ROUND + timedelta(weeks=n - 1)
        for i, (home, away) in enumerate(pairs):
            day, time = (saturday, "15:00") if i < 3 else (saturday + timedelta(days=1), "14:00")
            match: dict[str, object] = {
                "round": f"Matchday {n}",
                "date": day.isoformat(),
                "time": time,
                "team1": home,
                "team2": away,
            }
            if day < SEASON_CUTOFF:
                att_h, def_h = TEAMS[home]
                att_a, def_a = TEAMS[away]
                ft_h = poisson(rng, 1.45 * att_h * def_a)
                ft_a = poisson(rng, 1.15 * att_a * def_h)
                ht_h = sum(rng.random() < 0.45 for _ in range(ft_h))
                ht_a = sum(rng.random() < 0.45 for _ in range(ft_a))
                match["score"] = {"ht": [ht_h, ht_a], "ft": [ft_h, ft_a]}
            matches.append(match)
    return {"name": "Acme Valley League 2026/27", "matches": matches}


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/acme-valley-league.json")
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
