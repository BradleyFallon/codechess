from __future__ import annotations

from chessflow.chess_model import FlowBoard, Piece
from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime.candidate import Candidate
from chessflow.flow_runtime.evaluator import EvaluationContext, evaluate
from chessflow.flow_runtime.resolver import resolve_action
from chessflow.flow_runtime.rule import PieceRuleCollection, RuleRuntime, RuleStatus


class FlowRuntime:
    def __init__(self, definition: FlowDefinition, board: FlowBoard) -> None:
        self.definition = definition
        self.flags: set[str] = set()
        self.executed_action_keys: set[str] = set()
        self.reached_terminals: list[str] = []
        self._bind_rules_to_pieces(board)

    def _bind_rules_to_pieces(self, board: FlowBoard) -> None:
        for piece in board.flow_controlled_pieces():
            piece.rules = PieceRuleCollection()
        for definition in self.definition.rules:
            try:
                piece = board.flow_piece(definition.action.owner_code)
            except KeyError as exc:
                raise ValueError(
                    f"Rule {definition.action.canonical_key} has unknown owner"
                ) from exc
            assert piece.rules is not None
            status = (
                RuleStatus.ACTIVE if definition.when is None else RuleStatus.PENDING
            )
            runtime = RuleRuntime(definition, status)
            piece.rules.add(runtime)
            if status is RuleStatus.ACTIVE:
                self._record_activation(runtime, piece, board)

    @staticmethod
    def _record_activation(rule: RuleRuntime, owner: Piece, board: FlowBoard) -> None:
        activate_rule(rule, owner, board)

    def expire_rules(self, board: FlowBoard) -> None:
        for piece in board.flow_controlled_pieces():
            assert piece.rules is not None
            for rule in list(piece.rules.pending):
                if rule.definition.until is not None and evaluate(
                    rule.definition.until, EvaluationContext(board, self, rule)
                ):
                    rule.expired_at_ply = board.ply
                    piece.rules.transition(rule, RuleStatus.EXPIRED)
            for rule in list(piece.rules.active):
                if rule.definition.until is None:
                    expired = implicit_until_moved(rule, piece)
                else:
                    expired = evaluate(
                        rule.definition.until, EvaluationContext(board, self, rule)
                    )
                if expired:
                    rule.expired_at_ply = board.ply
                    piece.rules.transition(rule, RuleStatus.EXPIRED)

    def activate_rules(self, board: FlowBoard) -> None:
        for piece in board.flow_controlled_pieces():
            assert piece.rules is not None
            for rule in list(piece.rules.pending):
                when = rule.definition.when
                if when is not None and not evaluate(
                    when, EvaluationContext(board, self, rule)
                ):
                    continue
                piece.rules.transition(rule, RuleStatus.ACTIVE)
                self._record_activation(rule, piece, board)

    def collect_candidates(self, board: FlowBoard) -> list[Candidate]:
        candidates: list[Candidate] = []
        for piece in board.flow_controlled_pieces():
            assert piece.rules is not None
            for rule in piece.rules.active:
                condition = rule.definition.if_condition
                if condition is not None and not evaluate(
                    condition, EvaluationContext(board, self, rule)
                ):
                    continue
                move = resolve_action(rule.definition.action, piece, board)
                if move is not None:
                    candidates.append(Candidate(rule, move))
        candidates.sort(key=lambda candidate: candidate.rule.definition.source_order)
        return candidates

    def evaluate_turn(self, board: FlowBoard) -> list[Candidate]:
        board.rebuild_relationships()
        self.expire_rules(board)
        self.activate_rules(board)
        return self.collect_candidates(board)

    def execute(self, candidate: Candidate, board: FlowBoard) -> None:
        rule = candidate.rule
        if rule.status is not RuleStatus.ACTIVE:
            raise ValueError("Only an active rule can execute")
        owner = board.flow_piece(rule.definition.action.owner_code)
        assert owner.rules is not None
        current = resolve_action(rule.definition.action, owner, board)
        if current != candidate.move:
            raise ValueError("Candidate is stale or no longer legal")
        board.push(candidate.move)
        rule.executed_at_ply = board.ply
        owner.rules.transition(rule, RuleStatus.EXECUTED)
        self.executed_action_keys.add(rule.definition.action.canonical_key)
        self.flags.update(rule.definition.set_flags)
        if rule.definition.terminal is not None:
            self.reached_terminals.append(rule.definition.terminal)


def activate_rule(rule: RuleRuntime, piece: Piece, board: FlowBoard) -> None:
    """Record the owner-relative history baseline for an active rule."""
    rule.status = RuleStatus.ACTIVE
    rule.activated_at_ply = board.ply
    rule.owner_move_count_at_activation = piece.move_count


def implicit_until_moved(rule: RuleRuntime, owner: Piece) -> bool:
    baseline = rule.owner_move_count_at_activation
    if baseline is None:
        raise RuntimeError("Rule is not active")
    return owner.move_count > baseline


def expire_rules(flow: FlowRuntime, board: FlowBoard) -> None:
    flow.expire_rules(board)


def activate_rules(flow: FlowRuntime, board: FlowBoard) -> None:
    flow.activate_rules(board)


def collect_candidates(flow: FlowRuntime, board: FlowBoard) -> list[Candidate]:
    return flow.collect_candidates(board)


def evaluate_flow_turn(flow: FlowRuntime, board: FlowBoard) -> list[Candidate]:
    return flow.evaluate_turn(board)
