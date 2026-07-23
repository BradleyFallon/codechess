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
