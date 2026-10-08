from datetime import datetime

from matchday.models import Match
from matchday.stats import meetings, ordinal, standings, unbeaten_run, venue_record


def m(day: int, home: str, away: str, ft: tuple[int, int] | None) -> Match:
    return Match("L", "R", datetime(2026, 8, day, 15), home, away, ft)


MATCHES = [
    m(1, "A", "B", (2, 0)),
    m(1, "C", "D", (1, 1)),
    m(8, "B", "C", (3, 1)),
    m(8, "D", "A", (0, 0)),
    m(15, "A", "C", None),
]


def test_table_points_and_tiebreaks():
    table = standings(MATCHES)
    assert [r.team for r in table] == ["A", "B", "D", "C"]
    a = table[0]
    assert (a.played, a.won, a.drawn, a.lost, a.points, a.goal_difference) == (2, 1, 1, 0, 4, 2)
    assert table[1].points == 3 and table[1].goal_difference == 0
    assert [r.position for r in table] == [1, 2, 3, 4]
    assert a.form == ["W", "D"]


def test_cutoff_excludes_later_results():
    table = standings(MATCHES, cutoff=datetime(2026, 8, 8, 15))
    assert {r.team: r.played for r in table} == {"A": 1, "B": 1, "C": 1, "D": 1}
    table = standings(MATCHES, cutoff=datetime(2026, 8, 8, 15), inclusive=True)
    assert all(r.played == 2 for r in table)


def test_records_meetings_and_runs():
    assert venue_record(MATCHES, "A", True, None).won == 1
    assert venue_record(MATCHES, "A", False, None).drawn == 1
    assert len(meetings(MATCHES, "B", "A", None)) == 1
    assert unbeaten_run(MATCHES, "A", None) == 2
    assert unbeaten_run(MATCHES, "C", None) == 0


def test_ordinals():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101)] == [
        "1st",
        "2nd",
        "3rd",
        "4th",
        "11th",
        "12th",
        "13th",
        "21st",
        "22nd",
        "101st",
    ]
