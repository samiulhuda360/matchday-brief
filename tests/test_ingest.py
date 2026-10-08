from datetime import datetime

from matchday.ingest import parse_openfootball


def test_sample_league_shape(sample):
    assert len(sample) == 56
    assert sum(m.played for m in sample) == 32
    assert len({m.id for m in sample}) == 56
    assert sample == sorted(sample, key=lambda m: (m.kickoff, m.home))


def test_parses_scores_times_and_older_format():
    doc = {
        "name": "Test League",
        "matches": [
            {
                "round": "R1",
                "date": "2026-08-01",
                "time": "19:45 UTC+1",
                "team1": "A",
                "team2": "B",
                "score": {"ht": [1, 0], "ft": [2, 1]},
            },
            {"round": "R1", "date": "2026-08-02", "team1": "C", "team2": "D", "score1": 0, "score2": 3},
            {"round": "R2", "date": "2026-08-09", "time": "15:00", "team1": "B", "team2": "C"},
        ],
    }
    a, c, b = parse_openfootball(doc)
    assert a.kickoff == datetime(2026, 8, 1, 19, 45) and a.ft == (2, 1) and a.ht == (1, 0)
    assert c.ft == (0, 3) and c.ht is None and c.kickoff.hour == 15
    assert not b.played and b.ft is None
    assert a.league == "Test League"
    assert a.id == "2026-08-01-a-b"


def test_outcome_from_each_side():
    (m,) = parse_openfootball(
        {"matches": [{"date": "2026-08-01", "team1": "A", "team2": "B", "score": {"ft": [0, 2]}}]}
    )
    assert m.outcome_for("A") == "L" and m.outcome_for("B") == "W"
    assert m.goals_for("B") == (2, 0)
