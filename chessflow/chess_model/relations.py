from __future__ import annotations

from dataclasses import dataclass, field

import chess


@dataclass(slots=True)
class PieceRelations:
    """Position-dependent facts, rebuilt whenever the board changes."""

    controlled_squares: set[chess.Square] = field(default_factory=set)
    visible_allies: set[int] = field(default_factory=set)
    visible_enemies: set[int] = field(default_factory=set)
    geometric_attackers: set[int] = field(default_factory=set)
    geometric_defenders: set[int] = field(default_factory=set)
    legal_moves: set[chess.Move] = field(default_factory=set)
    legal_captures: set[chess.Move] = field(default_factory=set)
    is_pinned: bool = False

    def clear(self) -> None:
        self.controlled_squares.clear()
        self.visible_allies.clear()
        self.visible_enemies.clear()
        self.geometric_attackers.clear()
        self.geometric_defenders.clear()
        self.legal_moves.clear()
        self.legal_captures.clear()
        self.is_pinned = False
