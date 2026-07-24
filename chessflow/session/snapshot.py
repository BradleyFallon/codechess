from __future__ import annotations

from dataclasses import dataclass

from chessflow.flow_runtime.goal import GoalStatus
from chessflow.flow_runtime.rule import RuleStatus


@dataclass(frozen=True, slots=True)
class RuleRuntimeSnapshot:
    action_key: str
    status: RuleStatus
    activated_at_ply: int | None
    move_counts_at_activation: tuple[tuple[str, int], ...]
    executed_at_ply: int | None
    expired_at_ply: int | None


@dataclass(frozen=True, slots=True)
class GoalRuntimeSnapshot:
    key: str
    status: GoalStatus
    activated_at_ply: int | None
    completed_at_ply: int | None
    retired_at_ply: int | None


@dataclass(frozen=True, slots=True)
class FlowRuntimeSnapshot:
    flags: frozenset[str]
    executed_action_keys: frozenset[str]
    reached_terminals: tuple[str, ...]
    goals: tuple[GoalRuntimeSnapshot, ...]
    rules: tuple[RuleRuntimeSnapshot, ...]
