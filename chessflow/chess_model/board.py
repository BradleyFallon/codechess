from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, cast

import chess

from chessflow.chess_model.piece import (
    Bishop,
    Color,
    King,
    Knight,
    Pawn,
    Piece,
    PieceKind,
    Queen,
    Rook,
)


@dataclass(slots=True)
class MoveDelta:
    move: chess.Move
    moving_piece_id: int
    captured_piece_id: int | None = None
    captured_square: chess.Square | None = None
    rook_piece_id: int | None = None
    rook_from: chess.Square | None = None
    rook_to: chess.Square | None = None
    moving_kind_before: PieceKind | None = None


_STARTING_IDENTITIES: tuple[tuple[type[Piece], Color, chess.Square, str], ...] = (
    *(
        (Pawn, Color.WHITE, chess.square(file_index, 1), chess.FILE_NAMES[file_index])
        for file_index in range(8)
    ),
    (Rook, Color.WHITE, chess.A1, "rq"),
    (Knight, Color.WHITE, chess.B1, "nq"),
    (Bishop, Color.WHITE, chess.C1, "bq"),
    (Queen, Color.WHITE, chess.D1, "q"),
    (King, Color.WHITE, chess.E1, "k"),
    (Bishop, Color.WHITE, chess.F1, "bk"),
    (Knight, Color.WHITE, chess.G1, "nk"),
    (Rook, Color.WHITE, chess.H1, "rk"),
    *(
        (Pawn, Color.BLACK, chess.square(file_index, 6), chess.FILE_NAMES[file_index])
        for file_index in range(8)
    ),
    (Rook, Color.BLACK, chess.A8, "rq"),
    (Knight, Color.BLACK, chess.B8, "nq"),
    (Bishop, Color.BLACK, chess.C8, "bq"),
    (Queen, Color.BLACK, chess.D8, "q"),
    (King, Color.BLACK, chess.E8, "k"),
    (Bishop, Color.BLACK, chess.F8, "bk"),
    (Knight, Color.BLACK, chess.G8, "nk"),
    (Rook, Color.BLACK, chess.H8, "rk"),
)


