from __future__ import annotations

from collections.abc import Callable
import sys
import textwrap
from typing import TextIO

from chessflow.flow_language.ast import FlowDefinition
from chessflow.quiz import expand_lines, render_board
from chessflow.reporting import format_san_path
from chessflow.repertoire import RepertoireNode
from chessflow.session import FlowSession


class LearnError(RuntimeError):
    pass


def run_learn(
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
    seen_rules: set[str] = set()

    for line_number, line in enumerate(lines, start=1):
        session = FlowSession.fresh(definition)
        path: tuple[str, ...] = ()
        question = 0
        question_total = (len(line) + 1) // 2
        node_index = 0
        new_rules: list[tuple[str, str | None]] = []
        reviewed_rules = 0

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
                raise LearnError(f"Flow dead end at {position}")
            if len(candidates) > 1:
                actions = ", ".join(
                    candidate.rule.definition.action.canonical_key
                    for candidate in candidates
                )
                raise LearnError(f"Flow ambiguity at {position}: {actions}")

            selected = candidates[0]
            selected_san = session.board.chess_board.san(selected.move)
            if selected.move != reference_node.move:
                raise LearnError(
                    f"Flow disagreement at {position}: "
                    f"expected {reference_node.san}, selected {selected_san}"
                )

            action_key = selected.rule.definition.action.canonical_key
            why = selected.rule.definition.why
            preceding_comment = (
                line[node_index - 1].comment
                if node_index
                else repertoire.comment
            )
            _clear(stream, clear_screen)
            stream.write(
                _status_line(
                    line_number,
                    len(lines),
                    question,
                    question_total,
                    len(seen_rules),
                )
                + "\n"
            )
            stream.write(position + "\n\n")
            stream.write(render_board(session.board.chess_board) + "\n\n")
            coach = _distinct_paragraphs(preceding_comment)
            if coach:
                stream.write("Coach:\n")
                stream.write(_wrapped_paragraphs(coach) + "\n\n")

            prompt = "Your move: "
            while True:
                answer = _prompt(stream, read_input, prompt).strip()
                if answer.lower() == "quit":
                    return False
                try:
                    entered_move = session.board.chess_board.parse_san(answer)
                except ValueError:
                    entered_move = None

                if entered_move == selected.move:
                    break

                stream.write(
                    "\nNot quite.\n\n"
                    f"Expected: {selected_san}\n"
                    f"Rule: {action_key}\n"
                )
                guidance = _distinct_paragraphs(why)
                if guidance:
                    stream.write("\n" + _wrapped_paragraphs(guidance) + "\n")
                prompt = f"\nType {selected_san} to continue: "

            is_new_rule = action_key not in seen_rules
            if is_new_rule:
                seen_rules.add(action_key)
                new_rules.append((action_key, why))
            else:
                reviewed_rules += 1

            session.runtime.execute(selected, session.board)
            assert reference_node.san is not None
            path = (*path, reference_node.san)
            node_index += 1
            stream.write(f"\nCorrect: {selected_san}\n\n")
            stream.write("NEW RULE\n" if is_new_rule else "REVIEW\n")
            if is_new_rule:
                stream.write(action_key + "\n")
            reinforcement = _distinct_paragraphs(
                why,
                reference_node.comment,
            )
            if reinforcement:
                stream.write(
                    "\n" + _wrapped_paragraphs(reinforcement) + "\n"
                )
            answer = _prompt(
                stream,
                read_input,
                "\nPress Enter to continue. ",
            )
            if answer.strip().lower() == "quit":
                return False

        _clear(stream, clear_screen)
        stream.write(
            _line_complete_status(
                line_number,
                len(lines),
                len(seen_rules),
            )
            + "\n\n"
        )
        stream.write("Line complete.\n\n")
        stream.write(_new_rule_summary(new_rules))
        stream.write(f"\nReviewed: {reviewed_rules} rules\n")
        if line_number < len(lines):
            answer = _prompt(
                stream,
                read_input,
                "\nPress Enter for the next line. ",
            )
            if answer.strip().lower() == "quit":
                return False

    stream.write(
        "\n"
        + _walkthrough_complete_status(len(lines), len(seen_rules))
        + "\n\n"
        "Opening walkthrough complete.\n\n"
        "Run the quiz when ready:\n\n"
        "  codechess quiz opening.flow repertoire.pgn\n"
    )
    return True


def _status_line(
    line_number: int,
    line_total: int,
    question: int,
    question_total: int,
    rules: int,
) -> str:
    return _framed_status(
        f"── Learn · L{line_number}/{line_total} "
        f"· Q{question}/{question_total} · Rules {rules} "
    )


def _line_complete_status(
    line_number: int,
    line_total: int,
    rules: int,
) -> str:
    return _framed_status(
        f"── Learn · L{line_number}/{line_total} complete · Rules {rules} "
    )


def _walkthrough_complete_status(lines: int, rules: int) -> str:
    return _framed_status(
        f"── Learn complete · {lines} lines · {rules} rules "
    )


def _framed_status(label: str) -> str:
    if len(label) >= 50:
        return label[:48] + "──"
    return label + "─" * (50 - len(label))


def _new_rule_summary(
    new_rules: list[tuple[str, str | None]],
) -> str:
    if not new_rules:
        return "New rules: none\n"

    sections = ["New rules:"]
    for action_key, why in new_rules:
        sections.append(f"  {action_key}")
        if why:
            sections.append(
                textwrap.fill(
                    _normalize(why),
                    width=50,
                    initial_indent="    ",
                    subsequent_indent="    ",
                )
            )
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def _distinct_paragraphs(*paragraphs: str | None) -> tuple[str, ...]:
    distinct: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        normalized = _normalize(paragraph)
        if normalized and normalized not in distinct:
            distinct.append(normalized)
    return tuple(distinct)


def _wrapped_paragraphs(paragraphs: tuple[str, ...]) -> str:
    return "\n\n".join(
        textwrap.fill(paragraph, width=50) for paragraph in paragraphs
    )


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _clear(output: TextIO, enabled: bool) -> None:
    if enabled:
        output.write("\033[2J\033[H")


def _prompt(
    output: TextIO,
    input_fn: Callable[[], str],
    prompt: str,
) -> str:
    output.write(prompt)
    output.flush()
    return input_fn()
