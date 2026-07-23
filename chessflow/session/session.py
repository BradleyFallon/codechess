from __future__ import annotations

from dataclasses import dataclass

from chessflow.chess_model import FlowBoard
from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime import FlowRuntime


@dataclass(slots=True)
class FlowSession:
    definition: FlowDefinition
    board: FlowBoard
    runtime: FlowRuntime

    @classmethod
    def fresh(cls, definition: FlowDefinition) -> FlowSession:
        board = FlowBoard()
        return cls(
            definition=definition,
            board=board,
            runtime=FlowRuntime(definition, board),
        )

    def clone(self) -> FlowSession:
        board = FlowBoard(self.board.chess_board.copy(stack=True))
        runtime = FlowRuntime.restore(
            definition=self.definition,
            board=board,
            snapshot=self.runtime.snapshot(),
        )
        return FlowSession(
            definition=self.definition,
            board=board,
            runtime=runtime,
        )
