from chessflow import parse_flow
from chessflow.conformance import run_conformance
from chessflow.reporting import render_text_report, summarize_conformance
from chessflow.repertoire import load_pgn


def _mixed_result():
    definition = parse_flow(
        """
        flow mixed-report
        version 0.1
        side white
        d:
            develop.d4:
        bq:
            develop.f4:
                when: square.f6.has(enemy.knight)
        nk:
            develop.f3:
                when: square.f6.has(enemy.knight)
        c:
            develop.c3:
                when: square.d5.has(enemy.pawn)
        """
    )
    repertoire = load_pgn(
        """
        1. d4 d5
            (1... Nf6 2. Bf4)
            (1... g6 2. Bf4)
        2. c4
        *
        """
    )
    return run_conformance(definition, repertoire)


def test_summary_counts_decision_outcomes() -> None:
    summary = summarize_conformance(_mixed_result())

    assert summary.positions_tested == 4
    assert summary.matches == 1
    assert summary.ambiguities == 1
    assert summary.disagreements == 1
    assert summary.dead_ends == 1


def test_text_report_contains_summary_and_important_branch_details() -> None:
    report = render_text_report(_mixed_result())

    for line in (
        "Positions tested: 4",
        "Matches: 1",
        "Ambiguities: 1",
        "Disagreements: 1",
        "Dead ends: 1",
    ):
        assert line in report

    assert "MATCH\n1.d4" in report
    assert "AMBIGUOUS\n1.d4 Nf6 2.Bf4" in report
    assert "Candidates:" in report
    assert "  bq.develop.f4" in report
    assert "  nk.develop.f3" in report
    assert "DISAGREEMENT\n1.d4 d5" in report
    assert "Expected: c4" in report
    assert "Flow: c3" in report
    assert "Rule: c.develop.c3" in report
    assert "DEAD END\n1.d4 g6" in report
