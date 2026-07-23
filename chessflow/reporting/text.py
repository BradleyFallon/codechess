from __future__ import annotations

from dataclasses import dataclass

from chessflow.conformance import (
    ConformanceNode,
    ConformanceResult,
    ConformanceStatus,
)


@dataclass(frozen=True, slots=True)
class ConformanceSummary:
    positions_tested: int
    matches: int
    ambiguities: int
    disagreements: int
    dead_ends: int


def summarize_conformance(result: ConformanceResult) -> ConformanceSummary:
    nodes = _decision_nodes(result.root)
    return ConformanceSummary(
        positions_tested=len(nodes),
        matches=sum(node.status is ConformanceStatus.MATCH for node in nodes),
        ambiguities=sum(
            node.status is ConformanceStatus.AMBIGUOUS for node in nodes
        ),
        disagreements=sum(
            node.status is ConformanceStatus.DISAGREEMENT for node in nodes
        ),
        dead_ends=sum(
            node.status is ConformanceStatus.DEAD_END for node in nodes
        ),
    )


def render_text_report(result: ConformanceResult) -> str:
    summary = summarize_conformance(result)
    sections = [
        "\n".join(
            (
                f"Positions tested: {summary.positions_tested}",
                f"Matches: {summary.matches}",
                f"Ambiguities: {summary.ambiguities}",
                f"Disagreements: {summary.disagreements}",
                f"Dead ends: {summary.dead_ends}",
            )
        )
    ]
    sections.extend(_render_node(node) for node in _decision_nodes(result.root))
    return "\n\n".join(sections) + "\n"


def format_san_path(path: tuple[str, ...]) -> str:
    if not path:
        return "(starting position)"
    parts: list[str] = []
    for ply, san in enumerate(path):
        if ply % 2 == 0:
            parts.append(f"{ply // 2 + 1}.{san}")
        else:
            parts.append(san)
    return " ".join(parts)


def _decision_nodes(node: ConformanceNode) -> list[ConformanceNode]:
    nodes = [node] if node.status is not None else []
    for child in node.children:
        nodes.extend(_decision_nodes(child))
    return nodes


def _render_node(node: ConformanceNode) -> str:
    assert node.status is not None
    lines = [
        node.status.name.replace("_", " "),
        format_san_path(node.path_san),
    ]
    if node.status is ConformanceStatus.AMBIGUOUS:
        lines.append("Candidates:")
        lines.extend(
            f"  {candidate.action_key}" for candidate in node.candidates
        )
    elif node.status is ConformanceStatus.DISAGREEMENT:
        lines.append(f"Expected: {', '.join(node.expected_san)}")
        lines.append(f"Flow: {node.selected_san}")
        lines.append(f"Rule: {node.selected_action}")
    return "\n".join(lines)
