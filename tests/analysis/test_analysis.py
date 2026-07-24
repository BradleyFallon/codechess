import json
from pathlib import Path

import chess

from chessflow import parse_flow
from chessflow.analysis import AnalysisStatus, analyze_flow
from chessflow.conformance import run_conformance
from chessflow.repertoire import load_pgn
from chessflow.reporting import summarize_conformance
from chessflow.serialization import to_json_data


EXAMPLES = Path(__file__).parents[2] / "examples"


def test_goal_course_analysis_matches_conformance_and_has_valid_fens() -> None:
    definition = parse_flow(
        (EXAMPLES / "accelerated_london_goals.flow").read_text()
    )
    repertoire = load_pgn(
        (
            EXAMPLES / "accelerated_london_goals_learn.pgn"
        ).read_text()
    )

    result = analyze_flow(definition, repertoire)
    conformance = summarize_conformance(
        run_conformance(definition, repertoire)
    )

    assert result.summary.benchmark_positions == 49
    assert result.summary.positions_evaluated == 49
    assert result.summary.matches == conformance.matches == 49
    assert result.summary.ambiguities == conformance.ambiguities == 0
    assert result.summary.disagreements == conformance.disagreements == 0
    assert result.summary.dead_ends == conformance.dead_ends == 0
    assert result.summary.terminal_exits == 3
    assert result.summary.rules_declared == 25
    assert result.summary.rules_executed == 25
    assert all(
        isinstance(chess.Board(finding.fen), chess.Board)
        for finding in result.findings
    )
    serialized = to_json_data(result)
    assert json.loads(json.dumps(serialized)) == serialized


def test_disagreement_includes_selected_rule_move_and_position() -> None:
    definition = parse_flow(
        """
        flow analysis-disagreement
        version 0.1
        side white
        e:
            develop.e4:
        """
    )

    result = analyze_flow(definition, load_pgn("1. d4 *"))
    finding = result.findings[0]

    assert finding.status is AnalysisStatus.DISAGREEMENT
    assert finding.path_san == ()
    assert finding.fen == chess.Board().fen()
    assert finding.expected_san == ("d4",)
    assert finding.selected_san == "e4"
    assert finding.selected_rule == "e.develop.e4"
    assert finding.candidates[0].uci == "e2e4"


def test_ambiguity_includes_every_candidate() -> None:
    definition = parse_flow(
        """
        flow analysis-ambiguity
        version 0.1
        side white
        d:
            develop.d4:
        e:
            develop.e4:
        """
    )

    finding = analyze_flow(
        definition,
        load_pgn("1. d4 *"),
    ).findings[0]

    assert finding.status is AnalysisStatus.AMBIGUITY
    assert [
        candidate.rule_key for candidate in finding.candidates
    ] == ["d.develop.d4", "e.develop.e4"]
    assert [candidate.san for candidate in finding.candidates] == [
        "d4",
        "e4",
    ]


def test_goal_dead_end_preserves_current_and_fallback_context() -> None:
    definition = parse_flow(
        """
        flow analysis-dead-end
        version 0.2
        side white
        goals:
            current:
                while: true
                complete: false
                title: Current
                plan: Use the current plan.
                abandoned: Current retired.
            fallback:
                while: true
                complete: false
                title: Fallback
                plan: Use the fallback plan.
                abandoned: Fallback retired.
        e:
            develop.e4:
                goals: fallback
        """
    )

    result = analyze_flow(definition, load_pgn("1. d4 *"))
    finding = result.findings[0]

    assert finding.status is AnalysisStatus.DEAD_END
    assert finding.current_goal == "current"
    assert finding.fallback_goal == "fallback"
    assert finding.selected_rule is None
    assert result.summary.dead_ends == 1
    assert result.summary.positions_evaluated == 1


def test_terminal_finding_includes_terminal_key() -> None:
    definition = parse_flow(
        """
        flow analysis-terminal
        version 0.1
        side white
        d:
            develop.d4:
                terminal: prepared
        """
    )

    result = analyze_flow(definition, load_pgn("1. d4 *"))
    finding = result.findings[0]

    assert finding.status is AnalysisStatus.TERMINAL
    assert finding.terminal == "prepared"
    assert finding.selected_rule == "d.develop.d4"
    assert result.summary.matches == 1
    assert result.summary.terminal_exits == 1
    assert result.summary.rules_declared == 1
    assert result.summary.rules_executed == 1


def test_partial_analysis_distinguishes_benchmark_and_reached_positions() -> None:
    definition = parse_flow(
        """
        flow partial-analysis
        version 0.1
        side white
        e:
            develop.e4:
        """
    )
    repertoire = load_pgn(
        "1. d4 d5 (1... Nf6 2. Bf4) 2. Bf4 *"
    )

    result = analyze_flow(definition, repertoire)

    assert result.summary.benchmark_positions == 3
    assert result.summary.positions_evaluated == 1
    assert result.summary.disagreements == 1
