from __future__ import annotations

import chess

from chessflow.conformance import (
    ConformanceNode,
    ConformanceStatus,
    run_conformance,
)
from chessflow.flow_language.ast import FlowDefinition
from chessflow.repertoire import RepertoireNode

from chessflow.analysis.model import (
    AnalysisCandidate,
    AnalysisFinding,
    AnalysisResult,
    AnalysisStatus,
    AnalysisSummary,
)


def analyze_flow(
    definition: FlowDefinition,
    repertoire: RepertoireNode,
) -> AnalysisResult:
    conformance = run_conformance(
        definition,
        repertoire,
        strict_goal_dead_ends=False,
    )
    nodes = tuple(_decision_nodes(conformance.root))
    findings = tuple(_finding(node) for node in nodes)
    selected_rules = {
        node.selected_action
        for node in nodes
        if node.selected_action is not None
    }
    summary = AnalysisSummary(
        benchmark_positions=_benchmark_positions(
            repertoire,
            definition.side.chess_color,
        ),
        positions_evaluated=len(nodes),
        matches=sum(
            node.status is ConformanceStatus.MATCH for node in nodes
        ),
        ambiguities=sum(
            node.status is ConformanceStatus.AMBIGUOUS
            for node in nodes
        ),
        disagreements=sum(
            node.status is ConformanceStatus.DISAGREEMENT
            for node in nodes
        ),
        dead_ends=sum(
            node.status is ConformanceStatus.DEAD_END for node in nodes
        ),
        terminal_exits=sum(node.terminal is not None for node in nodes),
        rules_declared=len(definition.rules),
        rules_executed=len(selected_rules),
    )
    return AnalysisResult(summary=summary, findings=findings)


def _decision_nodes(node: ConformanceNode) -> list[ConformanceNode]:
    nodes = [node] if node.status is not None else []
    for child in node.children:
        nodes.extend(_decision_nodes(child))
    return nodes


def _benchmark_positions(
    node: RepertoireNode,
    flow_color: chess.Color,
) -> int:
    board = chess.Board(node.fen)
    count = int(bool(node.children) and board.turn == flow_color)
    return count + sum(
        _benchmark_positions(child, flow_color)
        for child in node.children
    )


def _finding(node: ConformanceNode) -> AnalysisFinding:
    assert node.status is not None
    if node.terminal is not None:
        status = AnalysisStatus.TERMINAL
    else:
        status = {
            ConformanceStatus.MATCH: AnalysisStatus.MATCH,
            ConformanceStatus.AMBIGUOUS: AnalysisStatus.AMBIGUITY,
            ConformanceStatus.DISAGREEMENT: AnalysisStatus.DISAGREEMENT,
            ConformanceStatus.DEAD_END: AnalysisStatus.DEAD_END,
        }[node.status]
    return AnalysisFinding(
        path_san=node.position_path_san,
        fen=node.fen,
        status=status,
        expected_san=node.expected_san,
        selected_san=node.selected_san,
        selected_rule=node.selected_action,
        candidates=tuple(
            AnalysisCandidate(
                rule_key=candidate.action_key,
                uci=candidate.move.uci(),
                san=candidate.san,
            )
            for candidate in node.candidates
        ),
        current_goal=node.current_goal,
        fallback_goal=node.fallback_goal,
        terminal=node.terminal,
    )
