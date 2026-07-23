from pathlib import Path

from chessflow.cli import main


def test_test_pgn_command_runs_end_to_end(
    tmp_path: Path,
    capsys,
) -> None:
    flow_path = tmp_path / "london.flow"
    flow_path.write_text(
        """
        flow cli-london
        version 0.1
        side white
        d:
            develop.d4:
        bq:
            develop.f4:
                when: d.developed()
        """
    )
    pgn_path = tmp_path / "london.pgn"
    pgn_path.write_text("1. d4 d5 2. Bf4 *")

    exit_code = main(["test-pgn", str(flow_path), str(pgn_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Positions tested: 2" in captured.out
    assert "Matches: 2" in captured.out
    assert "MATCH\n1.d4 d5 2.Bf4" in captured.out
    assert captured.err == ""

    invalid_exit_code = main(
        ["test-pgn", str(tmp_path / "missing.flow"), str(pgn_path)]
    )

    captured = capsys.readouterr()
    assert invalid_exit_code != 0
    assert "error:" in captured.err


def test_bare_benchmark_names_resolve_from_examples(
    monkeypatch,
    capsys,
) -> None:
    repository = Path(__file__).parents[1]
    monkeypatch.chdir(repository)

    exit_code = main(
        [
            "test-pgn",
            "accelerated_london_first_pass.flow",
            "accelerated_london_ruleset_benchmark_v2.pgn",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Positions tested: 81" in captured.out
    assert "Matches: 65" in captured.out
    assert "Ambiguities: 12" in captured.out
    assert "Disagreements: 2" in captured.out
    assert "Dead ends: 2" in captured.out
    assert captured.err == ""


def test_second_pass_ruleset_cleanly_matches_the_full_benchmark(
    monkeypatch,
    capsys,
) -> None:
    repository = Path(__file__).parents[1]
    monkeypatch.chdir(repository)

    exit_code = main(
        [
            "test-pgn",
            "accelerated_london_second_pass.flow",
            "accelerated_london_ruleset_benchmark_v2.pgn",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Positions tested: 84" in captured.out
    assert "Matches: 84" in captured.out
    assert "Ambiguities: 0" in captured.out
    assert "Disagreements: 0" in captured.out
    assert "Dead ends: 0" in captured.out
    assert captured.err == ""


def test_quiz_command_runs_one_interactive_line(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    flow_path = tmp_path / "quiz.flow"
    flow_path.write_text(
        """
        flow cli-quiz
        version 0.1
        side white
        d:
            develop.d4:
        """
    )
    pgn_path = tmp_path / "quiz.pgn"
    pgn_path.write_text("1. d4 *")
    answers = iter(("d4",))
    monkeypatch.setattr("builtins.input", lambda: next(answers))

    exit_code = main(["quiz", str(flow_path), str(pgn_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "CodeChess · L1/1 · Q1/1" in captured.out
    assert "Correct." in captured.out
    assert "Line complete." in captured.out
    assert captured.err == ""
