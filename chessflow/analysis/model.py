from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AnalysisStatus(Enum):
    MATCH = "match"
    AMBIGUITY = "ambiguity"
    DISAGREEMENT = "disagreement"
    DEAD_END = "dead_end"


@dataclass(frozen=True, slots=True)
class AnalysisCandidate:
    rule_key: str
    uci: str
    san: str


@dataclass(frozen=True, slots=True)
class AnalysisFinding:
    path_san: tuple[str, ...]
    fen: str
    status: AnalysisStatus
    expected_san: tuple[str, ...]
    selected_san: str | None
    selected_rule: str | None
    candidates: tuple[AnalysisCandidate, ...]
    current_goal: str | None
    fallback_goal: str | None
    terminal: str | None


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    """Deterministic coverage totals for one flow and one PGN benchmark.

    ``benchmark_positions`` counts every White decision position in the
    repertoire. ``positions_evaluated`` counts positions actually reached by
    source-order flow selection. ``rules_executed`` counts unique selected
    canonical rule keys across those evaluated positions.
    """

    benchmark_positions: int
    positions_evaluated: int
    matches: int
    ambiguities: int
    disagreements: int
    dead_ends: int
    terminal_exits: int
    rules_declared: int
    rules_executed: int


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    summary: AnalysisSummary
    findings: tuple[AnalysisFinding, ...]
