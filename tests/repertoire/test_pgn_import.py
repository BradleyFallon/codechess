import chess
import pytest

from chessflow.repertoire import load_pgn


def test_loads_main_line_positions_after_each_move() -> None:
    root = load_pgn(
        """
        [Event "Main line"]

        1. d4 d5 2. Bf4 Nf6 *
        """
    )

    d4 = root.children[0]
    d5 = d4.children[0]
    bf4 = d5.children[0]
    nf6 = bf4.children[0]

    board = chess.Board()
    assert root.move is None
    assert root.san is None
    assert root.fen == board.fen()
    assert d4.san == "d4"
    assert d4.move == chess.Move.from_uci("d2d4")
    board.push_san("d4")
    assert d4.fen == board.fen()
    board.push_san("d5")
    board.push_san("Bf4")
    board.push_san("Nf6")
    assert nf6.fen == board.fen()
    assert nf6.children == []


def test_preserves_sibling_variation_order_and_comments() -> None:
    root = load_pgn(
        """
        [Event "Branches"]

        1. d4 {Start London} d5 {Main response}
            (1... Nf6 {Indian response})
            (1... e6 {French setup})
        2. Bf4 *
        """
    )

    d4 = root.children[0]

    assert d4.comment == "Start London"
    assert [child.san for child in d4.children] == ["d5", "Nf6", "e6"]
    assert [child.comment for child in d4.children] == [
        "Main response",
        "Indian response",
        "French setup",
    ]
    assert d4.children[0].children[0].san == "Bf4"


def test_preserves_nested_variations_as_distinct_branches() -> None:
    root = load_pgn(
        """
        [Event "Nested"]

        1. d4 d5
            (1... Nf6 2. Bf4 g6 (2... e6))
        2. Bf4 *
        """
    )

    d4 = root.children[0]
    nf6 = d4.children[1]
    bf4 = nf6.children[0]

    assert nf6.san == "Nf6"
    assert bf4.san == "Bf4"
    assert [child.san for child in bf4.children] == ["g6", "e6"]
    assert d4.children[0] is not nf6


@pytest.mark.parametrize("source", ("", "not a PGN", "1. e5 *"))
def test_empty_or_unreadable_pgn_fails_clearly(source: str) -> None:
    with pytest.raises(ValueError, match="PGN contains no game|Unable to read PGN"):
        load_pgn(source)
