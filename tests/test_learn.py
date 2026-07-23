from io import StringIO
from pathlib import Path
import re

import chess

from chessflow import parse_flow
from chessflow.conformance import run_conformance
from chessflow.learn import run_learn
from chessflow.quiz import expand_lines, render_board
from chessflow.repertoire import load_pgn
from chessflow.reporting import summarize_conformance


FLOW_SOURCE = """
flow learn
version 0.1
side white
d:
    develop.d4:
        why: Claim central space and keep the c-pawn flexible.
bq:
    develop.f4:
        when: d.developed()
        why: Develop the bishop outside the pawn chain.
"""


def _answers(*answers: str):
    iterator = iter(answers)
    return lambda: next(iterator)


def test_first_encounter_displays_new_rule_and_reinforcement() -> None:
    output = StringIO()

    completed = run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn(
            """
            {Begin by taking space in the center.}
            1. d4
            {This keeps the c-pawn available for c3 or c4.} *
            """
        ),
        input_fn=_answers("d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert "NEW RULE\nd.develop.d4" in rendered
    assert "Claim central space and keep the c-pawn flexible." in rendered
    assert "This keeps the c-pawn available for c3 or c4." in rendered


def test_correct_answer_renders_the_moved_piece_before_confirmation() -> None:
    output = StringIO()
    expected_board = chess.Board()
    expected_board.push_san("d4")

    run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    board_index = rendered.index(render_board(expected_board))
    correct_index = rendered.index("Correct: d4")
    assert board_index < correct_index
    assert "1.d4\n\n" in rendered[board_index - 10 : board_index]


def test_repeated_rule_displays_review() -> None:
    output = StringIO()

    completed = run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 d5 (1... Nf6) *"),
        input_fn=_answers("d4", "", "", "d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert rendered.count("NEW RULE\nd.develop.d4") == 1
    assert "\nREVIEW\n" in rendered
    assert "Reviewed: 1 rules" in rendered


def test_preceding_black_comment_appears_before_prompt() -> None:
    output = StringIO()

    run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn(
            """
            1. d4 d5
            {Black has established a pawn on d5.}
            2. Bf4
            {Develop before playing e3.} *
            """
        ),
        input_fn=_answers("d4", "", "Bf4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    comment_index = rendered.index("Black has established a pawn on d5.")
    second_prompt_index = rendered.index(
        "Your move: ",
        rendered.index("Correct: d4"),
    )
    assert comment_index < second_prompt_index


def test_wrong_answer_requires_correction_without_advancing() -> None:
    output = StringIO()

    completed = run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("e4", "d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert "Not quite." in rendered
    assert "Expected: d4" in rendered
    assert "Rule: d.develop.d4" in rendered
    assert "Type d4 to continue: " in rendered
    assert rendered.count("Correct: d4") == 1
    assert "Correct: e4" not in rendered


def test_line_completion_lists_new_rules() -> None:
    output = StringIO()

    run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 d5 2. Bf4 *"),
        input_fn=_answers("d4", "", "Bf4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "Line complete." in rendered
    assert "New rules:\n  d.develop.d4" in rendered
    assert "    Claim central space and keep the c-pawn" in rendered
    assert "  bq.develop.f4" in rendered
    assert "Reviewed: 0 rules" in rendered
    status_lines = re.findall(r"── Learn.*", rendered)
    assert all(len(line) == 50 for line in status_lines)


def test_quit_stops_the_walkthrough() -> None:
    output = StringIO()

    completed = run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("quit"),
        output=output,
        clear_screen=False,
    )

    assert not completed
    assert "Correct:" not in output.getvalue()
    assert "Opening walkthrough complete." not in output.getvalue()


def test_accelerated_london_learn_example_matches_the_full_flow() -> None:
    repository = Path(__file__).parents[1]
    definition = parse_flow(
        (
            repository
            / "examples"
            / "accelerated_london_second_pass.flow"
        ).read_text()
    )
    repertoire = load_pgn(
        (
            repository
            / "examples"
            / "accelerated_london_learn.pgn"
        ).read_text()
    )

    summary = summarize_conformance(
        run_conformance(definition, repertoire)
    )

    assert len(expand_lines(repertoire)) == 17
    assert summary.positions_tested == 84
    assert summary.matches == 84
    assert summary.ambiguities == 0
    assert summary.disagreements == 0
    assert summary.dead_ends == 0
