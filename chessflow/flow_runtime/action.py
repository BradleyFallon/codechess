from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import chess


class ActionKind(Enum):
    DEVELOP = "develop"
    CAPTURE = "capture"
    CASTLE = "castle"

    @classmethod
    def parse(cls, value: str) -> ActionKind:
        try:
            return cls(value.lower())
        except ValueError as exc:
            raise ValueError(f"Unknown action kind: {value!r}") from exc


class CastleSide(Enum):
    KINGSIDE = "kingside"
    QUEENSIDE = "queenside"

    @classmethod
    def parse(cls, value: str) -> CastleSide:
        aliases = {
            "kingside": cls.KINGSIDE,
            "king": cls.KINGSIDE,
            "o-o": cls.KINGSIDE,
            "queenside": cls.QUEENSIDE,
            "queen": cls.QUEENSIDE,
            "o-o-o": cls.QUEENSIDE,
        }
        try:
            return aliases[value.lower()]
        except KeyError as exc:
            raise ValueError(f"Unknown castling side: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Action:
    owner_code: str
    kind: ActionKind
    target_square: chess.Square | None = None
    castle_side: CastleSide | None = None

    def __post_init__(self) -> None:
        if self.kind is ActionKind.CASTLE:
            if self.castle_side is None or self.target_square is not None:
                raise ValueError("A castle action needs only castle_side")
        elif self.target_square is None or self.castle_side is not None:
            raise ValueError(f"A {self.kind.value} action needs only target_square")

    @property
    def canonical_key(self) -> str:
        target = (
            self.castle_side.value
            if self.kind is ActionKind.CASTLE and self.castle_side is not None
            else chess.square_name(self.target_square)  # type: ignore[arg-type]
        )
        return f"{self.owner_code}.{self.kind.value}.{target}"
