from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import chess

from chessflow.chess_model import Color, FlowBoard, Piece
from chessflow.flow_language.expressions import (
    BooleanOperation,
    Call,
    Expression,
    Name,
    Not,
)
from chessflow.flow_runtime.rule import RuleRuntime

if TYPE_CHECKING:
    from chessflow.flow_runtime.runtime import FlowRuntime


class EvaluationError(ValueError):
    pass


@dataclass(slots=True)
class EvaluationContext:
    board: FlowBoard
    flow: "FlowRuntime"
    rule: RuleRuntime | None = None
    _condition_stack: list[str] = field(default_factory=list)

    @property
    def owner(self) -> Piece:
        if self.rule is None:
            raise EvaluationError("No contextual rule owner")
        return self.board.flow_piece(self.rule.definition.action.owner_code)


def evaluate(expression: Expression, context: EvaluationContext) -> bool:
    if isinstance(expression, Name):
        return _evaluate_name(expression.value, context)
    if isinstance(expression, Not):
        return not evaluate(expression.operand, context)
    if isinstance(expression, BooleanOperation):
        if expression.operator == "&&":
            return evaluate(expression.left, context) and evaluate(
                expression.right, context
            )
        if expression.operator == "||":
            return evaluate(expression.left, context) or evaluate(
                expression.right, context
            )
        raise EvaluationError(f"Unknown Boolean operator: {expression.operator}")
    if isinstance(expression, Call):
        return _evaluate_call(expression, context)
    raise TypeError(f"Unknown expression node: {type(expression).__name__}")


def _evaluate_name(name: str, context: EvaluationContext) -> bool:
    lowered = name.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "open":
        return context.board.ply == 0
    if name in context.flow.flags:
        return True
    if name in context.flow.definition.declared_flags:
        return False
    condition = context.flow.definition.conditions.get(name)
    if condition is None:
        raise EvaluationError(f"Unknown condition or flag: {name!r}")
    if name in context._condition_stack:
        chain = " -> ".join([*context._condition_stack, name])
        raise EvaluationError(f"Circular named condition: {chain}")
    context._condition_stack.append(name)
    try:
        return evaluate(condition, context)
    finally:
        context._condition_stack.pop()


def _evaluate_call(call: Call, context: EvaluationContext) -> bool:
    name = call.name.lower()
    args = tuple(_argument_name(argument) for argument in call.arguments)
    if name == "at":
        if len(args) == 1:
            return context.owner.at(_square(args[0]))
        _arity(call, args, 2)
        return context.board.piece_ref(args[0]).at(_square(args[1]))
    if name in {"moved", "hasmoved"}:
        if not args:
            if context.rule is None:
                raise EvaluationError("moved() needs a contextual rule")
            baseline = context.rule.owner_move_count_at_activation
            return baseline is not None and context.owner.move_count > baseline
        _arity(call, args, 1)
        return context.board.piece_ref(args[0]).has_moved
    if name == "unmoved":
        _arity(call, args, 1)
        return not context.board.piece_ref(args[0]).has_moved
    if name == "captured":
        _arity(call, args, 1)
        return context.board.piece_ref(args[0]).is_captured
    if name == "attacked":
        if not args:
            return context.owner.is_attacked
        if len(args) == 1:
            return bool(
                context.board.chess_board.attackers(
                    context.owner.color.opposite.chess_color, _square(args[0])
                )
            )
        _arity(call, args, 2)
        return bool(
            context.board.chess_board.attackers(
                Color.parse(args[1]).chess_color, _square(args[0])
            )
        )
    if name == "defended":
        if not args:
            return context.owner.is_defended
        if len(args) == 1:
            return bool(
                context.board.chess_board.attackers(
                    context.owner.color.chess_color, _square(args[0])
                )
            )
        _arity(call, args, 2)
        return bool(
            context.board.chess_board.attackers(
                Color.parse(args[1]).chess_color, _square(args[0])
            )
        )
    if name == "played":
        _arity(call, args, 1)
        return args[0] in context.flow.executed_action_keys
    if name == "canmoveto":
        _arity(call, args, 1)
        return context.owner.can_move_to(_square(args[0]))
    if name == "cancaptureon":
        _arity(call, args, 1)
        return context.owner.can_capture_on(_square(args[0]))
    if name == "flag":
        _arity(call, args, 1)
        return args[0] in context.flow.flags
    raise EvaluationError(f"Unknown predicate: {call.name}()")


def _argument_name(expression: Expression) -> str:
    if not isinstance(expression, Name):
        raise EvaluationError(
            "Predicate arguments must be names, piece references, or squares"
        )
    return expression.value


def _square(value: str) -> chess.Square:
    try:
        return chess.parse_square(value.lower())
    except ValueError as exc:
        raise EvaluationError(f"Invalid square: {value!r}") from exc


def _arity(call: Call, args: tuple[str, ...], expected: int) -> None:
    if len(args) != expected:
        raise EvaluationError(
            f"{call.name}() expects {expected} argument(s), received {len(args)}"
        )
