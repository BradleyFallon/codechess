from __future__ import annotations

from typing import TYPE_CHECKING

import chess

from chessflow.chess_model import FlowBoard, Piece
from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime.candidate import Candidate
from chessflow.flow_runtime.evaluator import EvaluationContext, evaluate
from chessflow.flow_runtime.goal import (
    GoalDeadEndError,
    GoalRuntime,
    GoalStatus,
)
from chessflow.flow_runtime.resolver import resolve_action
from chessflow.flow_runtime.rule import (
    PieceRuleCollection,
    RuleRuntime,
    RuleStatus,
)

if TYPE_CHECKING:
    from chessflow.session.snapshot import FlowRuntimeSnapshot


class FlowRuntime:
    def __init__(self, definition: FlowDefinition, board: FlowBoard) -> None:
        self.definition = definition
        self.flags: set[str] = set()
        self.executed_action_keys: set[str] = set()
        self.reached_terminals: list[str] = []
        self._rules_by_action_key: dict[str, RuleRuntime] = {}
        self._goals_by_key: dict[str, GoalRuntime] = {}
        self._bind_rules_to_pieces(board)
        self._bind_goals(board)
        self.update_goals(board)

    @property
    def is_terminal(self) -> bool:
        return bool(self.reached_terminals)

    def _bind_goals(self, board: FlowBoard) -> None:
        for definition in self.definition.goals:
            status = (
                GoalStatus.ACTIVE
                if definition.when is None
                else GoalStatus.PENDING
            )
            runtime = GoalRuntime(
                definition=definition,
                status=status,
                activated_at_ply=board.ply
                if status is GoalStatus.ACTIVE
                else None,
            )
            self._goals_by_key[definition.key] = runtime

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
            self._rules_by_action_key[definition.action.canonical_key] = runtime
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

    def update_goals(self, board: FlowBoard) -> None:
        for goal in self._goals_in_definition_order():
            if goal.status is not GoalStatus.PENDING:
                continue
            when = goal.definition.when
            if when is not None and evaluate(
                when,
                EvaluationContext(board, self),
            ):
                goal.status = GoalStatus.ACTIVE
                goal.activated_at_ply = board.ply

        for goal in self._goals_in_definition_order():
            if goal.status is not GoalStatus.ACTIVE:
                continue
            context = EvaluationContext(board, self)
            if evaluate(goal.definition.complete, context):
                goal.status = GoalStatus.COMPLETED
                goal.completed_at_ply = board.ply
            elif not evaluate(goal.definition.while_condition, context):
                goal.status = GoalStatus.RETIRED
                goal.retired_at_ply = board.ply

    def current_goal(self, board: FlowBoard) -> GoalRuntime | None:
        self.update_goals(board)
        return next(
            (
                goal
                for goal in self._goals_in_definition_order()
                if goal.status is GoalStatus.ACTIVE
            ),
            None,
        )

    def fallback_goal(self, board: FlowBoard) -> GoalRuntime | None:
        self.update_goals(board)
        active = [
            goal
            for goal in self._goals_in_definition_order()
            if goal.status is GoalStatus.ACTIVE
        ]
        return active[1] if len(active) > 1 else None

    def goal_status(self, key: str) -> GoalStatus:
        try:
            return self._goals_by_key[key].status
        except KeyError as exc:
            raise KeyError(f"Unknown goal: {key!r}") from exc

    def collect_candidates(self, board: FlowBoard) -> list[Candidate]:
        if self.is_terminal:
            return []
        candidates: list[Candidate] = []
        current_goal = self.current_goal(board)
        current_goal_key = (
            None if current_goal is None else current_goal.definition.key
        )
        for piece in board.flow_controlled_pieces():
            assert piece.rules is not None
            for rule in piece.rules.active:
                if (
                    rule.definition.goals
                    and current_goal_key not in rule.definition.goals
                ):
                    continue
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
        if self.is_terminal:
            return []
        board.rebuild_relationships()
        self.update_goals(board)
        self.expire_rules(board)
        self.activate_rules(board)
        candidates = self.collect_candidates(board)
        current_goal = self.current_goal(board)
        if not candidates and current_goal is not None:
            raise GoalDeadEndError(current_goal.definition.key)
        return candidates

    def execute(self, candidate: Candidate, board: FlowBoard) -> None:
        if self.is_terminal:
            raise ValueError(
                "Cannot execute after terminal "
                f"{self.reached_terminals[-1]!r}"
            )
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
        self.update_goals(board)

    def push_opponent(self, move: chess.Move, board: FlowBoard) -> None:
        if self.is_terminal:
            raise ValueError(
                "Cannot push an opponent move after terminal "
                f"{self.reached_terminals[-1]!r}"
            )
        if board.chess_board.turn == self.definition.side.chess_color:
            raise ValueError("Cannot push an opponent move on the flow side's turn")
        board.push(move)
        self.update_goals(board)

    def snapshot(self) -> FlowRuntimeSnapshot:
        from chessflow.session.snapshot import (
            FlowRuntimeSnapshot,
            GoalRuntimeSnapshot,
            RuleRuntimeSnapshot,
        )

        return FlowRuntimeSnapshot(
            flags=frozenset(self.flags),
            executed_action_keys=frozenset(self.executed_action_keys),
            reached_terminals=tuple(self.reached_terminals),
            goals=tuple(
                GoalRuntimeSnapshot(
                    key=goal.definition.key,
                    status=goal.status,
                    activated_at_ply=goal.activated_at_ply,
                    completed_at_ply=goal.completed_at_ply,
                    retired_at_ply=goal.retired_at_ply,
                )
                for goal in self._goals_in_definition_order()
            ),
            rules=tuple(
                RuleRuntimeSnapshot(
                    action_key=rule.definition.action.canonical_key,
                    status=rule.status,
                    activated_at_ply=rule.activated_at_ply,
                    move_counts_at_activation=tuple(
                        sorted(rule.move_counts_at_activation.items())
                    ),
                    executed_at_ply=rule.executed_at_ply,
                    expired_at_ply=rule.expired_at_ply,
                )
                for rule in self._rules_in_definition_order()
            ),
        )

    def _rules_in_definition_order(self) -> tuple[RuleRuntime, ...]:
        return tuple(
            self._rules_by_action_key[definition.action.canonical_key]
            for definition in self.definition.rules
        )

    def _goals_in_definition_order(self) -> tuple[GoalRuntime, ...]:
        return tuple(
            self._goals_by_key[definition.key]
            for definition in self.definition.goals
        )

    @classmethod
    def restore(
        cls,
        definition: FlowDefinition,
        board: FlowBoard,
        snapshot: FlowRuntimeSnapshot,
    ) -> FlowRuntime:
        expected_keys = tuple(
            rule.action.canonical_key for rule in definition.rules
        )
        snapshot_keys = tuple(rule.action_key for rule in snapshot.rules)
        if snapshot_keys != expected_keys:
            raise ValueError(
                "Runtime snapshot rules do not match the flow definition"
            )
        expected_goal_keys = tuple(goal.key for goal in definition.goals)
        snapshot_goal_keys = tuple(goal.key for goal in snapshot.goals)
        if snapshot_goal_keys != expected_goal_keys:
            raise ValueError(
                "Runtime snapshot goals do not match the flow definition"
            )
        unknown_flags = snapshot.flags - definition.declared_flags
        if unknown_flags:
            raise ValueError(
                f"Runtime snapshot contains undeclared flags: {sorted(unknown_flags)}"
            )
        unknown_actions = snapshot.executed_action_keys - set(expected_keys)
        if unknown_actions:
            raise ValueError(
                "Runtime snapshot contains unknown executed actions: "
                f"{sorted(unknown_actions)}"
            )

        runtime = cls(definition, board)
        runtime.flags = set(snapshot.flags)
        runtime.executed_action_keys = set(snapshot.executed_action_keys)
        runtime.reached_terminals = list(snapshot.reached_terminals)
        for goal_snapshot in snapshot.goals:
            goal = runtime._goals_by_key[goal_snapshot.key]
            goal.status = goal_snapshot.status
            goal.activated_at_ply = goal_snapshot.activated_at_ply
            goal.completed_at_ply = goal_snapshot.completed_at_ply
            goal.retired_at_ply = goal_snapshot.retired_at_ply
        for rule_snapshot in snapshot.rules:
            rule = runtime._rules_by_action_key[rule_snapshot.action_key]
            owner = board.flow_piece(rule.definition.action.owner_code)
            assert owner.rules is not None
            if rule.status is not rule_snapshot.status:
                owner.rules.transition(rule, rule_snapshot.status)
            rule.activated_at_ply = rule_snapshot.activated_at_ply
            rule.move_counts_at_activation = dict(
                rule_snapshot.move_counts_at_activation
            )
            rule.executed_at_ply = rule_snapshot.executed_at_ply
            rule.expired_at_ply = rule_snapshot.expired_at_ply

        return runtime


def activate_rule(rule: RuleRuntime, piece: Piece, board: FlowBoard) -> None:
    """Record flow-piece history baselines for an active rule."""
    rule.status = RuleStatus.ACTIVE
    rule.activated_at_ply = board.ply
    rule.move_counts_at_activation = {
        code: board.piece_by_id(piece_id).move_count
        for code, piece_id in board.flow_pieces.items()
    }


def implicit_until_moved(rule: RuleRuntime, owner: Piece) -> bool:
    if owner.flow_code is None:
        raise RuntimeError("Rule owner has no flow piece code")
    try:
        baseline = rule.move_counts_at_activation[owner.flow_code]
    except KeyError as exc:
        raise RuntimeError("Rule is not active") from exc
    return owner.move_count > baseline


def expire_rules(flow: FlowRuntime, board: FlowBoard) -> None:
    flow.expire_rules(board)


def activate_rules(flow: FlowRuntime, board: FlowBoard) -> None:
    flow.activate_rules(board)


def collect_candidates(flow: FlowRuntime, board: FlowBoard) -> list[Candidate]:
    return flow.collect_candidates(board)


def evaluate_flow_turn(flow: FlowRuntime, board: FlowBoard) -> list[Candidate]:
    return flow.evaluate_turn(board)
