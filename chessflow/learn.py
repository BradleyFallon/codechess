from __future__ import annotations

from collections.abc import Callable
import sys
import textwrap
from typing import TextIO

import chess

from chessflow.flow_language.ast import FlowDefinition
from chessflow.learning import (
    GoalEventKind,
    GoalEventView,
    GoalView,
    LearnPhase,
    LearnSession,
    LearnSessionError,
    LearnView,
    MoveFeedbackKind,
    RuleLessonView,
)
from chessflow.quiz import render_board
from chessflow.reporting import format_san_path
from chessflow.repertoire import RepertoireNode


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
    try:
        session = LearnSession.start(definition, repertoire)
        return _run_terminal_session(
            session,
            read_input,
            stream,
            clear_screen,
        )
    except LearnSessionError as exc:
        raise LearnError(str(exc)) from exc


def _run_terminal_session(
    session: LearnSession,
    read_input: Callable[[], str],
    stream: TextIO,
    clear_screen: bool,
) -> bool:
    while True:
        view = session.view()
        if view.phase is LearnPhase.AWAITING_MOVE:
            _render_question(stream, view, clear_screen)
            prompt = "Your move: "
            while True:
                answer = _prompt(stream, read_input, prompt).strip()
                if answer.lower() == "quit":
                    return False
                view = session.submit_san(answer)
                feedback = view.feedback
                assert feedback is not None
                if feedback.kind is MoveFeedbackKind.CORRECT:
                    break
                _render_incorrect_feedback(stream, view)
                prompt = (
                    f"\nType {feedback.expected.san} to continue: "
                )
            continue

        if view.phase is LearnPhase.SHOWING_FEEDBACK:
            _render_correct_feedback(stream, view, clear_screen)
            answer = _prompt(
                stream,
                read_input,
                "\nPress Enter to continue. ",
            )
            if answer.strip().lower() == "quit":
                return False
            session.continue_()
            continue

        if view.phase is LearnPhase.LINE_COMPLETE:
            _render_line_complete(stream, view, clear_screen)
            if view.line_number < view.line_total:
                answer = _prompt(
                    stream,
                    read_input,
                    "\nPress Enter for the next line. ",
                )
                if answer.strip().lower() == "quit":
                    return False
            session.continue_()
            continue

        _render_course_complete(stream, view)
        return True


def _render_question(
    stream: TextIO,
    view: LearnView,
    clear_screen: bool,
) -> None:
    _clear(stream, clear_screen)
    stream.write(_status_line(view) + "\n")
    stream.write(format_san_path(view.path_san) + "\n\n")
    stream.write(render_board(chess.Board(view.fen)) + "\n\n")
    if view.goal_events:
        stream.write(_goal_events_text(view.goal_events) + "\n\n")
    elif view.current_goal is not None:
        stream.write(
            _goal_context(
                view.current_goal,
                view.fallback_goal,
                include_fallback=view.question_number == 1,
            )
            + "\n\n"
        )
    if view.coach:
        stream.write("Coach:\n")
        stream.write(_wrapped_paragraphs(view.coach) + "\n\n")


def _render_incorrect_feedback(
    stream: TextIO,
    view: LearnView,
) -> None:
    feedback = view.feedback
    assert feedback is not None
    label = (
        "Invalid SAN."
        if feedback.kind is MoveFeedbackKind.INVALID_SAN
        else "Not quite."
    )
    stream.write(
        f"\n{label}\n\n"
        f"Expected: {feedback.expected.san}\n"
        f"Rule: {feedback.rule_key}\n"
    )
    if feedback.explanation:
        stream.write(
            "\n" + _wrapped_paragraphs(feedback.explanation) + "\n"
        )


def _render_correct_feedback(
    stream: TextIO,
    view: LearnView,
    clear_screen: bool,
) -> None:
    feedback = view.feedback
    assert feedback is not None
    _clear(stream, clear_screen)
    stream.write(_status_line(view) + "\n")
    stream.write(format_san_path(view.path_san) + "\n\n")
    stream.write(render_board(chess.Board(view.fen)) + "\n\n")
    stream.write(f"Correct: {feedback.expected.san}\n\n")
    if view.goal_events:
        stream.write(_goal_events_text(view.goal_events) + "\n\n")
    stream.write("NEW RULE\n" if feedback.is_new_rule else "REVIEW\n")
    if feedback.is_new_rule:
        stream.write(feedback.rule_key + "\n")
    if feedback.explanation:
        stream.write(
            "\n" + _wrapped_paragraphs(feedback.explanation) + "\n"
        )
    if view.terminal is not None:
        explanation = (
            (
                "Opening preparation ends here. Continue the game "
                "from this position."
            )
            if feedback.was_correction
            else view.terminal.explanation
        )
        stream.write(
            "\n"
            + _opening_exit_text(view.terminal.key, explanation)
            + "\n"
        )


