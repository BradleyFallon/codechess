from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from chessflow.flow_language.expressions import Expression


@dataclass(frozen=True, slots=True)
class GoalDefinition:
    key: str
    when: Expression | None
    while_condition: Expression
    complete: Expression
    title: str
    plan: str
    abandoned: str
    source_order: int = 0


class GoalStatus(Enum):
    PENDING = auto()
    ACTIVE = auto()
    COMPLETED = auto()
    RETIRED = auto()


@dataclass(slots=True)
class GoalRuntime:
    definition: GoalDefinition
    status: GoalStatus
    activated_at_ply: int | None = None
    completed_at_ply: int | None = None
    retired_at_ply: int | None = None


class GoalDeadEndError(RuntimeError):
    def __init__(self, goal_key: str, path: str | None = None) -> None:
        self.goal_key = goal_key
        self.path = path
        location = "" if path is None else f" at {path}"
        super().__init__(
            f"Goal dead end{location}: current goal {goal_key} "
            "has no eligible rule"
        )

    def at_path(self, path: str) -> GoalDeadEndError:
        return GoalDeadEndError(self.goal_key, path)
