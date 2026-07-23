from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import chess

from chessflow.chess_model.relations import PieceRelations

if TYPE_CHECKING:
    from chessflow.chess_model.board import FlowBoard
    from chessflow.flow_runtime.rule import PieceRuleCollection


class Color(Enum):
    WHITE = chess.WHITE
    BLACK = chess.BLACK

    @property
    def chess_color(self) -> chess.Color:
        return self.value

    @property
    def opposite(self) -> Color:
        return Color.BLACK if self is Color.WHITE else Color.WHITE

    @classmethod
    def parse(cls, value: str) -> Color:
        try:
            return cls[value.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown chess side: {value!r}") from exc


class PieceKind(Enum):
    PAWN = chess.PAWN
    KNIGHT = chess.KNIGHT
    BISHOP = chess.BISHOP
    ROOK = chess.ROOK
    QUEEN = chess.QUEEN
    KING = chess.KING

    @classmethod
    def from_chess(cls, piece_type: chess.PieceType) -> PieceKind:
        return cls(piece_type)


@dataclass(slots=True)
class Piece:
    piece_id: int
    color: Color
    kind: PieceKind
    origin: chess.Square
    flow_code: str | None = None
    square: chess.Square | None = None
    move_count: int = 0
    relations: PieceRelations = field(default_factory=PieceRelations)
    rules: PieceRuleCollection | None = None

    def __post_init__(self) -> None:
        if self.square is None:
            self.square = self.origin

    @property
    def is_alive(self) -> bool:
        return self.square is not None

    @property
    def is_captured(self) -> bool:
        return self.square is None

    @property
    def has_moved(self) -> bool:
        return self.move_count > 0

    @property
    def is_on_origin(self) -> bool:
        return self.square == self.origin

    @property
    def is_attacked(self) -> bool:
        return bool(self.relations.geometric_attackers)

    @property
    def is_defended(self) -> bool:
        return bool(self.relations.geometric_defenders)

    @property
    def is_pinned(self) -> bool:
        return self.relations.is_pinned

    @property
    def attacker_count(self) -> int:
        return len(self.relations.geometric_attackers)

    @property
    def defender_count(self) -> int:
        return len(self.relations.geometric_defenders)

    @property
    def has_developed(self) -> bool:
        # Kept here as a flow-facing convenience, while its value comes solely
        # from rule history rather than board geometry.
        if self.rules is None:
            return False
        from chessflow.flow_runtime.action import ActionKind
        from chessflow.flow_runtime.rule import RuleStatus

        return any(
            runtime.definition.action.kind is ActionKind.DEVELOP
            and runtime.status is RuleStatus.EXECUTED
            for runtime in self.rules.executed
        )

    def at(self, square: chess.Square) -> bool:
        return self.square == square

    def controls(self, square: chess.Square) -> bool:
        return square in self.relations.controlled_squares

    def can_move_to(self, square: chess.Square) -> bool:
        return any(move.to_square == square for move in self.relations.legal_moves)

    def can_capture_on(self, square: chess.Square) -> bool:
        return any(move.to_square == square for move in self.relations.legal_captures)


class Pawn(Piece):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.PAWN, origin, flow_code, square, move_count
        )


class Knight(Piece):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.KNIGHT, origin, flow_code, square, move_count
        )


class Slider(Piece):
    def visible_along_lines(self, board: FlowBoard) -> set[Piece]:
        return {
            board.piece_by_id(piece_id)
            for piece_id in self.relations.visible_allies
            | self.relations.visible_enemies
        }


class Bishop(Slider):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.BISHOP, origin, flow_code, square, move_count
        )


class Rook(Slider):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.ROOK, origin, flow_code, square, move_count
        )


class Queen(Slider):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.QUEEN, origin, flow_code, square, move_count
        )


class King(Piece):
    def __init__(
        self,
        *,
        piece_id: int,
        color: Color,
        origin: chess.Square,
        flow_code: str | None = None,
        square: chess.Square | None = None,
        move_count: int = 0,
    ) -> None:
        super().__init__(
            piece_id, color, PieceKind.KING, origin, flow_code, square, move_count
        )

    def in_check(self, board: FlowBoard) -> bool:
        return (
            board.chess_board.turn == self.color.chess_color
            and board.chess_board.is_check()
        )
