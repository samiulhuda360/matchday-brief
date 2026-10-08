"""Build eval/checker_cases.jsonl: labelled summaries for the grounding-checker evaluation.

Two kinds of case:
- generated: template summaries for 32 sample-league matches (grounded), plus copies with one number
  changed to a value absent from the fact sheet, one scoreline changed, or another league team
  mentioned (ungrounded). Labels are correct by construction.
- handwritten: 51 sentences in the style of real match reports, labelled by hand, including
  paraphrases ("four in a row", "two of their last five") and wrong numbers that happen to appear
  elsewhere in the fact sheet.

    python tools/make_checker_cases.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from matchday.facts import FactSheet, preview_facts, recap_facts  # noqa: E402
from matchday.grounding import Evidence, extract  # noqa: E402
from matchday.ingest import load_matches  # noqa: E402
from matchday.writer import TemplateWriter  # noqa: E402

PREVIEW = "2026-10-10-northfield-rovers-westmere-albion"
RECAP = "2026-10-03-westmere-albion-harbourside-fc"
PREVIEW2 = "2026-10-11-eastvale-united-copperhill-town"
RECAP2 = "2026-10-03-copperhill-town-stonebridge-city"

# (sheet, summary, grounded, note)
HANDWRITTEN: list[tuple[str, str, bool, str]] = [
    (
        PREVIEW,
        "Northfield Rovers, top of the table with 22 points, host Westmere Albion at 15:00 on Saturday 10 October.",
        True,
        "",
    ),
    (PREVIEW, "The leaders have won all four of their home games and lead by 12 points.", True, "number word"),
    (PREVIEW, "Westmere Albion won two of their last five and sit 4th.", True, "number words"),
    (PREVIEW, "Northfield won 4-2 at Westmere on 22 August.", True, "scoreline from the winner's side"),
    (PREVIEW, "Northfield have scored 14 and conceded only 5, a goal difference of +9.", True, ""),
    (PREVIEW, "One of the league's form sides, Northfield have won four in a row.", True, "'one' as a word"),
    (PREVIEW, "Westmere have lost 4 of their 8 league games and won just 1 of 3 away.", True, ""),
    (RECAP, "Westmere Albion beat Harbourside FC 5-1, having led 4-0 at the break.", True, ""),
    (RECAP, "Harbourside FC have now lost four in a row and slipped to 7th.", True, ""),
    (RECAP, "A four-goal win lifted Westmere from 6th to 4th.", True, "hyphenated number word"),
    (RECAP, "Six goals on Saturday 3 October, with one apiece after the break.", True, ""),
    (RECAP, "Westmere move on to 10 points from 8 matches.", True, ""),
    (PREVIEW, "Northfield Rovers have 23 points.", False, "wrong total"),
    (PREVIEW, "Northfield won 3-1 at Westmere in August.", False, "wrong scoreline"),
    (PREVIEW, "Kick-off is at 17:30.", False, "wrong time"),
    (PREVIEW, "Westmere Albion are 9th.", False, "wrong position; 9 appears elsewhere in the sheet"),
    (PREVIEW, "Westmere have won three of their last five.", False, "wrong count; 3 appears elsewhere in the sheet"),
    (PREVIEW, "Northfield are 11 points clear.", False, "wrong gap"),
    (PREVIEW, "Like Eastvale United, Northfield have won seven matches.", False, "team not in the fixture"),
    (PREVIEW, "Northfield sit second, twelve points ahead.", False, "'second' without a place word is not checked"),
    (PREVIEW, "Northfield average 1.75 goals a game.", False, "derived figure not in the data"),
    (PREVIEW, "Northfield have kept clean sheets in 62% of games.", False, "invented percentage"),
    (RECAP, "Westmere won 5-0.", False, "wrong scoreline"),
    (RECAP, "It was 3-0 at half-time.", False, "wrong half-time score"),
    (RECAP, "Harbourside fell to 8th.", False, "wrong position; 8 appears elsewhere in the sheet"),
    (RECAP, "Harbourside have 6 points.", False, "wrong total; 6 appears elsewhere in the sheet"),
    (RECAP, "A crowd of 4,812 watched a 12th-minute opener.", False, "invented attendance and minute"),
    (RECAP, "Harbourside collapsed just as Millbrook Athletic did last week.", False, "team not in the fixture"),
    (PREVIEW2, "Second-placed Eastvale United welcome Copperhill Town on Sunday at 14:00.", True, ""),
    (PREVIEW2, "Eastvale have won all three home games and lead Copperhill by five points.", True, ""),
    (PREVIEW2, "Copperhill beat Eastvale 1-0 on 23 August.", True, ""),
    (PREVIEW2, "Copperhill have scored 16, more than anyone in this fixture, but conceded 12.", True, ""),
    (PREVIEW2, "Copperhill come in 3rd on 13 points after losing three of their last five.", True, ""),
    (RECAP2, "Copperhill Town scored three times after the break to beat Stonebridge City 4-1.", True, ""),
    (RECAP2, "Stonebridge stay bottom, 8th of 8, on 5 points.", True, ""),
    (RECAP2, "Copperhill were only 1-0 up at half-time.", True, ""),
    (RECAP2, "Five goals in all, and a three-goal margin.", True, ""),
    (RECAP2, "Stonebridge slipped to a fourth defeat in five.", True, "ordinal used as a count"),
    (RECAP, "Harbourside suffered a fourth straight defeat.", True, "ordinal used as a count"),
    (PREVIEW2, "Eastvale United are 2nd with 19 points.", False, "wrong total"),
    (PREVIEW2, "Copperhill have 6 points fewer than Eastvale.", False, "wrong gap; 6 appears elsewhere in the sheet"),
    (PREVIEW2, "Eastvale are 3rd.", False, "position of the other team"),
    (PREVIEW2, "Copperhill won 2-0 when the sides met in August.", False, "wrong scoreline"),
    (PREVIEW2, "Kick-off is Saturday at 15:00.", False, "wrong time"),
    (PREVIEW2, "Eastvale have kept 4 clean sheets.", False, "invented statistic; 4 appears elsewhere in the sheet"),
    (RECAP2, "Copperhill won 4-2.", False, "wrong scoreline"),
    (RECAP2, "Stonebridge City are 7th.", False, "wrong position"),
    (RECAP2, "Copperhill moved up to 2nd.", False, "wrong position"),
    (RECAP2, "Copperhill led 2-0 at half-time.", False, "wrong half-time score"),
    (RECAP2, "Like Northfield Rovers, Copperhill scored four.", False, "team not in the fixture"),
    (RECAP2, "Stonebridge have lost four in a row.", False, "wrong streak; 4 appears elsewhere in the sheet"),
]


def unused_number(evidence: Evidence, rng: random.Random) -> int:
    return rng.choice([n for n in range(2, 40) if not evidence.has_number(n)])


def main() -> None:
    rng = random.Random(5)
    matches = load_matches(str(ROOT / "data" / "acme-valley-league.json"))
    teams = sorted({t for m in matches for t in (m.home, m.away)})
    by_id = {m.id: m for m in matches}
    played = [m for m in matches if m.played][-16:]
    upcoming = [m for m in matches if not m.played][:16]
    sheets: list[FactSheet] = [recap_facts(matches, m) for m in played] + [preview_facts(matches, m) for m in upcoming]
    writer = TemplateWriter()
    cases: list[dict[str, object]] = []

    def add(origin: str, sheet: FactSheet, summary: str, grounded: bool, note: str = "") -> None:
        cases.append({
            "id": f"{origin}-{len(cases) + 1:03d}", "origin": origin, "sheet": sheet.to_dict(),
            "summary": summary, "grounded": grounded, "note": note,
        })  # fmt: skip

    for sheet in sheets:
        text = writer.write(sheet)
        evidence = Evidence(sheet)
        add("template", sheet, text, True)

        numbers = [c for c in extract(text) if c.kind in ("number", "ordinal")]
        target = rng.choice(numbers)
        new = str(unused_number(evidence, rng))
        if target.kind == "ordinal":
            new += target.text[-2:] if not new.endswith(("1", "2", "3")) else "th"
        add("perturbed", sheet, text[: target.start] + new + text[target.end :], False, f"{target.text} -> {new}")

        scores = [c for c in extract(text) if c.kind == "score"]
        if scores:
            target = scores[0]
            a, b = (int(v) for v in target.values)
            fake = f"{a + 2}-{b}"
            if (min(a + 2, b), max(a + 2, b)) not in evidence.scores:
                add(
                    "perturbed",
                    sheet,
                    text[: target.start] + fake + text[target.end :],
                    False,
                    f"{target.text} -> {fake}",
                )

        other = rng.choice([t for t in teams if t not in sheet.teams])
        add("stray-team", sheet, f"{text} Unlike {other}, they look settled.", False, f"mentions {other}")

    for match_id, summary, grounded, note in HANDWRITTEN:
        m = by_id[match_id]
        sheet = recap_facts(matches, m) if m.played else preview_facts(matches, m)
        add("handwritten", sheet, summary, grounded, note)

    out = ROOT / "eval" / "checker_cases.jsonl"
    out.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    print(f"wrote {len(cases)} cases to {out}")


if __name__ == "__main__":
    main()
