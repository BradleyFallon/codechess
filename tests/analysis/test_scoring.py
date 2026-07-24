from dataclasses import replace

import pytest

from chessflow.analysis import (
    AnalysisResult,
    AnalysisSummary,
    score_analysis,
)


def _result(
    *,
    benchmark_positions: int = 1,
    positions_evaluated: int = 1,
    matches: int = 1,
    ambiguities: int = 0,
    disagreements: int = 0,
    dead_ends: int = 0,
    rules_declared: int = 1,
    rules_executed: int = 1,
) -> AnalysisResult:
    return AnalysisResult(
        summary=AnalysisSummary(
            benchmark_positions=benchmark_positions,
            positions_evaluated=positions_evaluated,
            matches=matches,
            ambiguities=ambiguities,
            disagreements=disagreements,
            dead_ends=dead_ends,
            terminal_exits=0,
            rules_declared=rules_declared,
            rules_executed=rules_executed,
        ),
        findings=(),
    )


def test_perfect_small_flow_score_and_version() -> None:
    score = score_analysis(_result())

    assert score.version == "conformance-v0.1"
    assert score.completeness == 1.0
    assert score.correctness == 1.0
    assert score.reliability == 1.0
    assert score.rule_utilization == 1.0
    assert score.raw_rule_cost == 1.0
    assert score.elegance == pytest.approx(1.0 / 1.05)


def test_partial_coverage_reduces_completeness() -> None:
    score = score_analysis(
        _result(
            benchmark_positions=4,
            positions_evaluated=2,
            matches=2,
        )
    )

    assert score.completeness == 0.5
    assert score.correctness == 1.0
    assert score.reliability == 1.0


@pytest.mark.parametrize(
    ("ambiguities", "disagreements", "expected_correctness"),
    ((1, 0, 1.0), (0, 1, 0.5)),
)
def test_correctness_credits_ambiguity_but_not_disagreement(
    ambiguities: int,
    disagreements: int,
    expected_correctness: float,
) -> None:
    score = score_analysis(
        _result(
            benchmark_positions=2,
            positions_evaluated=2,
            matches=1,
            ambiguities=ambiguities,
            disagreements=disagreements,
        )
    )

    assert score.reliability == 0.5
    assert score.correctness == expected_correctness


def test_more_declared_rules_lower_elegance_at_equal_quality() -> None:
    lean = score_analysis(_result(rules_declared=2))
    larger = score_analysis(
        replace(
            _result(rules_declared=2),
            summary=replace(
                _result(rules_declared=2).summary,
                rules_declared=10,
            ),
        )
    )

    assert lean.completeness == larger.completeness
    assert lean.reliability == larger.reliability
    assert lean.elegance > larger.elegance


def test_zero_position_and_zero_rule_denominators_are_explicit() -> None:
    score = score_analysis(
        _result(
            benchmark_positions=0,
            positions_evaluated=0,
            matches=0,
            rules_declared=0,
            rules_executed=0,
        )
    )

    assert score.completeness == 0.0
    assert score.correctness == 0.0
    assert score.reliability == 0.0
    assert score.rule_utilization == 0.0
    assert score.raw_rule_cost == 0.0
    assert score.elegance == 0.0