def _render_line_complete(
    stream: TextIO,
    view: LearnView,
    clear_screen: bool,
) -> None:
    _clear(stream, clear_screen)
    stream.write(
        _framed_status(
            f"── Learn · L{view.line_number}/{view.line_total} "
            f"complete · Rules {view.rules_seen} "
        )
        + "\n\n"
    )
    stream.write("Line complete.\n\n")
    stream.write(_new_rule_summary(view.new_rules))
    stream.write(f"\nReviewed: {view.review_count} rules\n")


def _render_course_complete(stream: TextIO, view: LearnView) -> None:
    stream.write(
        "\n"
        + _framed_status(
            f"── Learn complete · {view.line_total} lines "
            f"· {view.rules_seen} rules "
        )
        + "\n\n"
        "Opening walkthrough complete.\n\n"
        "Run the quiz when ready:\n\n"
        "  codechess quiz opening.flow repertoire.pgn\n"
    )


def _goal_events_text(events: tuple[GoalEventView, ...]) -> str:
    sections: list[str] = []
    for event in events:
        if event.kind is GoalEventKind.NEW_GOAL:
            sections.append(
                "NEW GOAL\n\n"
                + _goal_context(
                    event.goal,
                    event.fallback,
                    include_fallback=True,
                )
            )
        elif event.kind is GoalEventKind.GOAL_COMPLETE:
            sections.append(
                "GOAL COMPLETE\n\n"
                + _goal_title(event.previous_goal)
                + "\n\n"
                + _goal_context(
                    event.goal,
                    event.fallback,
                    include_fallback=True,
                    heading="Current goal",
                )
            )
        elif event.kind is GoalEventKind.GOAL_RETIRED:
            reason = event.reason or "The goal is no longer viable."
            sections.append(
                "GOAL RETIRED\n\n"
                + _goal_title(event.previous_goal)
                + "\n\nReason:\n"
                + textwrap.fill(reason, width=50)
                + "\n\n"
                + _goal_context(
                    event.goal,
                    event.fallback,
                    include_fallback=True,
                    heading="Current goal",
                )
            )
        else:
            sections.append(
                "FALLBACK UPDATED\n\n"
                + _goal_context(
                    event.goal,
                    event.fallback,
                    include_fallback=True,
                )
            )
    return "\n\n".join(sections)


def _goal_context(
    current: GoalView | None,
    fallback: GoalView | None,
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
        f"{heading}:\n" + _sentence(current.title),
        "Plan:\n" + textwrap.fill(current.plan, width=50),
    ]
    if include_fallback:
        sections.append("Fallback:\n" + _goal_title(fallback))
    return "\n\n".join(sections)


def _goal_title(goal: GoalView | None) -> str:
    return "None" if goal is None else _sentence(goal.title)


def _opening_exit_text(terminal: str, explanation: str) -> str:
    return (
        "OPENING EXIT\n\n"
        + terminal
        + "\n\n"
        + textwrap.fill(_normalize(explanation), width=50)
    )


def _status_line(view: LearnView) -> str:
    return _framed_status(
        f"── Learn · L{view.line_number}/{view.line_total} "
        f"· Q{view.question_number}/{view.question_total} "
        f"· Rules {view.rules_seen} "
    )


def _framed_status(label: str) -> str:
    if len(label) >= 50:
        return label[:48] + "──"
    return label + "─" * (50 - len(label))


def _new_rule_summary(rules: tuple[RuleLessonView, ...]) -> str:
    if not rules:
        return "New rules: none\n"
    sections = ["New rules:"]
    for rule in rules:
        sections.append(f"  {rule.rule_key}")
        if rule.explanation:
            sections.append(
                textwrap.fill(
                    _normalize(rule.explanation),
                    width=50,
                    initial_indent="    ",
                    subsequent_indent="    ",
                )
            )
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def _wrapped_paragraphs(paragraphs: tuple[str, ...]) -> str:
    return "\n\n".join(
        textwrap.fill(paragraph, width=50) for paragraph in paragraphs
    )


def _sentence(text: str) -> str:
    normalized = _normalize(text)
    return (
        normalized
        if normalized.endswith((".", "!", "?"))
        else normalized + "."
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
