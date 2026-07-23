from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from chessflow.flow_runtime.action import Action

if TYPE_CHECKING:
    from chessflow.flow_language.expressions import Expression


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    action: Action
    when: Expression | None = None
    until: Expression | None = None
    if_condition: Expression | None = None
    set_flags: tuple[str, ...] = ()
    why: str | None = None
    terminal: str | None = None
    source_order: int = 0


class RuleStatus(Enum):
    PENDING = auto()
    ACTIVE = auto()
    EXECUTED = auto()
    EXPIRED = auto()


@dataclass(slots=True, eq=False)
class RuleRuntime:
    definition: RuleDefinition
    status: RuleStatus
    activated_at_ply: int | None = None
    owner_move_count_at_activation: int | None = None
    executed_at_ply: int | None = None
    expired_at_ply: int | None = None


@dataclass(slots=True)
class PieceRuleCollection:
    all: list[RuleRuntime] = field(default_factory=list)
    pending: list[RuleRuntime] = field(default_factory=list)
    active: list[RuleRuntime] = field(default_factory=list)
    executed: list[RuleRuntime] = field(default_factory=list)
    expired: list[RuleRuntime] = field(default_factory=list)

    def add(self, rule: RuleRuntime) -> None:
        self.all.append(rule)
        self._bucket(rule.status).append(rule)

    def transition(self, rule: RuleRuntime, status: RuleStatus) -> None:
        if rule not in self.all:
            raise ValueError("Rule does not belong to this piece")
        current = self._bucket(rule.status)
        if rule not in current:
            raise RuntimeError("Rule status and collection are inconsistent")
        current.remove(rule)
        rule.status = status
        self._bucket(status).append(rule)

    def move_to_active(self, rule: RuleRuntime) -> None:
        self.transition(rule, RuleStatus.ACTIVE)

    def move_to_executed(self, rule: RuleRuntime) -> None:
        self.transition(rule, RuleStatus.EXECUTED)

    def move_to_expired(self, rule: RuleRuntime) -> None:
        self.transition(rule, RuleStatus.EXPIRED)

    def _bucket(self, status: RuleStatus) -> list[RuleRuntime]:
        return {
            RuleStatus.PENDING: self.pending,
            RuleStatus.ACTIVE: self.active,
            RuleStatus.EXECUTED: self.executed,
            RuleStatus.EXPIRED: self.expired,
        }[status]

    def assert_consistent(self) -> None:
        buckets = self.pending + self.active + self.executed + self.expired
        if len(buckets) != len(self.all) or set(buckets) != set(self.all):
            raise AssertionError("Rule collection contains missing or duplicate rules")
        for status in RuleStatus:
            if any(rule.status is not status for rule in self._bucket(status)):
                raise AssertionError(
                    f"Invalid member in {status.name.lower()} collection"
                )
