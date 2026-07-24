from dataclasses import replace

import chess
import pytest

from chessflow import FlowBoard, FlowRuntime, FlowSession, parse_flow
from chessflow.flow_runtime import Candidate, RuleRuntime, RuleStatus


FLOW_SOURCE = """
flow branch-isolation
version 0.1
side white

flags:
    center-claimed
    bishop-developed

d:
    develop.d4:
        set: center-claimed

bq:
    develop.f4:
        when: played(d.develop.d4)
        set: bishop-developed

c:
    develop.c3:

e:
    develop.e3:
        when: false

g:
    develop.g3:
"""


def _rule(session: FlowSession, action_key: str) -> RuleRuntime:
    for piece in session.board.flow_controlled_pieces():
        assert piece.rules is not None
        for rule in piece.rules.all:
            if rule.definition.action.canonical_key == action_key:
                return rule
    raise AssertionError(f"Missing runtime rule: {action_key}")


def _candidate(session: FlowSession, action_key: str) -> Candidate:
    return next(
        candidate
        for candidate in session.runtime.evaluate_turn(session.board)
        if candidate.rule.definition.action.canonical_key == action_key
    )


def test_fresh_session_builds_a_matching_board_and_runtime() -> None:
    definition = parse_flow(FLOW_SOURCE)

    session = FlowSession.fresh(definition)

    assert session.definition is definition
    assert session.board.fen == chess.Board().fen()
    assert session.runtime.definition is definition
    assert _rule(session, "d.develop.d4").status is RuleStatus.ACTIVE
    assert _rule(session, "bq.develop.f4").status is RuleStatus.PENDING


def test_clone_restores_complete_runtime_state_with_distinct_objects() -> None:
    session = FlowSession.fresh(parse_flow(FLOW_SOURCE))
    session.runtime.execute(_candidate(session, "d.develop.d4"), session.board)
    session.board.push_san("Nf6")
    session.runtime.execute(_candidate(session, "bq.develop.f4"), session.board)
    session.board.push_san("e6")
    session.board.push_san("c4")
    session.runtime.expire_rules(session.board)

    clone = session.clone()

    assert clone is not session
    assert clone.definition is session.definition
    assert clone.board is not session.board
    assert clone.board.chess_board is not session.board.chess_board
    assert clone.board.fen == session.board.fen
    assert clone.board.chess_board.move_stack == session.board.chess_board.move_stack
    assert clone.runtime is not session.runtime
    assert clone.runtime.snapshot() == session.runtime.snapshot()
    assert clone.runtime.flags == {"center-claimed", "bishop-developed"}
    assert clone.runtime.executed_action_keys == {
        "d.develop.d4",
        "bq.develop.f4",
    }
    assert clone.runtime.reached_terminals == []
    assert _rule(clone, "d.develop.d4").status is RuleStatus.EXECUTED
    assert _rule(clone, "bq.develop.f4").status is RuleStatus.EXECUTED
    assert _rule(clone, "c.develop.c3").status is RuleStatus.EXPIRED
    assert _rule(clone, "e.develop.e3").status is RuleStatus.PENDING
    assert _rule(clone, "g.develop.g3").status is RuleStatus.ACTIVE

    for piece_id, piece in session.board.pieces_by_id.items():
        cloned_piece = clone.board.piece_by_id(piece_id)
        assert cloned_piece is not piece
        if piece.rules is not None:
            assert cloned_piece.rules is not piece.rules

    for definition in session.definition.rules:
        action_key = definition.action.canonical_key
        original_rule = _rule(session, action_key)
        cloned_rule = _rule(clone, action_key)
        assert cloned_rule is not original_rule
        assert (
            cloned_rule.move_counts_at_activation
            is not original_rule.move_counts_at_activation
        )
        assert (
            cloned_rule.move_counts_at_activation
            == original_rule.move_counts_at_activation
        )


def test_black_branches_do_not_leak_moves_flags_baselines_or_rule_history() -> None:
    base = FlowSession.fresh(parse_flow(FLOW_SOURCE))
    base.runtime.execute(_candidate(base, "d.develop.d4"), base.board)
    d4_fen = base.board.fen
    left = base.clone()
    right = base.clone()

    left.board.push_san("d5")
    right.board.push_san("Nf6")

    assert base.board.fen == d4_fen
    assert left.board.fen != right.board.fen
    assert left.board.flow_piece("d") is not right.board.flow_piece("d")
    assert left.board.piece_ref("black.d").square == chess.D5
    assert right.board.piece_ref("black.d").square == chess.D7

    left_bishop = _rule(left, "bq.develop.f4")
    right_bishop = _rule(right, "bq.develop.f4")
    base_bishop = _rule(base, "bq.develop.f4")
    left_candidate = _candidate(left, "bq.develop.f4")
    right_candidate = _candidate(right, "bq.develop.f4")

    assert left_bishop.status is RuleStatus.ACTIVE
    assert right_bishop.status is RuleStatus.ACTIVE
    assert base_bishop.status is RuleStatus.PENDING
    assert left_bishop.move_counts_at_activation == right_bishop.move_counts_at_activation
    assert (
        left_bishop.move_counts_at_activation
        is not right_bishop.move_counts_at_activation
    )
    assert base_bishop.move_counts_at_activation == {}

    left_bishop.move_counts_at_activation["d"] = 99
    assert right_bishop.move_counts_at_activation["d"] == 1
    assert base_bishop.move_counts_at_activation == {}

    left.runtime.execute(left_candidate, left.board)

    assert left.runtime.flags == {"center-claimed", "bishop-developed"}
    assert right.runtime.flags == {"center-claimed"}
    assert base.runtime.flags == {"center-claimed"}
    assert left_bishop.status is RuleStatus.EXECUTED
    assert right_bishop.status is RuleStatus.ACTIVE
    assert base_bishop.status is RuleStatus.PENDING
    assert "bq.develop.f4" in left.runtime.executed_action_keys
    assert "bq.develop.f4" not in right.runtime.executed_action_keys
    assert "bq.develop.f4" not in base.runtime.executed_action_keys
    assert left.board.flow_piece("bq").square == chess.F4
    assert right.board.flow_piece("bq").square == chess.C1
    assert base.board.flow_piece("bq").square == chess.C1

    assert right_candidate.rule is right_bishop
    assert right_candidate.move == chess.Move.from_uci("c1f4")


def test_restore_rejects_a_snapshot_for_a_different_definition() -> None:
    session = FlowSession.fresh(parse_flow(FLOW_SOURCE))
    target_board = FlowBoard()
    other_definition = parse_flow(
        """
        flow other
        version 0.1
        side white
        e:
            develop.e4:
        """
    )

    with pytest.raises(ValueError, match="do not match the flow definition"):
        FlowRuntime.restore(
            other_definition,
            target_board,
            session.runtime.snapshot(),
        )
    assert all(piece.rules is None for piece in target_board.flow_controlled_pieces())


def test_restore_rejects_undeclared_snapshot_flags() -> None:
    session = FlowSession.fresh(parse_flow(FLOW_SOURCE))
    snapshot = replace(
        session.runtime.snapshot(),
        flags=frozenset({"not-declared"}),
    )

    with pytest.raises(ValueError, match="undeclared flags"):
        FlowRuntime.restore(session.definition, FlowBoard(), snapshot)
