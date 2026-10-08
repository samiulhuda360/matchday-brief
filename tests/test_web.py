import pytest
from fastapi.testclient import TestClient

from matchday.jobs import tick
from matchday.store import Store
from matchday.web import create_app

from .conftest import DEMO_NOW, SAMPLE, FakeNotifier


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "w.db")
    tick(store, SAMPLE, DEMO_NOW, [FakeNotifier()])
    yield TestClient(create_app(store, lambda: DEMO_NOW))
    store.close()


def test_dashboard(client):
    page = client.get("/")
    assert page.status_code == 200
    for text in ("League table", "Northfield Rovers", "Coming up", "Latest results", "36/36", "numbers checked"):
        assert text in page.text


def test_match_page_shows_highlighted_summary(client):
    page = client.get("/match/2026-10-03-westmere-albion-harbourside-fc")
    assert page.status_code == 200
    assert '<mark class="ok"' in page.text and "Fact sheet" in page.text
    assert client.get("/match/nope").status_code == 404


def test_draft_check_flags_wrong_numbers(client):
    page = client.get(
        "/match/2026-10-03-westmere-albion-harbourside-fc", params={"draft": "Westmere won 5-0 and sit 2nd."}
    )
    assert page.status_code == 200
    assert "Not in the data: 5-0, 2nd" in page.text


def test_api(client):
    table = client.get("/api/table").json()
    assert table[0]["team"] == "Northfield Rovers" and table[0]["points"] == 22
    summary = client.get("/api/summaries/2026-10-10-northfield-rovers-westmere-albion").json()
    assert summary["kind"] == "preview" and summary["grounding"]["grounded"]
    assert client.get("/api/summaries/nope").status_code == 404
    assert client.get("/healthz").json() == {"status": "ok"}
