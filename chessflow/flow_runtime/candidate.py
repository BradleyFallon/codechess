from __future__ import annotations

from dataclasses import dataclass

import chess

from chessflow.flow_runtime.rule import RuleRuntime


@dataclass(frozen=True, slots=True)
class Candidate:
    rule: RuleRuntime
    move: chess.Move
