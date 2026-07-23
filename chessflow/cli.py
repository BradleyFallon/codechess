from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from chessflow.conformance import run_conformance
from chessflow.flow_language import parse_flow
from chessflow.learn import LearnError, run_learn
from chessflow.quiz import QuizError, run_quiz
from chessflow.reporting import render_text_report
from chessflow.repertoire import load_pgn


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codechess")
    commands = parser.add_subparsers(dest="command", required=True)
    test_pgn = commands.add_parser(
        "test-pgn",
        help="test a flow against a PGN repertoire",
    )
    test_pgn.add_argument("flow", type=Path)
    test_pgn.add_argument("pgn", type=Path)
    quiz = commands.add_parser(
        "quiz",
        help="practice a flow through every PGN line",
    )
    quiz.add_argument("flow", type=Path)
    quiz.add_argument("pgn", type=Path)
    learn = commands.add_parser(
        "learn",
        help="walk through every PGN line with guided coaching",
    )
    learn.add_argument("flow", type=Path)
    learn.add_argument("pgn", type=Path)
    args = parser.parse_args(argv)

    try:
        flow_path = _resolve_input(args.flow)
        pgn_path = _resolve_input(args.pgn)
        definition = parse_flow(flow_path.read_text())
        repertoire = load_pgn(pgn_path.read_text())
        if args.command == "quiz":
            run_quiz(definition, repertoire)
        elif args.command == "learn":
            run_learn(definition, repertoire)
        else:
            result = run_conformance(definition, repertoire)
            print(render_text_report(result), end="")
    except (LearnError, OSError, QuizError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


def _resolve_input(path: Path) -> Path:
    if path.exists() or path.is_absolute() or path.parent != Path():
        return path
    example_path = Path("examples") / path
    return example_path if example_path.exists() else path
