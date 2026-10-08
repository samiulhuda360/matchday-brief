"""Dashboard: league table, fixtures with previews, results with recaps, and the grounding check."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .facts import FactSheet
from .grounding import check, highlight
from .stats import ordinal, standings
from .store import Store

HERE = Path(__file__).parent


def create_app(store: Store, now: Callable[[], datetime] = datetime.now) -> FastAPI:
    app = FastAPI(title="Matchday Brief")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["ordinal"] = ordinal

    def summary_view(match_id: str, kind: str) -> dict[str, Any] | None:
        row = store.summary(match_id, kind)
        if row is None:
            return None
        sheet = FactSheet.from_dict(json.loads(row["facts"]))
        teams = {t for m in store.matches() for t in (m.home, m.away)}
        report = check(row["text"], sheet, teams)
        return {**row, "html": highlight(row["text"], report), "report": report, "sheet": sheet}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        clock = now()
        matches = store.matches()
        upcoming = [m for m in matches if not m.played and m.kickoff >= clock][:8]
        results = [m for m in matches if m.played][::-1][:8]
        summaries = store.summaries()
        grounded = sum(json.loads(s["report"])["grounded"] for s in summaries)
        sources: dict[str, int] = {}
        for s in summaries:
            sources[s["source"]] = sources.get(s["source"], 0) + 1
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "now": clock,
                "league": matches[0].league if matches else "No data yet",
                "table": standings(matches),
                "upcoming": [(m, summary_view(m.id, "preview")) for m in upcoming],
                "results": [(m, summary_view(m.id, "recap")) for m in results],
                "notifications": store.notifications(8),
                "runs": store.runs(5),
                "stats": {
                    "summaries": len(summaries),
                    "grounded": grounded,
                    "numbers": sum(s["numbers_total"] for s in summaries),
                    "supported": sum(s["numbers_supported"] for s in summaries),
                    "sources": sources,
                },
            },
        )

    @app.get("/match/{match_id}", response_class=HTMLResponse)
    def match_page(request: Request, match_id: str, draft: str = "") -> HTMLResponse:
        """The stored summary next to its fact sheet; `draft` checks any text against the same sheet."""
        match = store.match(match_id)
        if match is None:
            raise HTTPException(404, "match not found")
        kind = "recap" if match.played else "preview"
        view = summary_view(match_id, kind)
        checked = None
        if draft.strip() and view is not None:
            teams = {t for m in store.matches() for t in (m.home, m.away)}
            report = check(draft[:2000], view["sheet"], teams)
            checked = {"html": highlight(draft[:2000], report), "report": report}
        context = {"match": match, "kind": kind, "view": view, "draft": draft[:2000], "checked": checked}
        return templates.TemplateResponse(request, "match.html", context)

    @app.get("/api/table")
    def api_table() -> list[dict[str, Any]]:
        return [
            {
                "position": r.position, "team": r.team, "played": r.played, "won": r.won, "drawn": r.drawn,
                "lost": r.lost, "scored": r.scored, "conceded": r.conceded, "points": r.points, "form": "".join(r.form),
            }
            for r in standings(store.matches())
        ]  # fmt: skip

    @app.get("/api/summaries/{match_id}")
    def api_summary(match_id: str) -> dict[str, Any]:
        for kind in ("recap", "preview"):
            row = store.summary(match_id, kind)
            if row:
                return {
                    "match_id": match_id, "kind": kind, "text": row["text"], "source": row["source"],
                    "grounding": json.loads(row["report"]), "facts": json.loads(row["facts"])["facts"],
                }  # fmt: skip
        raise HTTPException(404, "no summary for this match")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
