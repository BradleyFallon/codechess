from pathlib import Path

import chess

from chessflow import FlowBoard, FlowRuntime, parse_flow
from chessflow.flow_runtime import RuleStatus
from chessflow.simulation import FlowRunner, TurnOutcome


EXAMPLE = Path(__file__).parents[2] / "examples" / "vertical-slice.flow"


def test_vertical_slice_runs_through_persistent_piece_objects() -> None:
    board = FlowBoard()
    flow = FlowRuntime(parse_flow(EXAMPLE.read_text()), board)
    runner = FlowRunner(flow, board)
    expected = (
        ("d2d4", "d5"),
        ("c1f4", "Nf6"),
        ("e2e3", "e6"),
    )

    for white_uci, black_san in expected:
        report = runner.play_flow_turn()
        assert report.outcome is TurnOutcome.SELECTED
        assert report.selected is not None
        assert report.selected.move.uci() == white_uci
        board.push_san(black_san)

    report = runner.play_flow_turn()

    assert report.outcome is TurnOutcome.TERMINAL
    assert report.selected is not None
    assert report.selected.move == chess.Move.from_uci("g1f3")
    assert flow.flags == {"center-claimed"}
    assert flow.reached_terminals == ["vertical-slice-complete"]
    assert board.flow_piece("d").has_developed
    assert board.flow_piece("bq").has_developed
    assert board.flow_piece("e").has_developed
    assert board.flow_piece("nk").has_developed
    for piece_code in ("d", "bq", "e", "nk"):
        rules = board.flow_piece(piece_code).rules
        assert rules is not None
        rules.assert_consistent()
        assert len(rules.executed) == 1


def test_all_candidates_are_reported_before_source_order_selection() -> None:
    definition = parse_flow(
        """
        flow ambiguous
        version 0.1
        side white
        d:
            develop.d4:
                why: first in source
        e:
            develop.e4:
                why: also legal
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)

    report = FlowRunner(flow, board).play_flow_turn()

    assert report.outcome is TurnOutcome.AMBIGUOUS
    assert report.had_ambiguity
    assert [candidate.move.uci() for candidate in report.candidates] == ["d2d4", "e2e4"]
    assert report.selected is report.candidates[0]
    assert board.flow_piece("e").rules is not None
    assert len(board.flow_piece("e").rules.active) == 1


def test_implicit_until_expires_after_owner_moves_since_activation() -> None:
    definition = parse_flow(
        """
        flow expiry
        version 0.1
        side white
        c:
            develop.c3:
                why: expires if c-pawn goes elsewhere
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]

    board.push_uci("c2c4")
    flow.expire_rules(board)

    assert rule.status is RuleStatus.EXPIRED
    assert rule.expired_at_ply == 1
    assert board.flow_piece("c").rules is not None
    assert rule in board.flow_piece("c").rules.expired


def test_explicit_contextual_until_moved_has_rule_relative_semantics() -> None:
    definition = parse_flow(
        """
        flow explicit-expiry
        version 0.1
        side white
        c:
            develop.c3:
                until: moved()
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]

    flow.expire_rules(board)
    assert rule.status is RuleStatus.ACTIVE
    board.push_uci("c2c4")
    flow.expire_rules(board)
    assert rule.status is RuleStatus.EXPIRED
