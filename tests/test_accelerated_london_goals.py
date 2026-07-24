from io import StringIO
from pathlib import Path

from chessflow import parse_flow
from chessflow.conformance import run_conformance
from chessflow.learn import run_learn
from chessflow.quiz import expand_lines
from chessflow.repertoire import load_pgn
from chessflow.reporting import summarize_conformance


EXAMPLES = Path(__file__).parents[1] / "examples"
FLOW = EXAMPLES / "accelerated_london_goals.flow"
PGN = EXAMPLES / "accelerated_london_goals_learn.pgn"


def test_goal_based_london_course_cleanly_matches_all_positions() -> None:
    definition = parse_flow(FLOW.read_text())
    repertoire = load_pgn(PGN.read_text())

    summary = summarize_conformance(
        run_conformance(definition, repertoire)
    )

    assert len(expand_lines(repertoire)) == 9
    assert summary.positions_tested == 49
    assert summary.matches == 49
    assert summary.ambiguities == 0
    assert summary.disagreements == 0
    assert summary.dead_ends == 0


def test_goal_based_london_course_completes_the_full_learn_walkthrough() -> None:
    definition = parse_flow(FLOW.read_text())
    repertoire = load_pgn(PGN.read_text())
    lines = expand_lines(repertoire)
    answers: list[str] = []
    for line_number, line in enumerate(lines, start=1):
        for ply, node in enumerate(line):
            if ply % 2 == 0:
                assert node.san is not None
                answers.extend((node.san, ""))
        if line_number < len(lines):
            answers.append("")
    answer_iterator = iter(answers)
    output = StringIO()

    completed = run_learn(
        definition,
        repertoire,
        input_fn=lambda: next(answer_iterator),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert rendered.count("Line complete.") == 9
    assert "NEW GOAL" in rendered
    assert "GOAL COMPLETE" in rendered
    assert "GOAL RETIRED" in rendered
    assert rendered.count("OPENING EXIT") == 3
    assert "out-of-system-advantage" in rendered
    assert "fork-rook-won" in rendered
    assert "queen-won" in rendered
    assert "Learn complete · 9 lines" in rendered
