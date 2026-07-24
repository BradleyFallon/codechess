from io import StringIO
import re

import chess
import pytest

from chessflow import parse_flow
from chessflow.quiz import QuizError, expand_lines, render_board, run_quiz
from chessflow.repertoire import load_pgn


FLOW_SOURCE = """
flow quiz
version 0.1
side white
d:
    develop.d4:
        why: Claim the center.
bq:
    develop.f4:
        when: d.developed()
        why: Develop outside the pawn chain.
e:
    develop.e3:
        when: bq.developed()
        why: Support the center.
"""


def _answers(*answers: str):
    iterator = iter(answers)
    return lambda: next(iterator)


def test_expands_root_to_leaf_lines_in_pgn_order() -> None:
    repertoire = load_pgn(
        "1. d4 d5 (1... Nf6 2. Bf4) 2. Bf4 *"
    )

    lines = expand_lines(repertoire)

    assert [
        tuple(node.san for node in line)
        for line in lines
    ] == [
        ("d4", "d5", "Bf4"),
        ("d4", "Nf6", "Bf4"),
    ]


def test_renders_board_with_white_at_the_bottom() -> None:
    rendered = render_board(chess.Board())

    assert rendered == "\n".join(
        (
            "   ┌───┬───┬───┬───┬───┬───┬───┬───┐",
            " 8 │ ♜ │ ♞ │ ♝ │ ♛ │ ♚ │ ♝ │ ♞ │ ♜ │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 7 │ ♟ │ ♟ │ ♟ │ ♟ │ ♟ │ ♟ │ ♟ │ ♟ │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 6 │   │   │   │   │   │   │   │   │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 5 │   │   │   │   │   │   │   │   │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 4 │   │   │   │   │   │   │   │   │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 3 │   │   │   │   │   │   │   │   │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 2 │ ♙ │ ♙ │ ♙ │ ♙ │ ♙ │ ♙ │ ♙ │ ♙ │",
            "   ├───┼───┼───┼───┼───┼───┼───┼───┤",
            " 1 │ ♖ │ ♘ │ ♗ │ ♕ │ ♔ │ ♗ │ ♘ │ ♖ │",
            "   └───┴───┴───┴───┴───┴───┴───┴───┘",
            "     A   B   C   D   E   F   G   H",
        )
    )


def test_correct_answer_completes_a_line() -> None:
    output = StringIO()

    completed = run_quiz(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("d4"),
        output=output,
        clear_screen=False,
    )

    assert completed
    assert "Correct." in output.getvalue()
    assert "Line complete." in output.getvalue()
    assert "First-attempt correct: 1/1" in output.getvalue()


def test_wrong_answer_then_correction_tracks_miss_and_automatic_black_move() -> None:
    output = StringIO()

    completed = run_quiz(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 d5 2. Bf4 Nf6 3. e3 *"),
        input_fn=_answers("d4", "Nf3", "Bf4", "e3"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert "1.d4 d5" in rendered
    assert "Incorrect." in rendered
    assert "Expected: Bf4" in rendered
    assert "Rule: bq.develop.f4" in rendered
    assert "Why: Develop outside the pawn chain." in rendered
    assert "Try again: " in rendered
    assert "Q3/3 · ✓1 ✗1 · S0" in rendered
    assert "First-attempt correct: 2/3" in rendered


def test_quit_stops_without_advancing_or_completing_line() -> None:
    output = StringIO()

    completed = run_quiz(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("quit"),
        output=output,
        clear_screen=False,
    )

    assert not completed
    assert "Correct." not in output.getvalue()
    assert "Line complete." not in output.getvalue()


def test_each_pgn_line_starts_with_a_fresh_session() -> None:
    output = StringIO()

    completed = run_quiz(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 d5 (1... Nf6 2. Bf4) 2. Bf4 *"),
        input_fn=_answers("d4", "Bf4", "", "d4", "Bf4"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert rendered.count("Line complete.") == 2
    assert "CodeChess · L1/2 · Q1/2" in rendered
    assert "CodeChess · L2/2 · Q1/2" in rendered
    status_lines = re.findall(r"── CodeChess.*?──", rendered)
    assert all(len(line) <= 50 for line in status_lines)


def test_quiz_fails_loudly_on_flow_ambiguity() -> None:
    definition = parse_flow(
        """
        flow ambiguous-quiz
        version 0.1
        side white
        d:
            develop.d4:
        e:
            develop.e4:
        """
    )

    with pytest.raises(QuizError, match="Flow ambiguity"):
        run_quiz(
            definition,
            load_pgn("1. d4 *"),
            input_fn=_answers(),
            output=StringIO(),
            clear_screen=False,
        )


def test_terminal_move_completes_quiz_line_without_later_pgn_moves() -> None:
    definition = parse_flow(
        """
        flow terminal-quiz
        version 0.1
        side white
        d:
            develop.d4:
                terminal: center-claimed
        """
    )
    output = StringIO()

    completed = run_quiz(
        definition,
        load_pgn("1. d4 d5 2. c4 *"),
        input_fn=_answers("d4"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert rendered.count("Your move: ") == 1
    assert "Q1/1" in rendered
    assert "First-attempt correct: 1/1" in rendered
