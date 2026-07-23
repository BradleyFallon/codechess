from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from chessflow.chess_model import FlowBoard
from chessflow.flow_runtime import Candidate, FlowRuntime


class TurnOutcome(Enum):
    DEAD_END = "dead-end"
    SELECTED = "selected"
    AMBIGUOUS = "ambiguous"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class TurnReport:
    outcome: TurnOutcome
    candidates: tuple[Candidate, ...]
    selected: Candidate | None = None
    terminal: str | None = None

    @property
    def had_ambiguity(self) -> bool:
        return len(self.candidates) > 1


class FlowRunner:
    """Selects by source order while retaining every candidate in its report."""

    def __init__(self, flow: FlowRuntime, board: FlowBoard) -> None:
        self.flow = flow
        self.board = board

    def play_flow_turn(self) -> TurnReport:
        candidates = tuple(self.flow.evaluate_turn(self.board))
        if not candidates:
            return TurnReport(TurnOutcome.DEAD_END, candidates)
        selected = candidates[0]
        self.flow.execute(selected, self.board)
        terminal = selected.rule.definition.terminal
        if terminal is not None:
            outcome = TurnOutcome.TERMINAL
        elif len(candidates) > 1:
            outcome = TurnOutcome.AMBIGUOUS
        else:
            outcome = TurnOutcome.SELECTED
        return TurnReport(outcome, candidates, selected, terminal)
