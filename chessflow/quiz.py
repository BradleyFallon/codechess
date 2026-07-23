from __future__ import annotations

from collections.abc import Callable
import sys
from typing import TextIO

import chess

from chessflow.flow_language.ast import FlowDefinition
from chessflow.reporting import format_san_path
from chessflow.repertoire import RepertoireNode
from chessflow.session import FlowSession


class QuizError(RuntimeError):
    pass


_PIECE_SYMBOLS = {
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
}


def expand_lines(root: RepertoireNode) -> list[tuple[RepertoireNode, ...]]:
    lines: list[tuple[RepertoireNode, ...]] = []

    def visit(
        node: RepertoireNode,
        path: tuple[RepertoireNode, ...],
    ) -> None:
        if not node.children:
            lines.append(path)
            return
        for child in node.children:
            visit(child, (*path, child))

    visit(root, ())
    return lines


def render_board(board: chess.Board) -> str:
    lines = ["   ┌───┬───┬───┬───┬───┬───┬───┬───┐"]
    for rank in range(7, -1, -1):
        cells = []
        for file_index in range(8):
            piece = board.piece_at(chess.square(file_index, rank))
            cells.append(
                " " if piece is None else _PIECE_SYMBOLS[piece.symbol()]
            )
        lines.append(f" {rank + 1} │ " + " │ ".join(cells) + " │")
        if rank:
            lines.append("   ├───┼───┼───┼───┼───┼───┼───┼───┤")
    lines.extend(
        (
            "   └───┴───┴───┴───┴───┴───┴───┴───┘",
            "     A   B   C   D   E   F   G   H",
        )
    )
    return "\n".join(lines)


def run_quiz(
    definition: FlowDefinition,
    repertoire: RepertoireNode,
    *,
    input_fn: Callable[[], str] | None = None,
    output: TextIO | None = None,
    clear_screen: bool = True,
) -> bool:
    read_input = input if input_fn is None else input_fn
    stream = sys.stdout if output is None else output
    lines = expand_lines(repertoire)
    streak = 0

    for line_number, line in enumerate(lines, start=1):
        session = FlowSession.fresh(definition)
        path: tuple[str, ...] = ()
        question = 0
        first_attempt_correct = 0
        missed_questions = 0
        question_total = (len(line) + 1) // 2
        node_index = 0

        while node_index < len(line):
            reference_node = line[node_index]
            if (
                session.board.chess_board.turn
                != definition.side.chess_color
            ):
                assert reference_node.move is not None
                assert reference_node.san is not None
                session.board.push(reference_node.move)
                path = (*path, reference_node.san)
                node_index += 1
                continue

            question += 1
            candidates = session.runtime.evaluate_turn(session.board)
            position = format_san_path(path)
            if not candidates:
                raise QuizError(f"Flow dead end at {position}")
            if len(candidates) > 1:
                actions = ", ".join(
                    candidate.rule.definition.action.canonical_key
                    for candidate in candidates
                )
                raise QuizError(f"Flow ambiguity at {position}: {actions}")

            selected = candidates[0]
            selected_san = session.board.chess_board.san(selected.move)
            if selected.move != reference_node.move:
                raise QuizError(
                    f"Flow disagreement at {position}: "
                    f"expected {reference_node.san}, selected {selected_san}"
                )

            if clear_screen:
                stream.write("\033[2J\033[H")
            stream.write(
                _status_line(
                    line_number,
                    len(lines),
                    question,
                    question_total,
                    first_attempt_correct,
                    missed_questions,
                    streak,
                )
                + "\n"
            )
            stream.write(position + "\n\n")
            stream.write(render_board(session.board.chess_board) + "\n\n")

            first_attempt = True
            while True:
                prompt = "Your move: " if first_attempt else "Try again: "
                answer = _prompt(stream, read_input, prompt).strip()
                if answer.lower() == "quit":
                    return False
                try:
                    entered_move = session.board.chess_board.parse_san(answer)
                except ValueError:
                    entered_move = None

                if entered_move == selected.move:
                    if first_attempt:
                        first_attempt_correct += 1
                        streak += 1
                    session.runtime.execute(selected, session.board)
                    assert reference_node.san is not None
                    path = (*path, reference_node.san)
                    node_index += 1
                    stream.write("Correct.\n")
                    break

                if first_attempt:
                    missed_questions += 1
                    streak = 0
                first_attempt = False
                why = selected.rule.definition.why or "(none)"
                stream.write(
                    "\nIncorrect.\n"
                    f"Expected: {selected_san}\n"
                    "Rule: "
                    f"{selected.rule.definition.action.canonical_key}\n"
                    f"Why: {why}\n\n"
                )

        stream.write(
            "\nLine complete.\n"
            "First-attempt correct: "
            f"{first_attempt_correct}/{question_total}\n"
        )
        if line_number < len(lines):
            answer = _prompt(stream, read_input, "Press Enter for next line. ")
            if answer.strip().lower() == "quit":
                return False

    return True


def _status_line(
    line_number: int,
    line_total: int,
    question: int,
    question_total: int,
    correct: int,
    missed: int,
    streak: int,
) -> str:
    status = (
        f"── CodeChess · L{line_number}/{line_total} "
        f"· Q{question}/{question_total} "
        f"· ✓{correct} ✗{missed} · S{streak} ──"
    )
    if len(status) <= 50:
        return status
    return (
        f"── CC · L{line_number}/{line_total} · Q{question}/{question_total} "
        f"· ✓{correct} ✗{missed} · S{streak} ──"
    )[:50]


def _prompt(
    output: TextIO,
    input_fn: Callable[[], str],
    prompt: str,
) -> str:
    output.write(prompt)
    output.flush()
    return input_fn()
