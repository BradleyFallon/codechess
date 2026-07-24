from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import chess


class ConformanceStatus(Enum):
    MATCH = "match"
    AMBIGUOUS = "ambiguous"
    DISAGREEMENT = "disagreement"
    DEAD_END = "dead-end"


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    action_key: str
    move: chess.Move
    san: str


@dataclass(slots=True)
class ConformanceNode:
    path_san: tuple[str, ...]
    position_path_san: tuple[str, ...] = ()
    fen: str = ""
    status: ConformanceStatus | None = None
    expected_moves: tuple[chess.Move, ...] = ()
    expected_san: tuple[str, ...] = ()
    candidates: tuple[CandidateRecord, ...] = ()
    selected_action: str | None = None
    selected_move: chess.Move | None = None
    selected_san: str | None = None
    current_goal: str | None = None
    fallback_goal: str | None = None
    terminal: str | None = None
    children: list[ConformanceNode] = field(default_factory=list)


@dataclass(slots=True)
class ConformanceResult:
    root: ConformanceNode
