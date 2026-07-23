from __future__ import annotations

from io import StringIO
import textwrap

import chess
import chess.pgn

from chessflow.repertoire.model import RepertoireNode


class _QuietGameBuilder(chess.pgn.GameBuilder):
    def handle_error(self, error: Exception) -> None:
        self.game.errors.append(error)


def load_pgn(source: str) -> RepertoireNode:
    cleaned_source = textwrap.dedent(source).lstrip()
    try:
        game = chess.pgn.read_game(
            StringIO(cleaned_source),
            Visitor=_QuietGameBuilder,
        )
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Unable to read PGN: {exc}") from exc
    if game is None:
        raise ValueError("PGN contains no game")
    if game.errors:
        raise ValueError(f"Unable to read PGN: {game.errors[0]}")
    if (
        not game.variations
        and not cleaned_source.startswith("[")
        and cleaned_source.strip() not in {"*", "1-0", "0-1", "1/2-1/2"}
    ):
        raise ValueError("Unable to read PGN: no chess moves found")

    board = game.board()
    root = RepertoireNode(
        move=None,
        san=None,
        fen=board.fen(),
        comment=game.comment or None,
    )
    _import_children(game, root, board)
    return root


def _import_children(
    game_node: chess.pgn.GameNode,
    repertoire_node: RepertoireNode,
    board: chess.Board,
) -> None:
    for variation in game_node.variations:
        move = variation.move
        san = board.san(move)
        board.push(move)
        child = RepertoireNode(
            move=move,
            san=san,
            fen=board.fen(),
            comment=variation.comment or None,
        )
        repertoire_node.children.append(child)
        _import_children(variation, child, board)
        board.pop()
