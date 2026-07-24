from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import sys
import textwrap
from typing import TextIO

from chessflow.chess_model import FlowBoard
from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime import (
    FlowRuntime,
    GoalDeadEndError,
    GoalRuntime,
    GoalStatus,
)
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
        goal_display = _GoalDisplayState()

        while node_index < len(line):
            reference_node = line[node_index]
            if (
                session.board.chess_board.turn
                != definition.side.chess_color
            ):
                assert reference_node.move is not None
                assert reference_node.san is not None
                session.runtime.push_opponent(
                    reference_node.move,
                    session.board,
                )
                path = (*path, reference_node.san)
                node_index += 1
                continue

            question += 1
            position = format_san_path(path)
            try:
                candidates = session.runtime.evaluate_turn(session.board)
            except GoalDeadEndError as exc:
                raise LearnError(str(exc.at_path(position))) from exc
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
                if line_number == 1
                else None
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
            goal_text = _goal_update_text(
                session.runtime,
                session.board,
                goal_display,
                show_normal=True,
            )
            if goal_text:
                stream.write(goal_text + "\n\n")
            coach = _distinct_paragraphs(preceding_comment)
            if coach:
                stream.write("Coach:\n")
                stream.write(_wrapped_paragraphs(coach) + "\n\n")

            prompt = "Your move: "
            needed_correction = False
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

                needed_correction = True
                stream.write(
                    "\nNot quite.\n\n"
                    f"Expected: {selected_san}\n"
                    f"Rule: {action_key}\n"
                )
                guidance = _distinct_paragraphs(
                    why,
                    reference_node.comment,
                )
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
            stream.write(format_san_path(path) + "\n\n")
            stream.write(render_board(session.board.chess_board) + "\n\n")
            stream.write(f"Correct: {selected_san}\n\n")
            goal_text = _goal_update_text(
                session.runtime,
                session.board,
                goal_display,
                show_normal=False,
            )
            if goal_text:
                stream.write(goal_text + "\n\n")
            stream.write("NEW RULE\n" if is_new_rule else "REVIEW\n")
            if is_new_rule:
                stream.write(action_key + "\n")
            reinforcement = (
                ()
                if needed_correction
                else _distinct_paragraphs(
                    why,
                    reference_node.comment,
                )
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


@dataclass(slots=True)
class _GoalDisplayState:
    initialized: bool = False
    current_key: str | None = None
    fallback_key: str | None = None
    statuses: dict[str, GoalStatus] = field(default_factory=dict)


def _goal_update_text(
    runtime: FlowRuntime,
    board: FlowBoard,
    state: _GoalDisplayState,
    *,
    show_normal: bool,
) -> str:
    if not runtime.definition.goals:
        return ""

    current = runtime.current_goal(board)
    fallback = runtime.fallback_goal(board)
    statuses = {
        goal.key: runtime.goal_status(goal.key)
        for goal in runtime.definition.goals
    }
    current_key = (
        None if current is None else current.definition.key
    )
    fallback_key = (
        None if fallback is None else fallback.definition.key
    )

    if not state.initialized:
        state.initialized = True
        state.current_key = current_key
        state.fallback_key = fallback_key
        state.statuses = statuses
        return _goal_context(current, fallback, include_fallback=True)

    sections: list[str] = []
    current_changed = current_key != state.current_key
    fallback_changed = fallback_key != state.fallback_key
    if current_changed and state.current_key is not None:
        previous_definition = next(
            goal
            for goal in runtime.definition.goals
            if goal.key == state.current_key
        )
        previous_status = statuses[state.current_key]
        if previous_status is GoalStatus.COMPLETED:
            sections.append(
                "GOAL COMPLETE\n\n"
                + _sentence(previous_definition.title)
                + "\n\n"
                + _goal_context(
                    current,
                    fallback,
                    include_fallback=True,
                    heading="Current goal",
                )
            )
        elif previous_status is GoalStatus.RETIRED:
            sections.append(
                "GOAL RETIRED\n\n"
                + _sentence(previous_definition.title)
                + "\n\nReason:\n"
                + textwrap.fill(
                    previous_definition.abandoned,
                    width=50,
                )
                + "\n\n"
                + _goal_context(
                    current,
                    fallback,
                    include_fallback=True,
                    heading="Current goal",
                )
            )
        else:
            sections.append(
                "NEW GOAL\n\n"
                + _goal_context(
                    current,
                    fallback,
                    include_fallback=True,
                )
            )
    elif current_changed:
        sections.append(
            "NEW GOAL\n\n"
            + _goal_context(current, fallback, include_fallback=True)
        )
    elif fallback_changed:
        sections.append(
            "FALLBACK UPDATED\n\n"
            + _goal_context(current, fallback, include_fallback=True)
        )
    elif not sections and show_normal:
        sections.append(
            _goal_context(
                current,
                fallback,
                include_fallback=current_key != state.current_key,
            )
        )

    state.current_key = current_key
    state.fallback_key = fallback_key
    state.statuses = statuses
    return "\n\n".join(section for section in sections if section)


def _goal_context(
    current: GoalRuntime | None,
    fallback: GoalRuntime | None,
    *,
    include_fallback: bool,
    heading: str = "Goal",
) -> str:
    if current is None:
        sections = [f"{heading}:\nNone"]
        if include_fallback:
            sections.append("Fallback:\nNone")
        return "\n\n".join(sections)
    sections = [
        f"{heading}:\n" + _sentence(current.definition.title),
        "Plan:\n" + textwrap.fill(current.definition.plan, width=50),
    ]
    if include_fallback:
        fallback_title = (
            "None"
            if fallback is None
            else _sentence(fallback.definition.title)
        )
        sections.append("Fallback:\n" + fallback_title)
    return "\n\n".join(sections)


def _sentence(text: str) -> str:
    normalized = _normalize(text)
    return normalized if normalized.endswith((".", "!", "?")) else normalized + "."


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
