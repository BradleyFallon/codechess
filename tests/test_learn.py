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

GOAL_FLOW_SOURCE = """
flow learn-goals
version 0.2
side white
goals:
    urgent:
        when: square.a6.has(enemy.pawn)
        while: true
        complete: false
        title: Use the urgent plan
        plan: Respond to the new opportunity before continuing normal development.
        abandoned: The urgent opportunity is no longer available.
    foundation:
        while: true
        complete: false
        title: Build the foundation
        plan: Claim central space while keeping the position flexible.
        abandoned: The foundation is no longer useful.
d:
    develop.d4:
        goals: foundation
c:
    develop.c4:
        goals: urgent
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


def test_learn_displays_the_current_goal_and_plan() -> None:
    output = StringIO()

    run_learn(
        parse_flow(GOAL_FLOW_SOURCE),
        load_pgn("1. d4 *"),
        input_fn=_answers("quit"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "Goal:\nBuild the foundation." in rendered
    assert "Plan:\nClaim central space while keeping the" in rendered
    assert "Fallback:\nNone" in rendered


def test_learn_announces_a_new_higher_priority_goal() -> None:
    output = StringIO()

    run_learn(
        parse_flow(GOAL_FLOW_SOURCE),
        load_pgn("1. d4 a6 2. c4 *"),
        input_fn=_answers("d4", "", "quit"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "NEW GOAL" in rendered
    assert "Goal:\nUse the urgent plan." in rendered
    assert "Fallback:\nBuild the foundation." in rendered


def test_learn_announces_goal_completion() -> None:
    definition = parse_flow(
        """
        flow learn-completion
        version 0.2
        side white
        goals:
            center:
                while: true
                complete: played(d.develop.d4)
                title: Claim the center
                plan: Establish a pawn on d4.
                abandoned: The center can no longer be claimed.
            development:
                while: true
                complete: false
                title: Continue development
                plan: Develop the minor pieces and castle.
                abandoned: Normal development is unavailable.
        d:
            develop.d4:
                goals: center
        """
    )
    output = StringIO()

    run_learn(
        definition,
        load_pgn("1. d4 *"),
        input_fn=_answers("d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "GOAL COMPLETE\n\nClaim the center." in rendered
    assert "Current goal:\nContinue development." in rendered
    assert "Plan:\nDevelop the minor pieces and castle." in rendered
    assert "Fallback:\nNone" in rendered


def test_learn_announces_retirement_and_fallback_transition() -> None:
    definition = parse_flow(
        """
        flow learn-retirement
        version 0.2
        side white
        goals:
            queenside:
                while: square.a7.has(enemy.pawn)
                complete: false
                title: Use the queenside window
                plan: Act while the a-pawn remains on a7.
                abandoned: The a-pawn moved and closed the window.
            fallback:
                while: true
                complete: false
                title: Continue normal development
                plan: Return to a sound central setup.
                abandoned: Normal development is unavailable.
        d:
            develop.d4:
                goals: queenside
        c:
            develop.c4:
                goals: fallback
        """
    )
    output = StringIO()

    run_learn(
        definition,
        load_pgn("1. d4 a6 2. c4 *"),
        input_fn=_answers("d4", "", "quit"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "GOAL RETIRED\n\nUse the queenside window." in rendered
    assert "Reason:\nThe a-pawn moved and closed the window." in rendered
    assert "Current goal:\nContinue normal development." in rendered
    assert "Plan:\nReturn to a sound central setup." in rendered
    assert "Fallback:\nNone" in rendered


def test_learn_announces_fallback_updates_without_changing_current_goal() -> None:
    definition = parse_flow(
        """
        flow learn-fallback
        version 0.2
        side white
        goals:
            current:
                while: true
                complete: false
                title: Keep the current plan
                plan: Continue the stable central setup.
                abandoned: The stable setup is unavailable.
            tactical-fallback:
                when: square.a6.has(enemy.pawn)
                while: true
                complete: false
                title: Use the tactical fallback
                plan: Exploit the newly available queenside target.
                abandoned: The tactical target disappeared.
            quiet-fallback:
                while: true
                complete: false
                title: Use the quiet fallback
                plan: Complete ordinary development.
                abandoned: Quiet development is unavailable.
        d:
            develop.d4:
                goals: current
        c:
            develop.c4:
                goals: current
                when: played(d.develop.d4)
        """
    )
    output = StringIO()

    run_learn(
        definition,
        load_pgn("1. d4 a6 2. c4 *"),
        input_fn=_answers("d4", "", "quit"),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert "FALLBACK UPDATED" in rendered
    assert "Goal:\nKeep the current plan." in rendered
    assert "Fallback:\nUse the tactical fallback." in rendered


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


def test_course_introduction_appears_only_on_the_first_line() -> None:
    output = StringIO()

    run_learn(
        parse_flow(FLOW_SOURCE),
        load_pgn(
            """
            {Learn the purpose of the opening before starting.}
            1. d4 d5 (1... Nf6) *
            """
        ),
        input_fn=_answers("d4", "", "", "d4", ""),
        output=output,
        clear_screen=False,
    )

    assert output.getvalue().count(
        "Coach:\nLearn the purpose of the opening before starting."
    ) == 1


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
        load_pgn(
            "1. d4 {Keep the c-pawn flexible for the right structure.} *"
        ),
        input_fn=_answers("e4", "d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert "Not quite." in rendered
    assert "Expected: d4" in rendered
    assert "Rule: d.develop.d4" in rendered
    assert "Claim central space and keep the c-pawn flexible." in rendered
    assert "Keep the c-pawn flexible for the right structure." in rendered
    assert "Type d4 to continue: " in rendered
    assert rendered.count("Correct: d4") == 1
    assert "Correct: e4" not in rendered
    correct_index = rendered.index("Correct: d4")
    continue_index = rendered.index(
        "Press Enter to continue.",
        correct_index,
    )
    correction_feedback = rendered[correct_index:continue_index]
    assert "Claim central space" not in correction_feedback
    assert "Keep the c-pawn flexible" not in correction_feedback


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


def test_terminal_move_completes_learn_line_without_later_pgn_moves() -> None:
    definition = parse_flow(
        """
        flow terminal-learn
        version 0.1
        side white
        d:
            develop.d4:
                terminal: center-claimed
                why: Take the available advantage.
        """
    )
    output = StringIO()

    completed = run_learn(
        definition,
        load_pgn("1. d4 d5 2. c4 *"),
        input_fn=_answers("d4", ""),
        output=output,
        clear_screen=False,
    )

    rendered = output.getvalue()
    assert completed
    assert rendered.count("Your move: ") == 1
    assert "Q1/1" in rendered
    assert (
        "OPENING EXIT\n\ncenter-claimed\n\n"
        "Take the available advantage."
    ) in rendered
    assert rendered.index("OPENING EXIT") < rendered.index("Line complete.")
    assert "Line complete." in rendered


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
