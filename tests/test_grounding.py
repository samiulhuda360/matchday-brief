import pytest

from matchday.facts import preview_facts, recap_facts
from matchday.grounding import check, extract, highlight

PREVIEW = "2026-10-10-northfield-rovers-westmere-albion"
RECAP = "2026-10-03-westmere-albion-harbourside-fc"


@pytest.fixture
def preview(sample, by_id):
    return preview_facts(sample, by_id[PREVIEW])


@pytest.fixture
def recap(sample, by_id):
    return recap_facts(sample, by_id[RECAP])


@pytest.fixture
def teams(sample):
    return {t for m in sample for t in (m.home, m.away)}


def kinds(text):
    return [(c.text, c.kind, c.unit) for c in extract(text)]


def test_extracts_each_kind():
    assert kinds("Kick-off 15:00 on 2026-10-10, a 2-1 win, 4th, 1.75 a game, 62% and three") == [
        ("15:00", "time", ""),
        ("2026-10-10", "date", ""),
        ("2-1", "score", ""),
        ("4th", "ordinal", "position"),
        ("1.75", "number", ""),
        ("62%", "number", ""),
        ("three", "word", ""),
    ]


def test_scoreline_at_end_of_sentence():
    assert kinds("Westmere won 5-0.") == [("5-0", "score", "")]


def test_units_and_ordinary_words():
    assert kinds("a 12-point lead") == [("12", "number", "points")]
    assert kinds("one of the best in the first half") == []
    assert kinds("second place") == [("second", "word", "position")]
    assert kinds("a fourth straight defeat") == [("fourth", "word", "")]
    assert kinds("Saturday 3rd October") == [("3rd", "ordinal", "")]


def test_grounded_summary_passes(preview, teams):
    text = "Northfield Rovers, 1st with 22 points, host Westmere Albion at 15:00. They won 4-2 on 22 August."
    report = check(text, preview, teams)
    assert report.grounded and report.total == report.supported == 5


@pytest.mark.parametrize(
    "text, bad",
    [
        ("Northfield Rovers have 23 points.", ["23"]),
        ("Northfield won 3-1 last time.", ["3-1"]),
        ("Kick-off is at 17:30.", ["17:30"]),
        ("Westmere Albion are 9th.", ["9th"]),
        ("Northfield are 11 points clear.", ["11"]),
        ("Northfield average 1.75 goals a game.", ["1.75"]),
    ],
)
def test_unsupported_numbers_are_flagged(preview, teams, text, bad):
    report = check(text, preview, teams)
    assert not report.grounded and report.unsupported == bad


def test_wrong_value_present_elsewhere_is_caught_when_typed(recap, teams):
    # 6 and 8 both appear in the sheet, but not as points or as a position
    assert check("Harbourside have 6 points.", recap, teams).unsupported == ["6"]
    assert check("Harbourside fell to 8th.", recap, teams).unsupported == ["8th"]


def test_stray_team_is_flagged(recap, teams):
    report = check("Unlike Northfield Rovers, Westmere won 5-1.", recap, teams)
    assert report.stray_teams == ["Northfield Rovers"] and not report.grounded


def test_highlight_marks_and_escapes(recap, teams):
    text = "Westmere <b>won</b> 5-1, not 5-0."
    html = highlight(text, check(text, recap, teams))
    assert '<mark class="ok"' in html and '<mark class="bad"' in html
    assert "&lt;b&gt;" in html and "<b>" not in html
