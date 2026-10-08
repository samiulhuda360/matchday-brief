from matchday import evaluate
from matchday.cli import main


def test_checker_eval_meets_bar(tmp_path):
    result = evaluate.run_checker_eval(str(tmp_path))
    assert result["cases"] >= 170
    assert result["precision"] == 1.0
    assert result["recall"] >= 0.95
    assert (tmp_path / "checker.json").exists()


def test_demo_runs_without_a_key(tmp_path, capsys):
    db = str(tmp_path / "demo.db")
    main(["demo", "--db", db, "--notify", "console"])
    out = capsys.readouterr().out
    assert "template (no AI_API_KEY)" in out
    assert "recaps 32" in out and "Northfield Rovers" in out
    main(["show", "2026-10-10-northfield-rovers-westmere-albion", "--db", db, "--now", "2026-10-08T18:00"])
    assert "grounded=True" in capsys.readouterr().out
