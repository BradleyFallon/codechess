from __future__ import annotations

from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime import GoalDeadEndError
from chessflow.repertoire import RepertoireNode
from chessflow.session import FlowSession

from chessflow.conformance.result import (
    CandidateRecord,
    ConformanceNode,
    ConformanceResult,
    ConformanceStatus,
)


class ConformanceRunner:
    def __init__(
        self,
        definition: FlowDefinition,
        repertoire: RepertoireNode,
    ) -> None:
        self.definition = definition
        self.repertoire = repertoire

    def run(self) -> ConformanceResult:
        session = FlowSession.fresh(self.definition)
        if session.board.fen != self.repertoire.fen:
            raise ValueError("Flow and PGN must begin from the same position")
        return ConformanceResult(
            self._walk(self.repertoire, session, path=())
        )

    def _walk(
        self,
        repertoire_node: RepertoireNode,
        session: FlowSession,
        path: tuple[str, ...],
    ) -> ConformanceNode:
        if not repertoire_node.children:
            return ConformanceNode(path_san=path)
        if (
            session.board.chess_board.turn
            == self.definition.side.chess_color
        ):
            return self._walk_flow_turn(repertoire_node, session, path)
        return self._walk_opponent_turn(repertoire_node, session, path)

    def _walk_flow_turn(
        self,
        repertoire_node: RepertoireNode,
        session: FlowSession,
        path: tuple[str, ...],
    ) -> ConformanceNode:
        expected_moves = tuple(
            child.move
            for child in repertoire_node.children
            if child.move is not None
        )
        expected_san = tuple(
            child.san
            for child in repertoire_node.children
            if child.san is not None
        )
        try:
            candidates = tuple(session.runtime.evaluate_turn(session.board))
        except GoalDeadEndError as exc:
            raise exc.at_path(_format_san_path(path)) from exc
        candidate_records = tuple(
            CandidateRecord(
                action_key=candidate.rule.definition.action.canonical_key,
                move=candidate.move,
                san=session.board.chess_board.san(candidate.move),
            )
            for candidate in candidates
        )
        if not candidates:
            return ConformanceNode(
                path_san=path,
                status=ConformanceStatus.DEAD_END,
                expected_moves=expected_moves,
                expected_san=expected_san,
            )

        selected = candidates[0]
        selected_record = candidate_records[0]
        matching_child = next(
            (
                child
                for child in repertoire_node.children
                if child.move == selected.move
            ),
            None,
        )
        if matching_child is None:
            return ConformanceNode(
                path_san=path,
                status=ConformanceStatus.DISAGREEMENT,
                expected_moves=expected_moves,
                expected_san=expected_san,
                candidates=candidate_records,
                selected_action=selected_record.action_key,
                selected_move=selected_record.move,
                selected_san=selected_record.san,
            )

        status = (
            ConformanceStatus.AMBIGUOUS
            if len(candidates) > 1
            else ConformanceStatus.MATCH
        )
        session.runtime.execute(selected, session.board)
        assert matching_child.san is not None
        matched_path = (*path, matching_child.san)
        return ConformanceNode(
            path_san=matched_path,
            status=status,
            expected_moves=expected_moves,
            expected_san=expected_san,
            candidates=candidate_records,
            selected_action=selected_record.action_key,
            selected_move=selected_record.move,
            selected_san=selected_record.san,
            children=[
                self._walk(matching_child, session, matched_path)
            ],
        )

    def _walk_opponent_turn(
        self,
        repertoire_node: RepertoireNode,
        session: FlowSession,
        path: tuple[str, ...],
    ) -> ConformanceNode:
        result = ConformanceNode(path_san=path)
        for child in repertoire_node.children:
            assert child.move is not None
            assert child.san is not None
            branch = session.clone()
            branch.runtime.push_opponent(child.move, branch.board)
            child_path = (*path, child.san)
            result.children.append(self._walk(child, branch, child_path))
        return result


def run_conformance(
    definition: FlowDefinition,
    repertoire: RepertoireNode,
) -> ConformanceResult:
    return ConformanceRunner(definition, repertoire).run()


def _format_san_path(path: tuple[str, ...]) -> str:
    if not path:
        return "(starting position)"
    parts: list[str] = []
    for ply, san in enumerate(path):
        if ply % 2 == 0:
            parts.append(f"{ply // 2 + 1}.{san}")
        else:
            parts.append(san)
    return " ".join(parts)
