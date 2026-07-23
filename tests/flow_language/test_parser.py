from pathlib import Path

import chess
import pytest

from chessflow.flow_language import FlowSyntaxError, parse_flow
from chessflow.flow_runtime import ActionKind


EXAMPLE = Path(__file__).parents[2] / "examples" / "vertical-slice.flow"


def test_flow_schema_parses_with_direct_domain_parity() -> None:
    definition = parse_flow(EXAMPLE.read_text())

    assert definition.name == "london-vertical-slice"
    assert definition.version == "0.1"
    assert definition.declared_flags == frozenset({"center-claimed"})
    assert len(definition.conditions) == 3
    assert len(definition.rules) == 4
    first = definition.rules[0]
    assert first.action.owner_code == "d"
    assert first.action.kind is ActionKind.DEVELOP
    assert first.action.target_square == chess.D4
    assert first.set_flags == ("center-claimed",)
    assert first.why == "claim the center"


def test_parser_rejects_undeclared_set_flags() -> None:
    with pytest.raises(FlowSyntaxError, match="undeclared flags"):
        parse_flow(
            """
            flow demo
            version 0.1
            side white
            d:
                develop.d4:
                    set: missing
            """
        )


def test_parser_rejects_duplicate_actions() -> None:
    with pytest.raises(FlowSyntaxError, match="Duplicate rule action"):
        parse_flow(
            """
            flow demo
            version 0.1
            side white
            d:
                develop.d4:
                    why: first
                develop.d4:
                    why: duplicate
            """
        )


def test_multiline_boolean_fields_and_conditions_parse() -> None:
    definition = parse_flow(
        """
        flow multiline
        version 0.1
        side white
        flags:
            enabled
        conditions:
            ready =
                at(d2) &&
                !attacked()
        d:
            develop.d4:
                if: ready &&
                    enabled
        """
    )

    assert "ready" in definition.conditions
    assert definition.rules[0].if_condition is not None


def test_parser_rejects_unknown_condition_names() -> None:
    with pytest.raises(FlowSyntaxError, match="Unknown condition or flag"):
        parse_flow(
            """
            flow unknown-name
            version 0.1
            side white
            d:
                develop.d4:
                    if: misspelled-condition
            """
        )
