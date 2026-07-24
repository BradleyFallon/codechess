from __future__ import annotations

from dataclasses import dataclass

from chessflow.analysis.model import AnalysisResult


@dataclass(frozen=True, slots=True)
class RulesetScore:
    """Experimental score for one ruleset against one specific PGN.

    Version ``conformance-v0.1`` uses deterministic conformance counts only.
    Scores produced from different benchmark PGNs are not directly
    comparable, and the elegance formula is deliberately provisional.
    """

    version: str
    completeness: float
    correctness: float
    reliability: float
    declared_rules: int
    executed_rules: int
    rule_utilization: float
    raw_rule_cost: float
    elegance: float


def score_analysis(result: AnalysisResult) -> RulesetScore:
    """Score PGN coverage, move agreement, and deterministic selection.

    An ambiguity remains correct when the expected move is selected, but it
    is not reliable because the flow offered more than one candidate.
    """

    summary = result.summary
    completeness = _ratio(
        summary.positions_evaluated,
        summary.benchmark_positions,
    )
    correctness = _ratio(
        summary.matches + summary.ambiguities,
        summary.positions_evaluated,
    )
    reliability = _ratio(
        summary.matches,
        summary.positions_evaluated,
    )
    raw_rule_cost = float(summary.rules_declared)
    rule_utilization = _ratio(
        summary.rules_executed,
        summary.rules_declared,
    )
    quality = completeness * reliability
    elegance = quality / (1.0 + 0.05 * raw_rule_cost)
    return RulesetScore(
        version="conformance-v0.1",
        completeness=completeness,
        correctness=correctness,
        reliability=reliability,
        declared_rules=summary.rules_declared,
        executed_rules=summary.rules_executed,
        rule_utilization=rule_utilization,
        raw_rule_cost=raw_rule_cost,
        elegance=elegance,
    )


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator
