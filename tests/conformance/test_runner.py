import chess

from chessflow import parse_flow
from chessflow.conformance import (
    ConformanceNode,
    ConformanceStatus,
    run_conformance,
)
from chessflow.repertoire import load_pgn


def _decision_nodes(node: ConformanceNode) -> list[ConformanceNode]:
    result = [node] if node.status is not None else []
    for child in node.children:
        result.extend(_decision_nodes(child))
    return result


def test_exact_matches_follow_the_reference_line() -> None:
    definition = parse_flow(
        """
        flow exact
        version 0.1
        side white
        d:
            develop.d4:
        bq:
            develop.f4:
                when: d.developed()
        """
    )
    repertoire = load_pgn("1. d4 d5 2. Bf4 *")

    result = run_conformance(definition, repertoire)
    decisions = _decision_nodes(result.root)

    assert [node.status for node in decisions] == [
        ConformanceStatus.MATCH,
        ConformanceStatus.MATCH,
    ]
    assert decisions[0].path_san == ("d4",)
    assert decisions[1].path_san == ("d4", "d5", "Bf4")
    assert decisions[1].selected_action == "bq.develop.f4"
    assert decisions[1].selected_move == chess.Move.from_uci("c1f4")


def test_matching_selected_move_reports_ambiguity() -> None:
    definition = parse_flow(
        """
        flow ambiguous
        version 0.1
        side white
        d:
            develop.d4:
        e:
            develop.e4:
        """
    )

    result = run_conformance(definition, load_pgn("1. d4 *"))
    node = result.root

    assert node.status is ConformanceStatus.AMBIGUOUS
    assert [candidate.action_key for candidate in node.candidates] == [
        "d.develop.d4",
        "e.develop.e4",
    ]
    assert node.selected_move == chess.Move.from_uci("d2d4")


def test_unlisted_selected_move_is_a_disagreement() -> None:
    definition = parse_flow(
        """
        flow disagreement
        version 0.1
        side white
        e:
            develop.e4:
        """
    )

    node = run_conformance(definition, load_pgn("1. d4 *")).root

    assert node.status is ConformanceStatus.DISAGREEMENT
    assert node.path_san == ()
    assert node.expected_moves == (chess.Move.from_uci("d2d4"),)
    assert node.expected_san == ("d4",)
    assert node.selected_action == "e.develop.e4"
    assert node.selected_san == "e4"
    assert node.children == []


def test_no_legal_flow_candidate_is_a_dead_end() -> None:
    definition = parse_flow(
        """
        flow dead-end
        version 0.1
        side white
        bq:
            develop.f4:
        """
    )

    node = run_conformance(definition, load_pgn("1. d4 *")).root

    assert node.status is ConformanceStatus.DEAD_END
    assert node.expected_san == ("d4",)
    assert node.candidates == ()
    assert node.selected_move is None
    assert node.children == []


def test_multiple_black_branches_have_isolated_flow_state() -> None:
    definition = parse_flow(
        """
        flow branches
        version 0.1
        side white
        d:
            develop.d4:
        bq:
            develop.f4:
                when: d.developed()
        """
    )
    repertoire = load_pgn(
        "1. d4 d5 (1... Nf6 2. Bf4) 2. Bf4 *"
    )

    result = run_conformance(definition, repertoire)
    decisions = _decision_nodes(result.root)
    bishop_decisions = [
        node
        for node in decisions
        if node.selected_action == "bq.develop.f4"
    ]

    assert len(bishop_decisions) == 2
    assert all(
        node.status is ConformanceStatus.MATCH
        for node in bishop_decisions
    )
    assert {node.path_san for node in bishop_decisions} == {
        ("d4", "d5", "Bf4"),
        ("d4", "Nf6", "Bf4"),
    }


def test_reference_leaf_completes_without_an_extra_dead_end() -> None:
    definition = parse_flow(
        """
        flow leaf
        version 0.1
        side white
        d:
            develop.d4:
        """
    )

    result = run_conformance(definition, load_pgn("1. d4 *"))
    decisions = _decision_nodes(result.root)

    assert [node.status for node in decisions] == [ConformanceStatus.MATCH]
    assert result.root.children[0].status is None
    assert result.root.children[0].children == []
