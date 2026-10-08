"""Evaluations.

checker  Accuracy of the grounding checker on labelled summaries (eval/checker_cases.jsonl).
         Offline and deterministic; runs in CI.
writer   How often model-written previews and recaps are grounded on the first draft, after one
         retry, and after the template fallback. Needs AI_API_KEY; never runs in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .facts import FactSheet, preview_facts, recap_facts
from .grounding import check
from .ingest import load_matches
from .llm import LLMClient
from .writer import GroundedWriter

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval" / "checker_cases.jsonl"
SAMPLE = ROOT / "data" / "acme-valley-league.json"


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_checker(cases: list[dict[str, Any]], league_teams: set[str]) -> dict[str, Any]:
    """'Positive' means the case contains an unsupported number or team, which the checker should flag."""
    tp = fp = tn = fn = 0
    misses: list[dict[str, Any]] = []
    by_origin: dict[str, dict[str, int]] = {}
    for case in cases:
        sheet = FactSheet.from_dict(case["sheet"])
        flagged = not check(case["summary"], sheet, league_teams).grounded
        should_flag = not case["grounded"]
        tp += flagged and should_flag
        fp += flagged and not should_flag
        tn += (not flagged) and (not should_flag)
        fn += (not flagged) and should_flag
        bucket = by_origin.setdefault(case["origin"], {"cases": 0, "correct": 0})
        bucket["cases"] += 1
        bucket["correct"] += flagged == should_flag
        if flagged != should_flag:
            misses.append({"id": case["id"], "expected_flag": should_flag, "note": case.get("note", "")})
    total = tp + fp + tn + fn
    return {
        "cases": total,
        "ungrounded_cases": tp + fn,
        "accuracy": round((tp + tn) / total, 4),
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "by_origin": by_origin,
        "misses": misses,
    }


def run_checker_eval(out: str) -> dict[str, Any]:
    teams = {t for m in load_matches(str(SAMPLE)) for t in (m.home, m.away)}
    result = score_checker(load_cases(), teams)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "checker.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        f"checker: {result['cases']} cases ({result['ungrounded_cases']} ungrounded), "
        f"accuracy {result['accuracy']:.1%}, "
        f"precision {result['precision']:.1%}, recall {result['recall']:.1%}"
    )
    for origin, b in result["by_origin"].items():
        print(f"  {origin:<12} {b['correct']}/{b['cases']}")
    for miss in result["misses"]:
        print(f"  miss {miss['id']}: expected_flag={miss['expected_flag']} {miss['note']}")
    return result


def writer_sheets(limit: int) -> list[FactSheet]:
    """Recaps of the latest played matches and previews of the next fixtures, half each."""
    matches = load_matches(str(SAMPLE))
    played = [m for m in matches if m.played][-(limit // 2) :]
    upcoming = [m for m in matches if not m.played][: limit - limit // 2]
    return [recap_facts(matches, m) for m in played] + [preview_facts(matches, m) for m in upcoming]


def run_writer_eval(out: str, limit: int = 24) -> dict[str, Any]:
    client = LLMClient.from_env(cache_dir=ROOT / "eval" / ".cache")
    if client is None:
        raise SystemExit("the writer eval needs AI_API_KEY (it calls the model)")
    teams = {t for m in load_matches(str(SAMPLE)) for t in (m.home, m.away)}
    writer = GroundedWriter(client, teams)
    rows: list[dict[str, Any]] = []
    for sheet in writer_sheets(limit):
        s = writer.write(sheet)
        first = s.first_report
        rows.append(
            {
                "match_id": sheet.match_id,
                "kind": sheet.kind,
                "source": s.source,
                "first_draft": first.to_dict() if first else None,
                "first_draft_text": s.first_text,
                "final": s.report.to_dict(),
                "words": len(s.text.split()),
                "text": s.text,
            }
        )
    drafts = [r["first_draft"] for r in rows if r["first_draft"]]
    n = len(rows)
    summary = {
        "model": client.model,
        "summaries": n,
        "first_draft_grounded": sum(d["grounded"] for d in drafts),
        "first_draft_numbers": sum(d["numbers_total"] for d in drafts),
        "first_draft_numbers_supported": sum(d["numbers_supported"] for d in drafts),
        "published_by": {k: sum(r["source"] == k for r in rows) for k in ("model", "model-retry", "template")},
        "published_grounded": sum(r["final"]["grounded"] for r in rows),
        "mean_words": round(sum(r["words"] for r in rows) / n, 1),
        "model_calls": client.calls,
        "cache_hits": client.cache_hits,
    }
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "writer.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return summary