class FlowBoard:
    """A python-chess board plus stable application-level piece identities."""

    def __init__(self, chess_board: chess.Board | None = None) -> None:
        supplied = (
            chess_board.copy(stack=True) if chess_board is not None else chess.Board()
        )
        moves = list(supplied.move_stack)
        root = supplied.root() if moves else supplied.copy(stack=False)

        self.chess_board = root
        self.pieces_by_id: dict[int, Piece] = {}
        self.pieces_by_square: dict[chess.Square, int] = {}
        self.flow_pieces: dict[str, int] = {}
        self._piece_codes: dict[tuple[Color, str], int] = {}
        self.move_deltas: list[MoveDelta] = []

        if root.fen() == chess.Board().fen():
            self._create_starting_pieces()
            for move in moves:
                self.push(move)
        else:
            self._create_snapshot_pieces(root)
        self.rebuild_relationships()

    @classmethod
    def from_fen(cls, fen: str) -> FlowBoard:
        """Build a snapshot board, inferring identities from piece type/proximity.

        FEN contains no move history. Consequently, moved pieces receive a
        conservative move_count of one, while pieces on their origins receive
        zero. Use a python-chess Board with its move stack when exact historical
        facts are required.
        """
        return cls(chess.Board(fen))

    @property
    def ply(self) -> int:
        return self.chess_board.ply()

    @property
    def fen(self) -> str:
        return self.chess_board.fen()

    def _create_starting_pieces(self) -> None:
        for piece_id, (piece_class, color, origin, code) in enumerate(
            _STARTING_IDENTITIES, start=1
        ):
            piece = cast(Any, piece_class)(
                piece_id=piece_id,
                color=color,
                origin=origin,
                flow_code=code if color is Color.WHITE else None,
            )
            self._register(piece, internal_code=code)

    def _create_snapshot_pieces(self, board: chess.Board) -> None:
        available = set(board.piece_map())
        reserved_exact = {
            origin
            for piece_class, color, origin, _ in _STARTING_IDENTITIES
            if board.color_at(origin) == color.chess_color
            and board.piece_type_at(origin) == piece_class_kind(piece_class).value
        }
        next_extra_id = len(_STARTING_IDENTITIES) + 1
        for piece_id, (piece_class, color, origin, code) in enumerate(
            _STARTING_IDENTITIES, start=1
        ):
            occupant_type = board.piece_type_at(origin)
            expected_type = (
                PieceKind.from_chess(occupant_type)
                if (
                    occupant_type is not None
                    and board.color_at(origin) == color.chess_color
                )
                else None
            )
            square: chess.Square | None = None
            if (
                expected_type is not None
                and expected_type.value == piece_class_kind(piece_class).value
            ):
                square = origin
            else:
                candidates = [
                    candidate
                    for candidate in available - reserved_exact
                    if board.color_at(candidate) == color.chess_color
                    and board.piece_type_at(candidate)
                    == piece_class_kind(piece_class).value
                ]
                if candidates:
                    square = min(
                        candidates,
                        key=lambda candidate: chess.square_distance(origin, candidate),
                    )
            piece = cast(Any, piece_class)(
                piece_id=piece_id,
                color=color,
                origin=origin,
                flow_code=code if color is Color.WHITE else None,
                square=origin,
                move_count=0 if square == origin else int(square is not None),
            )
            piece.square = square
            if square is not None:
                available.discard(square)
            self._register(piece, internal_code=code)

        # Extra occupants generally indicate promotions. They still receive a
        # stable internal identity even though a history-free FEN cannot tell us
        # which pawn produced them.
        class_by_type = {
            chess.PAWN: Pawn,
            chess.KNIGHT: Knight,
            chess.BISHOP: Bishop,
            chess.ROOK: Rook,
            chess.QUEEN: Queen,
            chess.KING: King,
        }
        for square in sorted(available):
            chess_piece = board.piece_at(square)
            assert chess_piece is not None
            color = Color(chess_piece.color)
            piece = class_by_type[chess_piece.piece_type](
                piece_id=next_extra_id,
                color=color,
                origin=square,
                square=square,
                move_count=1,
            )
            self._register(piece, internal_code=f"promoted-{next_extra_id}")
            next_extra_id += 1

    def _register(self, piece: Piece, *, internal_code: str) -> None:
        if piece.piece_id in self.pieces_by_id:
            raise ValueError(f"Duplicate piece id: {piece.piece_id}")
        self.pieces_by_id[piece.piece_id] = piece
        if piece.square is not None:
            self.pieces_by_square[piece.square] = piece.piece_id
        self._piece_codes[(piece.color, internal_code)] = piece.piece_id
        if piece.flow_code is not None:
            self.flow_pieces[piece.flow_code] = piece.piece_id

    def piece_by_id(self, piece_id: int) -> Piece:
        try:
            return self.pieces_by_id[piece_id]
        except KeyError as exc:
            raise KeyError(f"Unknown piece id: {piece_id}") from exc

    def piece_at(self, square: chess.Square) -> Piece | None:
        piece_id = self.pieces_by_square.get(square)
        return None if piece_id is None else self.pieces_by_id[piece_id]

    def flow_piece(self, code: str) -> Piece:
        try:
            return self.pieces_by_id[self.flow_pieces[code]]
        except KeyError as exc:
            raise KeyError(f"Unknown flow piece code: {code!r}") from exc

    def piece_ref(self, reference: str, *, default_color: Color = Color.WHITE) -> Piece:
        parts = reference.lower().split(".", maxsplit=1)
        if len(parts) == 2 and parts[0] in {"white", "black"}:
            color = Color.parse(parts[0])
            code = parts[1]
        else:
            color = default_color
            code = parts[0]
        try:
            return self.piece_by_id(self._piece_codes[(color, code)])
        except KeyError as exc:
            raise KeyError(f"Unknown piece reference: {reference!r}") from exc

    def alive_pieces(self) -> Iterable[Piece]:
        return (piece for piece in self.pieces_by_id.values() if piece.is_alive)

    def flow_controlled_pieces(self) -> Iterable[Piece]:
        return (self.pieces_by_id[piece_id] for piece_id in self.flow_pieces.values())

    def push_san(self, san: str) -> MoveDelta:
        return self.push(self.chess_board.parse_san(san))

    def push_uci(self, uci: str) -> MoveDelta:
        return self.push(chess.Move.from_uci(uci))

    def push(self, move: chess.Move) -> MoveDelta:
        if move not in self.chess_board.legal_moves:
            raise ValueError(f"Illegal move: {move.uci()}")
        moving_piece = self.piece_at(move.from_square)
        if moving_piece is None:
            raise RuntimeError(
                f"No persistent piece at {chess.square_name(move.from_square)}"
            )

        captured_square: chess.Square | None = None
        if self.chess_board.is_en_passant(move):
            direction = -8 if moving_piece.color is Color.WHITE else 8
            captured_square = move.to_square + direction
        elif self.chess_board.is_capture(move):
            captured_square = move.to_square
        captured = (
            self.piece_at(captured_square) if captured_square is not None else None
        )

        delta = MoveDelta(
            move=move,
            moving_piece_id=moving_piece.piece_id,
            captured_piece_id=captured.piece_id if captured else None,
            captured_square=captured_square,
            moving_kind_before=moving_piece.kind,
        )
        if self.chess_board.is_castling(move):
            kingside = chess.square_file(move.to_square) > chess.square_file(
                move.from_square
            )
            rank = chess.square_rank(move.from_square)
            delta.rook_from = chess.square(7 if kingside else 0, rank)
            delta.rook_to = chess.square(5 if kingside else 3, rank)
            rook = self.piece_at(delta.rook_from)
            if rook is None:
                raise RuntimeError("Castling rook has no persistent identity")
            delta.rook_piece_id = rook.piece_id

        self.chess_board.push(move)
        self.pieces_by_square.pop(move.from_square)
        if captured is not None:
            assert captured_square is not None
            self.pieces_by_square.pop(captured_square)
            captured.square = None
        moving_piece.square = move.to_square
        moving_piece.move_count += 1
        if move.promotion is not None:
            moving_piece.kind = PieceKind.from_chess(move.promotion)
        self.pieces_by_square[move.to_square] = moving_piece.piece_id
        if delta.rook_piece_id is not None:
            assert delta.rook_from is not None and delta.rook_to is not None
            rook = self.piece_by_id(delta.rook_piece_id)
            self.pieces_by_square.pop(delta.rook_from)
            rook.square = delta.rook_to
            rook.move_count += 1
            self.pieces_by_square[delta.rook_to] = rook.piece_id

        self.move_deltas.append(delta)
        self.rebuild_relationships()
        return delta

    def pop(self) -> MoveDelta:
        if not self.move_deltas:
            raise IndexError("No moves to pop")
        delta = self.move_deltas.pop()
        self.chess_board.pop()
        moving_piece = self.piece_by_id(delta.moving_piece_id)
        self.pieces_by_square.pop(delta.move.to_square)
        moving_piece.square = delta.move.from_square
        moving_piece.move_count -= 1
        if delta.moving_kind_before is not None:
            moving_piece.kind = delta.moving_kind_before
        self.pieces_by_square[delta.move.from_square] = moving_piece.piece_id

        if delta.captured_piece_id is not None:
            assert delta.captured_square is not None
            captured = self.piece_by_id(delta.captured_piece_id)
            captured.square = delta.captured_square
            self.pieces_by_square[delta.captured_square] = captured.piece_id
        if delta.rook_piece_id is not None:
            assert delta.rook_from is not None and delta.rook_to is not None
            rook = self.piece_by_id(delta.rook_piece_id)
            self.pieces_by_square.pop(delta.rook_to)
            rook.square = delta.rook_from
            rook.move_count -= 1
            self.pieces_by_square[delta.rook_from] = rook.piece_id
        self.rebuild_relationships()
        return delta

    def rebuild_relationships(self) -> None:
        for piece in self.pieces_by_id.values():
            piece.relations.clear()
        for piece in self.alive_pieces():
            assert piece.square is not None
            piece.relations.controlled_squares.update(
                self.chess_board.attacks(piece.square)
            )
        for piece in self.alive_pieces():
            for square in piece.relations.controlled_squares:
                visible = self.piece_at(square)
                if visible is None:
                    continue
                relation = (
                    piece.relations.visible_allies
                    if visible.color is piece.color
                    else piece.relations.visible_enemies
                )
                relation.add(visible.piece_id)
        for target in self.alive_pieces():
            assert target.square is not None
            for square in self.chess_board.attackers(
                target.color.chess_color, target.square
            ):
                defender = self.piece_at(square)
                if defender is not None and defender is not target:
                    target.relations.geometric_defenders.add(defender.piece_id)
            for square in self.chess_board.attackers(
                target.color.opposite.chess_color, target.square
            ):
                attacker = self.piece_at(square)
                if attacker is not None:
                    target.relations.geometric_attackers.add(attacker.piece_id)
        for piece in self.alive_pieces():
            if piece.kind is not PieceKind.KING:
                assert piece.square is not None
                piece.relations.is_pinned = self.chess_board.is_pinned(
                    piece.color.chess_color, piece.square
                )
        for move in self.chess_board.legal_moves:
            legal_piece = self.piece_at(move.from_square)
            if legal_piece is None:
                raise RuntimeError(
                    f"No persistent piece at {chess.square_name(move.from_square)}"
                )
            legal_piece.relations.legal_moves.add(move)
            if self.chess_board.is_capture(move):
                legal_piece.relations.legal_captures.add(move)


def piece_class_kind(piece_class: type[Piece]) -> PieceKind:
    return {
        Pawn: PieceKind.PAWN,
        Knight: PieceKind.KNIGHT,
        Bishop: PieceKind.BISHOP,
        Rook: PieceKind.ROOK,
        Queen: PieceKind.QUEEN,
        King: PieceKind.KING,
    }[piece_class]
