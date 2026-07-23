import chess
import pytest

from chessflow.chess_model import Color, FlowBoard, Knight, Pawn


def test_starting_pieces_have_stable_public_and_internal_identities() -> None:
    board = FlowBoard()

    assert len(board.pieces_by_id) == 32
    assert len(board.flow_pieces) == 16
    assert isinstance(board.flow_piece("d"), Pawn)
    assert isinstance(board.flow_piece("nk"), Knight)
    assert board.piece_ref("black.d").color is Color.BLACK
    assert board.piece_ref("black.d").flow_code is None


def test_push_updates_the_same_piece_and_pop_restores_it() -> None:
    board = FlowBoard()
    pawn = board.flow_piece("d")
    original_id = id(pawn)

    delta = board.push_san("d4")

    assert delta.moving_piece_id == pawn.piece_id
    assert id(board.piece_at(chess.D4)) == original_id
    assert pawn.square == chess.D4
    assert pawn.move_count == 1
    assert pawn.has_moved
    assert not pawn.is_on_origin

    board.pop()

    assert board.piece_at(chess.D2) is pawn
    assert pawn.move_count == 0
    assert pawn.is_on_origin


def test_has_moved_is_historical_even_after_return_to_origin() -> None:
    board = FlowBoard()
    knight = board.flow_piece("nk")

    for san in ("Nf3", "a6", "Ng1", "a5"):
        board.push_san(san)

    assert knight.square == chess.G1
    assert knight.is_on_origin
    assert knight.has_moved
    assert knight.move_count == 2


def test_capture_and_castling_deltas_preserve_piece_objects() -> None:
    capture_board = FlowBoard()
    white_e = capture_board.flow_piece("e")
    black_d = capture_board.piece_ref("black.d")
    for san in ("e4", "d5", "exd5"):
        capture_board.push_san(san)

    assert capture_board.piece_at(chess.D5) is white_e
    assert black_d.is_captured
    capture_board.pop()
    assert capture_board.piece_at(chess.E4) is white_e
    assert capture_board.piece_at(chess.D5) is black_d

    castle_board = FlowBoard()
    king = castle_board.flow_piece("k")
    rook = castle_board.flow_piece("rk")
    for san in ("e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "O-O"):
        delta = castle_board.push_san(san)
    assert delta.rook_piece_id == rook.piece_id
    assert castle_board.piece_at(chess.G1) is king
    assert castle_board.piece_at(chess.F1) is rook
    castle_board.pop()
    assert castle_board.piece_at(chess.E1) is king
    assert castle_board.piece_at(chess.H1) is rook


def test_relationships_come_from_python_chess() -> None:
    board = FlowBoard()
    knight = board.flow_piece("nk")
    pawn = board.flow_piece("e")

    assert knight.can_move_to(chess.F3)
    assert knight.controls(chess.F3)
    assert chess.F3 in knight.relations.controlled_squares
    assert pawn.piece_id in knight.relations.visible_allies

    board.push_san("e4")
    board.push_san("d5")
    assert pawn.can_capture_on(chess.D5)


def test_geometric_control_is_distinct_from_legal_movement() -> None:
    board = FlowBoard()
    for san in ("b3", "e5", "d3", "Bb4+", "Nd2", "a6"):
        board.push_san(san)

    knight = board.flow_piece("nq")
    friendly_pawn = board.flow_piece("b")

    assert knight.is_pinned
    assert knight.controls(chess.F3)
    assert not knight.can_move_to(chess.F3)
    assert knight.controls(chess.B3)
    assert friendly_pawn.is_defended
    assert knight.piece_id in friendly_pawn.relations.geometric_defenders


def test_sliding_visibility_stops_at_the_first_occupied_square() -> None:
    board = FlowBoard()
    bishop = board.flow_piece("bq")

    assert bishop.controls(chess.B2)
    assert bishop.controls(chess.D2)
    assert not bishop.controls(chess.A3)
    assert not bishop.controls(chess.E3)
    assert bishop.relations.visible_allies == {
        board.flow_piece("b").piece_id,
        board.flow_piece("d").piece_id,
    }


def test_board_with_retained_move_stack_reconstructs_exact_identities() -> None:
    source = chess.Board()
    source.push_san("d4")
    source.push_san("d5")

    board = FlowBoard(source)

    assert board.flow_piece("d").square == chess.D4
    assert board.flow_piece("d").move_count == 1
    assert board.piece_ref("black.d").square == chess.D5
    assert board.piece_ref("black.d").move_count == 1


def test_history_free_nonstarting_position_is_rejected() -> None:
    snapshot = chess.Board()
    snapshot.push_san("d4")
    history_free = chess.Board(snapshot.fen())

    with pytest.raises(
        ValueError,
        match="Persistent flow identities require a game beginning",
    ):
        FlowBoard(history_free)


def test_current_fen_can_be_exported_as_a_snapshot() -> None:
    board = FlowBoard()
    board.push_san("d4")
    board.push_san("Nf6")

    assert board.fen == board.chess_board.fen()
    assert board.fen == "rnbqkb1r/pppppppp/5n2/8/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 1 2"
