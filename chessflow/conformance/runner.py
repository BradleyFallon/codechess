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
        *,
        strict_goal_dead_ends: bool = True,
    ) -> None:
        self.definition = definition
        self.repertoire = repertoire
        self.strict_goal_dead_ends = strict_goal_dead_ends

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
        if session.runtime.is_terminal:
            if repertoire_node.children:
                terminal = session.runtime.reached_terminals[-1]
                raise ValueError(
                    f"PGN continues after terminal {terminal} "
                    f"at {_format_san_path(path)}"
                )
            return ConformanceNode(path_san=path)
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
        current = session.runtime.current_goal(session.board)
        fallback = session.runtime.fallback_goal(session.board)
        current_goal = (
            None if current is None else current.definition.key
        )
        fallback_goal = (
            None if fallback is None else fallback.definition.key
        )
        try:
            candidates = tuple(
                session.runtime.evaluate_turn(session.board)
            )
        except GoalDeadEndError as exc:
            if self.strict_goal_dead_ends:
                raise exc.at_path(_format_san_path(path)) from exc
            candidates = ()
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
                position_path_san=path,
                fen=session.board.fen,
                status=ConformanceStatus.DEAD_END,
                expected_moves=expected_moves,
                expected_san=expected_san,
                current_goal=current_goal,
                fallback_goal=fallback_goal,
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
                position_path_san=path,
                fen=session.board.fen,
                status=ConformanceStatus.DISAGREEMENT,
                expected_moves=expected_moves,
                expected_san=expected_san,
                candidates=candidate_records,
                selected_action=selected_record.action_key,
                selected_move=selected_record.move,
                selected_san=selected_record.san,
                current_goal=current_goal,
                fallback_goal=fallback_goal,
            )

        status = (
            ConformanceStatus.AMBIGUOUS
            if len(candidates) > 1
            else ConformanceStatus.MATCH
        )
        session.runtime.execute(selected, session.board)
        terminal = selected.rule.definition.terminal
        assert matching_child.san is not None
        matched_path = (*path, matching_child.san)
        return ConformanceNode(
            path_san=matched_path,
            position_path_san=path,
            fen=repertoire_node.fen,
            status=status,
            expected_moves=expected_moves,
            expected_san=expected_san,
            candidates=candidate_records,
            selected_action=selected_record.action_key,
            selected_move=selected_record.move,
            selected_san=selected_record.san,
            current_goal=current_goal,
            fallback_goal=fallback_goal,
            terminal=terminal,
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
    *,
    strict_goal_dead_ends: bool = True,
) -> ConformanceResult:
    return ConformanceRunner(
        definition,
        repertoire,
        strict_goal_dead_ends=strict_goal_dead_ends,
    ).run()


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
