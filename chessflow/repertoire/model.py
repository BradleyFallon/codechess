from __future__ import annotations

from dataclasses import dataclass, field

import chess


@dataclass(slots=True)
class RepertoireNode:
    move: chess.Move | None
    san: str | None
    fen: str
    comment: str | None
    children: list[RepertoireNode] = field(default_factory=list)
