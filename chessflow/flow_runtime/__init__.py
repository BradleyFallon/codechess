from chessflow.flow_runtime.action import Action, ActionKind, CastleSide
from chessflow.flow_runtime.candidate import Candidate
from chessflow.flow_runtime.goal import (
    GoalDeadEndError,
    GoalDefinition,
    GoalRuntime,
    GoalStatus,
)
from chessflow.flow_runtime.rule import (
    PieceRuleCollection,
    RuleDefinition,
    RuleRuntime,
    RuleStatus,
    moved_since_activation,
)

__all__ = [
    "Action",
    "ActionKind",
    "Candidate",
    "CastleSide",
    "FlowRuntime",
    "GoalDeadEndError",
    "GoalDefinition",
    "GoalRuntime",
    "GoalStatus",
    "PieceRuleCollection",
    "RuleDefinition",
    "RuleRuntime",
    "RuleStatus",
    "activate_rule",
    "activate_rules",
    "collect_candidates",
    "evaluate_flow_turn",
    "expire_rules",
    "implicit_until_moved",
    "moved_since_activation",
]


def __getattr__(name: str):
    # FlowDefinition contains RuleDefinition, while FlowRuntime consumes
    # FlowDefinition. Keeping this one export lazy avoids making that clean
    # type relationship an import cycle at package initialization time.
    runtime_exports = {
        "FlowRuntime",
        "activate_rule",
        "activate_rules",
        "collect_candidates",
        "evaluate_flow_turn",
        "expire_rules",
        "implicit_until_moved",
    }
    if name in runtime_exports:
        from chessflow.flow_runtime import runtime

        return getattr(runtime, name)
    raise AttributeError(name)
