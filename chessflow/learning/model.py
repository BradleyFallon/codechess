from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LearnPhase(Enum):
    AWAITING_MOVE = "awaiting_move"
    SHOWING_FEEDBACK = "showing_feedback"
    LINE_COMPLETE = "line_complete"
    COURSE_COMPLETE = "course_complete"


class MoveFeedbackKind(Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    INVALID_SAN = "invalid_san"


class GoalEventKind(Enum):
    NEW_GOAL = "new_goal"
    GOAL_COMPLETE = "goal_complete"
    GOAL_RETIRED = "goal_retired"
    FALLBACK_UPDATED = "fallback_updated"


@dataclass(frozen=True, slots=True)
class MoveView:
    uci: str
    san: str
    from_square: str
    to_square: str
    promotion: str | None


@dataclass(frozen=True, slots=True)
class GoalView:
    key: str
    title: str
    plan: str


@dataclass(frozen=True, slots=True)
class GoalEventView:
    kind: GoalEventKind
    goal: GoalView | None
    previous_goal: GoalView | None
    fallback: GoalView | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class MoveFeedbackView:
    kind: MoveFeedbackKind
    entered: str | None
    expected: MoveView
    rule_key: str
    explanation: tuple[str, ...]
    is_new_rule: bool
    was_correction: bool


@dataclass(frozen=True, slots=True)
class TerminalExitView:
    key: str
    explanation: str


@dataclass(frozen=True, slots=True)
class RuleLessonView:
    rule_key: str
    explanation: str | None


@dataclass(frozen=True, slots=True)
class LearnView:
    phase: LearnPhase
    fen: str
    path_san: tuple[str, ...]
    line_number: int
    line_total: int
    question_number: int
    question_total: int
    current_goal: GoalView | None
    fallback_goal: GoalView | None
    goal_events: tuple[GoalEventView, ...]
    coach: tuple[str, ...]
    legal_moves: tuple[MoveView, ...]
    expected_move: MoveView | None
    feedback: MoveFeedbackView | None
    terminal: TerminalExitView | None
    new_rules: tuple[RuleLessonView, ...]
    review_count: int
    rules_seen: int
