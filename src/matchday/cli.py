"""Command line: matchday {demo, tick, watch, serve, table, show, eval}."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from .facts import preview_facts, recap_facts
from .jobs import Settings, tick, watch
from .llm import LLMClient
from .notify import build_notifiers
from .stats import standings
from .store import Store
from .writer import GroundedWriter

SAMPLE = str(Path(__file__).resolve().parents[2] / "data" / "acme-valley-league.json")
DEMO_NOW = "2026-10-08T18:00"


def _now(value: str | None) -> datetime:
    raw = value or os.environ.get("MATCHDAY_NOW")
    return datetime.fromisoformat(raw) if raw else datetime.now().replace(microsecond=0)


def _db(value: str | None) -> str:
    return value or os.environ.get("MATCHDAY_DB", ".matchday/matchday.db")


def _source(value: str | None) -> str:
    return value or os.environ.get("MATCHDAY_SOURCE", SAMPLE)


def _settings(args: argparse.Namespace) -> Settings:
    teams = set(args.team or []) or {t.strip() for t in os.environ.get("MATCHDAY_TEAMS", "").split(",") if t.strip()}
    return Settings(teams=teams)


def print_table(store: Store) -> None:
    print(f"{'#':>2}  {'Team':<22}{'P':>3}{'W':>3}{'D':>3}{'L':>3}{'GD':>5}{'Pts':>5}  Form")
    for r in standings(store.matches()):
        print(
            f"{r.position:>2}  {r.team:<22}{r.played:>3}{r.won:>3}{r.drawn:>3}{r.lost:>3}"
            f"{r.goal_difference:>+5}{r.points:>5}  {''.join(r.form)}"
        )


def cmd_tick(args: argparse.Namespace) -> None:
    store = Store(_db(args.db))
    model = None if args.no_model else LLMClient.from_env()
    counts = tick(store, _source(args.source), _now(args.now), build_notifiers(args.notify), model, _settings(args))
    print("tick:", ", ".join(f"{k} {v}" for k, v in counts.items()))


def cmd_watch(args: argparse.Namespace) -> None:
    store = Store(_db(args.db))
    model = None if args.no_model else LLMClient.from_env()
    notifiers = build_notifiers(args.notify)
    settings = _settings(args)
    watch(lambda: tick(store, _source(args.source), _now(args.now), notifiers, model, settings), args.every)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .web import create_app

    fixed = args.now or os.environ.get("MATCHDAY_NOW")
    app = create_app(Store(_db(args.db)), (lambda: _now(fixed)) if fixed else datetime.now)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


def cmd_table(args: argparse.Namespace) -> None:
    print_table(Store(_db(args.db)))


def cmd_show(args: argparse.Namespace) -> None:
    """Write (or rewrite) the preview or recap for one match and print it with its grounding report."""
    store = Store(_db(args.db))
    matches = store.matches()
    match = next((m for m in matches if m.id == args.match_id), None)
    if match is None:
        sys.exit(f"unknown match id: {args.match_id} (see the dashboard or /api/table)")
    sheet = recap_facts(matches, match) if match.played else preview_facts(matches, match)
    model = None if args.no_model else LLMClient.from_env()
    summary = GroundedWriter(model, {t for m in matches for t in (m.home, m.away)}).write(sheet)
    store.save_summary(sheet, summary, _now(args.now))
    if args.facts:
        print(sheet.text(), end="\n\n")
    print(summary.text)
    r = summary.report
    print(
        f"\n[{sheet.kind} by {summary.source}] {r.supported}/{r.total} numbers found in the data, grounded={r.grounded}"
    )


def cmd_demo(args: argparse.Namespace) -> None:
    db = Path(_db(args.db) if args.db else ".matchday/demo.db")
    if db.exists():
        db.unlink()
    store = Store(db)
    model = None if args.no_model else LLMClient.from_env()
    writer = "model + grounding check" if model else "template (no AI_API_KEY)"
    print(f"Sample league: {SAMPLE}\nClock fixed at {DEMO_NOW}; writer: {writer}\n")
    counts = tick(store, SAMPLE, _now(DEMO_NOW), build_notifiers(args.notify or "console,outbox"), model, Settings())
    print("\ntick:", ", ".join(f"{k} {v}" for k, v in counts.items()))
    again = tick(store, SAMPLE, _now(DEMO_NOW), build_notifiers("console"), model, Settings())
    print("second tick (nothing new is due):", ", ".join(f"{k} {v}" for k, v in again.items()), "\n")
    print_table(store)
    if args.serve:
        print(f"\nDashboard: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
        args.db, args.now, args.host = str(db), DEMO_NOW, "127.0.0.1"
        cmd_serve(args)
    else:
        print(f"\nOpen the dashboard with:  matchday serve --db {db} --now {DEMO_NOW}")


def cmd_eval(args: argparse.Namespace) -> None:
    from . import evaluate

    if args.which == "checker":
        evaluate.run_checker_eval(args.out)
    else:
        evaluate.run_writer_eval(args.out, limit=args.limit)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(
        prog="matchday", description="Fixtures, reminders and grounded match previews and recaps."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--db", help="SQLite path (env MATCHDAY_DB, default .matchday/matchday.db)")
        sp.add_argument("--now", help="fixed clock, ISO format (env MATCHDAY_NOW)")

    def job(sp: argparse.ArgumentParser) -> None:
        common(sp)
        sp.add_argument("--source", help="openfootball JSON file or URL (env MATCHDAY_SOURCE)")
        sp.add_argument("--notify", help="channels: console,outbox,telegram,webhook (env MATCHDAY_NOTIFY)")
        sp.add_argument("--team", action="append", help="follow a team (repeatable; env MATCHDAY_TEAMS)")
        sp.add_argument("--no-model", action="store_true", help="use templates even if AI_API_KEY is set")

    sp = sub.add_parser("demo", help="run the sample league end to end")
    common(sp)
    sp.add_argument("--notify")
    sp.add_argument("--no-model", action="store_true")
    sp.add_argument("--serve", action="store_true", help="start the dashboard afterwards")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_demo)

    sp = sub.add_parser("tick", help="run the scheduled job once")
    job(sp)
    sp.set_defaults(func=cmd_tick)

    sp = sub.add_parser("watch", help="run the job on an interval")
    job(sp)
    sp.add_argument("--every", type=float, default=900, help="seconds between runs (default 900)")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("serve", help="start the dashboard")
    common(sp)
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("table", help="print the league table")
    common(sp)
    sp.set_defaults(func=cmd_table)

    sp = sub.add_parser("show", help="write and print the preview or recap for one match")
    common(sp)
    sp.add_argument("match_id")
    sp.add_argument("--facts", action="store_true", help="print the fact sheet too")
    sp.add_argument("--no-model", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("eval", help="run an evaluation")
    sp.add_argument("which", choices=["checker", "writer"])
    sp.add_argument("--out", default="eval/results")
    sp.add_argument("--limit", type=int, default=24)
    sp.set_defaults(func=cmd_eval)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
