from pathlib import Path

import chess
import pytest

from chessflow import parse_flow
from chessflow.learning import (
    GoalEventKind,
    LearnPhase,
    LearnSession,
    LearnSessionError,
    MoveFeedbackKind,
)
from chessflow.repertoire import load_pgn


BASIC_FLOW = """
flow learning-session
version 0.1
side white
d:
    develop.d4:
        why: Claim the center.
bq:
    develop.f4:
        when: d.developed()
        why: Develop outside the pawn chain.
"""

GOAL_FLOW = """
flow learning-goals
version 0.2
side white
goals:
    urgent:
        when: square.a6.has(enemy.pawn)
        while: true
        complete: false
        title: Use the urgent plan
        plan: Respond before returning to development.
        abandoned: The urgent plan is no longer viable.
    foundation:
        while: true
        complete: false
        title: Build the foundation
        plan: Claim the center and stay flexible.
        abandoned: The foundation is no longer viable.
d:
    develop.d4:
        goals: foundation
c:
    develop.c4:
        goals: urgent
"""


def _session(
    flow: str = BASIC_FLOW,
    pgn: str = "1. d4 {Keep the c-pawn flexible.} *",
) -> LearnSession:
    return LearnSession.start(parse_flow(flow), load_pgn(pgn))


def test_initial_view_has_goal_moves_and_structured_expected_move() -> None:
    session = _session(
        GOAL_FLOW,
        "{Start with a flexible center.} 1. d4 *",
    )

    view = session.view()

    assert view.phase is LearnPhase.AWAITING_MOVE
    assert view.fen == chess.Board().fen()
    assert view.path_san == ()
    assert (view.line_number, view.line_total) == (1, 1)
    assert (view.question_number, view.question_total) == (1, 1)
    assert view.current_goal is not None
    assert view.current_goal.key == "foundation"
    assert view.fallback_goal is None
    assert view.coach == ("Start with a flexible center.",)
    assert len(view.legal_moves) == 20
    assert view.expected_move is not None
    assert view.expected_move.uci == "d2d4"
    assert view.expected_move.san == "d4"
    assert view.expected_move.from_square == "d2"
    assert view.expected_move.to_square == "d4"
    assert view.expected_move.promotion is None


def test_empty_repertoire_fails_with_domain_error() -> None:
    with pytest.raises(
        LearnSessionError,
        match="Repertoire contains no learnable lines",
    ):
        _session(pgn="*")


def test_custom_repertoire_position_fails_with_domain_error() -> None:
    pgn = """
    [SetUp "1"]
    [FEN "7k/8/8/8/8/8/8/K7 w - - 0 1"]

    1. Kb2 *
    """

    with pytest.raises(
        LearnSessionError,
        match="Flow and repertoire must begin from the same position",
    ):
        _session(pgn=pgn)


def test_invalid_san_and_legal_incorrect_move_do_not_advance() -> None:
    session = _session()
    initial_fen = session.view().fen

    invalid = session.submit_san("not-a-move")

    assert invalid.phase is LearnPhase.AWAITING_MOVE
    assert invalid.feedback is not None
    assert invalid.feedback.kind is MoveFeedbackKind.INVALID_SAN
    assert invalid.fen == initial_fen
    assert invalid.path_san == ()

    incorrect = session.submit_san("e4")

    assert incorrect.phase is LearnPhase.AWAITING_MOVE
    assert incorrect.feedback is not None
    assert incorrect.feedback.kind is MoveFeedbackKind.INCORRECT
    assert incorrect.feedback.explanation == (
        "Claim the center.",
        "Keep the c-pawn flexible.",
    )
    assert incorrect.fen == initial_fen
    assert incorrect.path_san == ()


def test_correct_move_advances_and_correction_detail_appears_once() -> None:
    session = _session()
    session.submit_san("e4")

    corrected = session.submit_move(chess.Move.from_uci("d2d4"))

    assert corrected.phase is LearnPhase.SHOWING_FEEDBACK
    assert corrected.feedback is not None
    assert corrected.feedback.kind is MoveFeedbackKind.CORRECT
    assert corrected.feedback.was_correction
    assert corrected.feedback.explanation == ()
    assert corrected.path_san == ("d4",)
    assert chess.Board(corrected.fen).piece_at(chess.D4) == chess.Piece(
        chess.PAWN,
        chess.WHITE,
    )


def test_continue_enforces_phase_and_advances_to_line_and_course_completion() -> None:
    session = _session()

    with pytest.raises(LearnSessionError, match="awaiting a move"):
        session.continue_()

    session.submit_san("d4")
    line_complete = session.continue_()

    assert line_complete.phase is LearnPhase.LINE_COMPLETE
    course_complete = session.continue_()
    assert course_complete.phase is LearnPhase.COURSE_COMPLETE
    with pytest.raises(LearnSessionError, match="already complete"):
        session.continue_()


def test_next_line_progression_uses_a_fresh_flow_session() -> None:
    session = _session(
        pgn="1. d4 d5 (1... Nf6) 2. Bf4 *",
    )
    session.submit_san("d4")
    session.continue_()
    session.submit_san("Bf4")
    session.continue_()
    next_line = session.continue_()

    assert next_line.phase is LearnPhase.AWAITING_MOVE
    assert next_line.line_number == 2
    assert next_line.question_number == 1
    assert next_line.path_san == ()
    assert next_line.expected_move is not None
    assert next_line.expected_move.san == "d4"


