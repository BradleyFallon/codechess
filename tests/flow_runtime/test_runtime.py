from pathlib import Path

import chess
import pytest

from chessflow import FlowBoard, FlowRuntime, parse_flow
from chessflow.flow_language.expressions import Name, parse_expression
from chessflow.flow_runtime import RuleStatus
from chessflow.flow_runtime.evaluator import EvaluationContext, evaluate
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
    e_rules = board.flow_piece("e").rules
    assert e_rules is not None
    assert len(e_rules.active) == 1


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
    c_rules = board.flow_piece("c").rules
    assert c_rules is not None
    assert rule in c_rules.expired


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


def test_developed_tracks_executed_develop_actions_not_current_square() -> None:
    definition = parse_flow(
        """
        flow developed-history
        version 0.1
        side white
        nk:
            develop.f3:
        c:
            develop.c3:
                when: nk.developed()
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    runner = FlowRunner(flow, board)

    report = runner.play_flow_turn()
    assert report.selected is not None
    assert report.selected.move == chess.Move.from_uci("g1f3")
    board.push_san("a6")
    board.push_san("Ng1")
    board.push_san("a5")

    knight = board.flow_piece("nk")
    knight_rule = knight.rules.executed[0]  # type: ignore[union-attr]
    c_rule = board.flow_piece("c").rules.pending[0]  # type: ignore[union-attr]
    context = EvaluationContext(board, flow, c_rule)

    assert knight.square == chess.G1
    assert knight.has_developed
    assert evaluate(parse_expression("nk.developed()"), context)
    assert evaluate(
        parse_expression("developed()"),
        EvaluationContext(board, flow, knight_rule),
    )
    flow.activate_rules(board)
    assert c_rule.status is RuleStatus.ACTIVE


def test_explicit_moved_is_relative_to_another_rules_activation() -> None:
    definition = parse_flow(
        """
        flow cross-piece-movement
        version 0.1
        side white
        c:
            develop.c3:
                when: at(d, d4)
                until: d.moved()
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.pending[0]  # type: ignore[union-attr]

    board.push_san("d4")
    flow.activate_rules(board)

    assert rule.status is RuleStatus.ACTIVE
    assert rule.move_counts_at_activation["d"] == 1
    flow.expire_rules(board)
    assert rule.status is RuleStatus.ACTIVE

    board.push_san("a6")
    board.push_san("d5")
    flow.expire_rules(board)

    assert rule.status is RuleStatus.EXPIRED


def test_contextual_moved_is_false_at_activation_then_true_after_owner_moves() -> None:
    definition = parse_flow(
        """
        flow contextual-movement
        version 0.1
        side white
        c:
            develop.c3:
                if: moved()
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]
    context = EvaluationContext(board, flow, rule)

    assert not evaluate(parse_expression("moved()"), context)
    board.push_san("c4")
    assert evaluate(parse_expression("moved()"), context)


def test_explicit_and_implicit_until_moved_expire_together() -> None:
    implicit_definition = parse_flow(
        """
        flow implicit
        version 0.1
        side white
        c:
            develop.c3:
        """
    )
    explicit_definition = parse_flow(
        """
        flow explicit
        version 0.1
        side white
        c:
            develop.c3:
                until: moved()
        """
    )
    implicit_board = FlowBoard()
    explicit_board = FlowBoard()
    implicit_flow = FlowRuntime(implicit_definition, implicit_board)
    explicit_flow = FlowRuntime(explicit_definition, explicit_board)
    implicit_rule = implicit_board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]
    explicit_rule = explicit_board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]

    implicit_board.push_san("c4")
    explicit_board.push_san("c4")
    implicit_flow.expire_rules(implicit_board)
    explicit_flow.expire_rules(explicit_board)

    assert implicit_rule.status is RuleStatus.EXPIRED
    assert explicit_rule.status is RuleStatus.EXPIRED


def test_square_queries_support_relative_type_and_identity_selectors() -> None:
    definition = parse_flow(
        """
        flow square-queries
        version 0.1
        side white
        conditions:
            enemy-bishop = square.f5.has(enemy.bishop)
            wrong-type = square.f5.has(enemy.knight)
            empty-square = square.h4.empty()
            ours = square.d4.has(ours)
            ours-pawn = square.d4.has(ours.pawn)
            enemy = square.f5.has(enemy)
            black-identity = square.f5.has(black.bq)
        c:
            develop.c3:
                if: enemy-bishop
        """
    )
    board = FlowBoard()
    for san in ("d4", "d5", "Nf3", "Bf5"):
        board.push_san(san)
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]
    context = EvaluationContext(board, flow, rule)

    assert evaluate(Name("enemy-bishop"), context)
    assert not evaluate(Name("wrong-type"), context)
    assert evaluate(Name("empty-square"), context)
    assert evaluate(Name("ours"), context)
    assert evaluate(Name("ours-pawn"), context)
    assert evaluate(Name("enemy"), context)
    assert evaluate(Name("black-identity"), context)
    assert board.piece_at(chess.F5) is board.piece_ref("black.bq")


def test_square_query_accepts_flow_piece_identity() -> None:
    definition = parse_flow(
        """
        flow identity-query
        version 0.1
        side white
        c:
            develop.c3:
                if: square.f4.has(bq)
        """
    )
    board = FlowBoard()
    for san in ("d4", "d5", "Bf4", "Nf6"):
        board.push_san(san)
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("c").rules.active[0]  # type: ignore[union-attr]

    assert evaluate(
        parse_expression("square.f4.has(bq)"),
        EvaluationContext(board, flow, rule),
    )


def test_piece_geometry_queries_distinguish_control_from_legal_moves() -> None:
    definition = parse_flow(
        """
        flow geometry-queries
        version 0.1
        side white
        nq:
            develop.c4:
                if:
                    controls(f3) &&
                    nq.controls(f3) &&
                    attacked() &&
                    nq.attacked() &&
                    b.defended() &&
                    !canMoveTo(f3) &&
                    !nq.canMoveTo(f3)
        """
    )
    board = FlowBoard()
    for san in ("b3", "e5", "d3", "Bb4+", "Nd2", "a6"):
        board.push_san(san)
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("nq").rules.active[0]  # type: ignore[union-attr]
    context = EvaluationContext(board, flow, rule)

    assert evaluate(parse_expression("controls(f3)"), context)
    assert evaluate(parse_expression("nq.controls(f3)"), context)
    assert evaluate(parse_expression("attacked()"), context)
    assert evaluate(parse_expression("nq.attacked()"), context)
    assert evaluate(parse_expression("b.defended()"), context)
    assert not evaluate(parse_expression("canMoveTo(f3)"), context)
    assert not evaluate(parse_expression("nq.canMoveTo(f3)"), context)


def test_piece_qualified_legal_capture_query() -> None:
    definition = parse_flow(
        """
        flow legal-capture-query
        version 0.1
        side white
        e:
            capture.d5:
                if: canCaptureOn(d5) && e.canCaptureOn(d5)
        """
    )
    board = FlowBoard()
    board.push_san("e4")
    board.push_san("d5")
    flow = FlowRuntime(definition, board)
    rule = board.flow_piece("e").rules.active[0]  # type: ignore[union-attr]
    context = EvaluationContext(board, flow, rule)

    assert evaluate(parse_expression("canCaptureOn(d5)"), context)
    assert evaluate(parse_expression("e.canCaptureOn(d5)"), context)


def test_retreat_resolves_like_develop_without_marking_piece_developed() -> None:
    definition = parse_flow(
        """
        flow retreat
        version 0.1
        side white
        nq:
            retreat.c3:
        """
    )
    board = FlowBoard()
    for san in ("Nc3", "a6", "Nb5", "e6"):
        board.push_san(san)
    flow = FlowRuntime(definition, board)

    candidates = flow.evaluate_turn(board)

    assert len(candidates) == 1
    assert candidates[0].move == chess.Move.from_uci("b5c3")
    flow.execute(candidates[0], board)
    assert board.flow_piece("nq").square == chess.C3
    assert not board.flow_piece("nq").has_developed
    assert flow.executed_action_keys == {"nq.retreat.c3"}


def test_terminal_stops_candidate_evaluation_and_further_moves() -> None:
    definition = parse_flow(
        """
        flow terminal
        version 0.1
        side white
        d:
            develop.d4:
                terminal: center-claimed
        e:
            develop.e4:
        """
    )
    board = FlowBoard()
    flow = FlowRuntime(definition, board)
    candidates = flow.evaluate_turn(board)

    flow.execute(candidates[0], board)

    assert flow.is_terminal
    assert flow.reached_terminals == ["center-claimed"]
    assert flow.evaluate_turn(board) == []
    assert flow.collect_candidates(board) == []
    with pytest.raises(ValueError, match="after terminal"):
        flow.execute(candidates[1], board)
    with pytest.raises(ValueError, match="after terminal"):
        flow.push_opponent(board.chess_board.parse_san("d5"), board)
