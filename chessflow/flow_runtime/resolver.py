from __future__ import annotations

import chess

from chessflow.chess_model import FlowBoard, King, Piece
from chessflow.flow_runtime.action import Action, ActionKind, CastleSide


class AmbiguousActionError(RuntimeError):
    pass


def resolve_action(action: Action, piece: Piece, board: FlowBoard) -> chess.Move | None:
    if not piece.is_alive:
        return None
    if action.kind is ActionKind.DEVELOP:
        return resolve_develop(action, piece, board)
    if action.kind is ActionKind.CAPTURE:
        return resolve_capture(action, piece, board)
    if action.kind is ActionKind.CASTLE:
        if not isinstance(piece, King):
            raise TypeError("Only a king can own a castle action")
        return resolve_castle(action, piece, board)
    raise ValueError(f"Unsupported action kind: {action.kind}")


def resolve_develop(
    action: Action, piece: Piece, board: FlowBoard
) -> chess.Move | None:
    return _unique(
        move
        for move in piece.relations.legal_moves
        if move.to_square == action.target_square
        and not board.chess_board.is_capture(move)
    )


def resolve_capture(
    action: Action, piece: Piece, board: FlowBoard
) -> chess.Move | None:
    return _unique(
        move
        for move in piece.relations.legal_captures
        if move.to_square == action.target_square
    )


def resolve_castle(action: Action, piece: King, board: FlowBoard) -> chess.Move | None:
    return _unique(
        move
        for move in piece.relations.legal_moves
        if board.chess_board.is_castling(move)
        and (
            (
                action.castle_side is CastleSide.KINGSIDE
                and chess.square_file(move.to_square)
                > chess.square_file(move.from_square)
            )
            or (
                action.castle_side is CastleSide.QUEENSIDE
                and chess.square_file(move.to_square)
                < chess.square_file(move.from_square)
            )
        )
    )


def _unique(moves) -> chess.Move | None:
    matches = list(moves)
    if len(matches) > 1:
        raise AmbiguousActionError(
            f"Action resolved to multiple legal moves: {[move.uci() for move in matches]}"
        )
    return matches[0] if matches else None