def test_pending_goal_activation_emits_new_goal_event() -> None:
    session = _session(
        GOAL_FLOW,
        "1. d4 a6 2. c4 *",
    )
    session.submit_san("d4")

    view = session.continue_()

    assert view.goal_events[0].kind is GoalEventKind.NEW_GOAL
    assert view.goal_events[0].goal is not None
    assert view.goal_events[0].goal.key == "urgent"
    assert view.goal_events[0].fallback is not None
    assert view.goal_events[0].fallback.key == "foundation"


@pytest.mark.parametrize(
    ("first_goal", "expected_kind"),
    (
        (
            """
            while: true
            complete: played(d.develop.d4)
            """,
            GoalEventKind.GOAL_COMPLETE,
        ),
        (
            """
            while: square.a7.has(enemy.pawn)
            complete: false
            """,
            GoalEventKind.GOAL_RETIRED,
        ),
    ),
)
def test_current_goal_completion_and_retirement_events(
    first_goal: str,
    expected_kind: GoalEventKind,
) -> None:
    flow = f"""
    flow goal-transition
    version 0.2
    side white
    goals:
        first:
            {first_goal}
            title: First plan
            plan: Use the first plan.
            abandoned: The first plan lost viability.
        fallback:
            while: true
            complete: false
            title: Fallback plan
            plan: Use the fallback plan.
            abandoned: The fallback is unavailable.
    d:
        develop.d4:
            goals: first
    c:
        develop.c4:
            goals: fallback
    """
    pgn = (
        "1. d4 *"
        if expected_kind is GoalEventKind.GOAL_COMPLETE
        else "1. d4 a6 2. c4 *"
    )
    session = _session(flow, pgn)
    submitted = session.submit_san("d4")
    view = (
        submitted
        if expected_kind is GoalEventKind.GOAL_COMPLETE
        else session.continue_()
    )

    event = view.goal_events[0]
    assert event.kind is expected_kind
    assert event.previous_goal is not None
    assert event.previous_goal.key == "first"
    assert event.goal is not None
    assert event.goal.key == "fallback"
    if expected_kind is GoalEventKind.GOAL_RETIRED:
        assert event.reason == "The first plan lost viability."


def test_fallback_update_event_keeps_current_goal() -> None:
    flow = """
    flow fallback-update
    version 0.2
    side white
    goals:
        current:
            while: true
            complete: false
            title: Current
            plan: Keep the current plan.
            abandoned: Current retired.
        new-fallback:
            when: square.a6.has(enemy.pawn)
            while: true
            complete: false
            title: New fallback
            plan: Use the new fallback.
            abandoned: New fallback retired.
        old-fallback:
            while: true
            complete: false
            title: Old fallback
            plan: Use the old fallback.
            abandoned: Old fallback retired.
    d:
        develop.d4:
            goals: current
    c:
        develop.c4:
            goals: current
            when: played(d.develop.d4)
    """
    session = _session(flow, "1. d4 a6 2. c4 *")
    session.submit_san("d4")

    view = session.continue_()

    event = view.goal_events[0]
    assert event.kind is GoalEventKind.FALLBACK_UPDATED
    assert event.goal is not None
    assert event.goal.key == "current"
    assert event.fallback is not None
    assert event.fallback.key == "new-fallback"


def test_terminal_exit_ends_line_immediately() -> None:
    flow = """
    flow terminal-learning
    version 0.1
    side white
    d:
        develop.d4:
            terminal: prepared
            why: The opening has reached its planned handoff.
    """
    session = _session(flow, "1. d4 d5 2. c4 *")

    feedback = session.submit_san("d4")

    assert feedback.terminal is not None
    assert feedback.terminal.key == "prepared"
    assert (
        feedback.terminal.explanation
        == "The opening has reached its planned handoff."
    )
    assert feedback.question_total == 1
    assert session.continue_().phase is LearnPhase.LINE_COMPLETE


def test_restart_line_and_course_restore_expected_progress() -> None:
    session = _session(
        pgn="1. d4 d5 (1... Nf6) 2. Bf4 *",
    )
    session.submit_san("d4")

    restarted_line = session.restart_line()

    assert restarted_line.phase is LearnPhase.AWAITING_MOVE
    assert restarted_line.path_san == ()
    assert restarted_line.rules_seen == 0
    session.submit_san("d4")
    session.continue_()
    session.submit_san("Bf4")
    session.continue_()
    session.continue_()
    restarted_course = session.restart_course()
    assert restarted_course.line_number == 1
    assert restarted_course.path_san == ()
    assert restarted_course.rules_seen == 0


def test_existing_goal_course_completes_through_structured_session() -> None:
    examples = Path(__file__).parents[2] / "examples"
    session = LearnSession.start(
        parse_flow(
            (examples / "accelerated_london_goals.flow").read_text()
        ),
        load_pgn(
            (
                examples / "accelerated_london_goals_learn.pgn"
            ).read_text()
        ),
    )

    while session.view().phase is not LearnPhase.COURSE_COMPLETE:
        view = session.view()
        if view.phase is LearnPhase.AWAITING_MOVE:
            assert view.expected_move is not None
            session.submit_move(
                chess.Move.from_uci(view.expected_move.uci)
            )
        else:
            session.continue_()

    assert session.view().line_number == 9
    assert session.view().rules_seen > 0
