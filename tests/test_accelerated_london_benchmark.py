from pathlib import Path

from chessflow import parse_flow
from chessflow.conformance import run_conformance
from chessflow.reporting import render_text_report, summarize_conformance
from chessflow.repertoire import RepertoireNode, load_pgn


EXAMPLES = Path(__file__).parents[1] / "examples"
BENCHMARK = EXAMPLES / "accelerated-london-benchmark.pgn"
FLOW = EXAMPLES / "vertical-slice.flow"

INCOMPLETE_FLOW = """
flow: london-incomplete-baseline
version: 0.1
side: white

flags:
    center-claimed

conditions:
    d-pawn-developed = played(d.develop.d4)
    bishop-developed = played(bq.develop.f4)
    e-pawn-developed = played(e.develop.e3)

d:
    develop.d4:
        set: center-claimed
        why: claim the center

bq:
    develop.f4:
        when: d-pawn-developed
        if: center-claimed
        why: develop outside the pawn chain

e:
    develop.e3:
        when: bishop-developed
        if: at(e2)
        why: support d4 and open the kingside bishop

nk:
    develop.f3:
        when: e-pawn-developed
        why: defend d4 and control e5
"""


def _child(node: RepertoireNode, san: str) -> RepertoireNode:
    return next(child for child in node.children if child.san == san)


def _node_count(node: RepertoireNode) -> int:
    return 1 + sum(_node_count(child) for child in node.children)


def test_accelerated_london_benchmark_tree() -> None:
    repertoire = load_pgn(BENCHMARK.read_text())

    assert _node_count(repertoire) == 169
    d4 = _child(repertoire, "d4")
    assert [child.san for child in d4.children] == ["d5", "c5", "Nf6"]
    immediate_c5_d5 = _child(_child(d4, "c5"), "d5")
    assert immediate_c5_d5.comment is not None
    assert "Benoni-style space setup" in immediate_c5_d5.comment

    early_knight = _child(_child(d4, "Nf6"), "Bf4")
    assert [child.san for child in early_knight.children] == [
        "d5",
        "g6",
        "b6",
    ]
    fork = _child(
        _child(
            _child(
                _child(early_knight, "d5"),
                "Nc3",
            ),
            "e6",
        ),
        "Nb5",
    )
    assert [child.san for child in fork.children] == [
        "Na6",
        "Be7",
        "c6",
        "Bb4+",
        "Bd6",
    ]


def test_vertical_slice_terminal_line_ends_at_n_f3() -> None:
    repertoire = load_pgn(
        "1. d4 d5 2. Bf4 Nf6 3. e3 e6 4. Nf3 *"
    )

    result = run_conformance(parse_flow(FLOW.read_text()), repertoire)
    summary = summarize_conformance(result)

    assert summary.positions_tested == 4
    assert summary.matches == 4
    assert summary.ambiguities == 0
    assert summary.disagreements == 0
    assert summary.dead_ends == 0


def test_explicit_incomplete_flow_baseline_against_full_benchmark() -> None:
    repertoire = load_pgn(BENCHMARK.read_text())

    result = run_conformance(parse_flow(INCOMPLETE_FLOW), repertoire)
    summary = summarize_conformance(result)

    assert summary.positions_tested == 18
    assert summary.matches == 8
    assert summary.ambiguities == 0
    assert summary.disagreements == 8
    assert summary.dead_ends == 2

    report = render_text_report(result)
    assert "DISAGREEMENT\n1.d4 c5" in report
    assert "Expected: d5" in report
    assert "Flow: Bf4" in report
    assert "DEAD END\n1.d4 d5 2.Bf4 Nf6 3.e3 Bg4 4.Nf3 e6" in report
