import chess
import pytest

from chessflow import FlowSession, parse_flow
from chessflow.flow_runtime import GoalDeadEndError, GoalStatus


def _goal(
    key: str,
    *,
    when: str | None = None,
    while_condition: str = "true",
    complete: str = "false",
) -> str:
    when_field = "" if when is None else f"        when: {when}\n"
    return (
        f"    {key}:\n"
        f"{when_field}"
        f"        while: {while_condition}\n"
        f"        complete: {complete}\n"
        f"        title: {key} title\n"
        f"        plan: Follow the {key} plan.\n"
        f"        abandoned: The {key} plan is no longer viable.\n"
    )


def _definition(goals: str, rules: str):
    return parse_flow(
        "flow goal-runtime\n"
        "version 0.2\n"
        "side white\n"
        "goals:\n"
        f"{goals}"
        f"{rules}"
    )


def _candidate(session: FlowSession, action_key: str):
    return next(
        candidate
        for candidate in session.runtime.evaluate_turn(session.board)
        if candidate.rule.definition.action.canonical_key == action_key
    )


def test_goal_without_when_is_initially_active() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("center"),
            "d:\n"
            "    develop.d4:\n"
            "        goals: center\n",
        )
    )

    current = session.runtime.current_goal(session.board)

    assert current is not None
    assert current.definition.key == "center"
    assert session.runtime.goal_status("center") is GoalStatus.ACTIVE
    assert current.activated_at_ply == 0


def test_goal_activation_latches_after_when_becomes_false() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("queenside", when="square.a6.has(enemy.pawn)"),
            "d:\n"
            "    develop.d4:\n"
            "c:\n"
            "    develop.c3:\n"
            "        when: played(d.develop.d4)\n",
        )
    )
    assert session.runtime.goal_status("queenside") is GoalStatus.PENDING

    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)
    session.runtime.push_opponent(
        session.board.chess_board.parse_san("a6"),
        session.board,
    )
    assert session.runtime.goal_status("queenside") is GoalStatus.ACTIVE

    session.runtime.execute(_candidate(session, "c.develop.c3"), session.board)
    session.runtime.push_opponent(
        session.board.chess_board.parse_san("a5"),
        session.board,
    )

    assert not session.board.piece_ref("black.a").at(chess.A6)
    assert session.runtime.goal_status("queenside") is GoalStatus.ACTIVE


def test_goal_completes_after_its_rule_executes() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("center", complete="played(d.develop.d4)"),
            "d:\n"
            "    develop.d4:\n"
            "        goals: center\n",
        )
    )

    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)

    assert session.runtime.goal_status("center") is GoalStatus.COMPLETED


def test_goal_retires_when_while_becomes_false() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal(
                "queenside",
                while_condition="square.a7.has(enemy.pawn)",
            ),
            "d:\n"
            "    develop.d4:\n"
            "        goals: queenside\n",
        )
    )
    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)

    session.runtime.push_opponent(
        session.board.chess_board.parse_san("a6"),
        session.board,
    )

    assert session.runtime.goal_status("queenside") is GoalStatus.RETIRED


def test_completion_is_checked_before_retirement() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal(
                "center",
                while_condition="square.d2.has(ours.pawn)",
                complete="played(d.develop.d4)",
            ),
            "d:\n"
            "    develop.d4:\n"
            "        goals: center\n",
        )
    )

    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)

    assert session.runtime.goal_status("center") is GoalStatus.COMPLETED


def test_source_order_selects_current_and_next_active_fallback() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("first") + _goal("second"),
            "d:\n"
            "    develop.d4:\n",
        )
    )

    current = session.runtime.current_goal(session.board)
    fallback = session.runtime.fallback_goal(session.board)

    assert current is not None
    assert fallback is not None
    assert current.definition.key == "first"
    assert fallback.definition.key == "second"


def test_universal_and_current_goal_rules_preserve_source_order() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("current") + _goal("fallback"),
            "d:\n"
            "    develop.d4:\n"
            "c:\n"
            "    develop.c4:\n"
            "        goals: current\n"
            "e:\n"
            "    develop.e4:\n"
            "        goals: fallback\n",
        )
    )

    candidates = session.runtime.evaluate_turn(session.board)

    assert [
        candidate.rule.definition.action.canonical_key
        for candidate in candidates
    ] == ["d.develop.d4", "c.develop.c4"]


def test_fallback_rule_does_not_rescue_current_goal_dead_end() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("current") + _goal("fallback"),
            "e:\n"
            "    develop.e4:\n"
            "        goals: fallback\n",
        )
    )

    with pytest.raises(
        GoalDeadEndError,
        match="current goal current has no eligible rule",
    ):
        session.runtime.evaluate_turn(session.board)


def test_cloned_session_preserves_independent_goal_states() -> None:
    session = FlowSession.fresh(
        _definition(
            _goal("center", complete="played(d.develop.d4)")
            + _goal(
                "queenside",
                while_condition="square.a7.has(enemy.pawn)",
            ),
            "d:\n"
            "    develop.d4:\n"
            "        goals: center\n",
        )
    )
    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)
    session.runtime.push_opponent(
        session.board.chess_board.parse_san("a6"),
        session.board,
    )

    clone = session.clone()

    assert clone.runtime.snapshot() == session.runtime.snapshot()
    assert clone.runtime.goal_status("center") is GoalStatus.COMPLETED
    assert clone.runtime.goal_status("queenside") is GoalStatus.RETIRED
