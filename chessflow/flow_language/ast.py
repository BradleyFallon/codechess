from __future__ import annotations

from dataclasses import dataclass

from chessflow.chess_model.piece import Color
from chessflow.flow_language.expressions import Expression
from chessflow.flow_runtime.rule import RuleDefinition


@dataclass(frozen=True, slots=True)
class FlowDefinition:
    name: str
    version: str
    side: Color
    declared_flags: frozenset[str]
    conditions: dict[str, Expression]
    rules: tuple[RuleDefinition, ...]
