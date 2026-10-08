import pytest

from matchday.facts import preview_facts, recap_facts
from matchday.grounding import check
from matchday.writer import GroundedWriter, TemplateWriter

from .conftest import ScriptedModel

RECAP = "2026-10-03-westmere-albion-harbourside-fc"
GOOD = "Westmere Albion beat Harbourside FC 5-1 on Saturday 3 October 2026, leading 4-0 at half-time."
BAD = "Westmere Albion beat Harbourside FC 5-2 in front of 9,000 fans."


@pytest.fixture
def sheet(sample, by_id):
    return recap_facts(sample, by_id[RECAP])


def test_template_is_grounded_for_every_match(sample):
    teams = {t for m in sample for t in (m.home, m.away)}
    writer = TemplateWriter()
    for m in sample:
        sheet = recap_facts(sample, m) if m.played else preview_facts(sample, m)
        report = check(writer.write(sheet), sheet, teams)
        assert report.grounded, (m.id, report.unsupported, report.stray_teams)
        assert report.total >= 8


def test_no_model_uses_template(sheet):
    summary = GroundedWriter(None).write(sheet)
    assert summary.source == "template" and summary.report.grounded and summary.attempts == 0


def test_grounded_model_draft_is_kept(sheet):
    summary = GroundedWriter(ScriptedModel(GOOD)).write(sheet)
    assert (summary.source, summary.text, summary.attempts) == ("model", GOOD, 1)


def test_retry_lists_the_unsupported_numbers(sheet):
    model = ScriptedModel(BAD, GOOD)
    summary = GroundedWriter(model).write(sheet)
    assert summary.source == "model-retry" and summary.text == GOOD
    assert "5-2" in model.prompts[1] and "9,000" in model.prompts[1]
    assert summary.first_report is not None and not summary.first_report.grounded
    assert summary.first_text == BAD


def test_falls_back_to_template_when_still_ungrounded(sheet):
    summary = GroundedWriter(ScriptedModel(BAD, BAD)).write(sheet)
    assert summary.source == "template" and summary.report.grounded and summary.attempts == 2


def test_model_error_falls_back(sheet):
    summary = GroundedWriter(ScriptedModel(RuntimeError("quota"))).write(sheet)
    assert summary.source == "template" and summary.report.grounded
