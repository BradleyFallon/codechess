from __future__ import annotations

from dataclasses import dataclass
import re
import textwrap
from typing import Never

import chess

from chessflow.chess_model.piece import Color
from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_language.expressions import (
    BooleanOperation,
    Call,
    Expression,
    Name,
    Not,
    parse_expression,
)
from chessflow.flow_runtime.action import Action, ActionKind, CastleSide
from chessflow.flow_runtime.rule import RuleDefinition


class FlowSyntaxError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _Line:
    number: int
    indent: int
    text: str


_PIECE_CODES = frozenset(
    {
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "nq",
        "nk",
        "bq",
        "bk",
        "rq",
        "rk",
        "q",
        "k",
    }
)


class FlowParser:
    """Parser for the indentation-based flow schema described by the domain model."""

    def parse(self, source: str) -> FlowDefinition:
        lines = self._lines(source)
        name: str | None = None
        version: str | None = None
        side: Color | None = None
        flags: set[str] = set()
        conditions: dict[str, Expression] = {}
        rules: list[RuleDefinition] = []
        owner: str | None = None
        index = 0

        while index < len(lines):
            line = lines[index]
            if line.indent == 0 and self._header_value(line.text, "flow") is not None:
                name = self._header_value(line.text, "flow")
                index += 1
                continue
            if (
                line.indent == 0
                and self._header_value(line.text, "version") is not None
            ):
                version = self._header_value(line.text, "version")
                index += 1
                continue
            if line.indent == 0 and self._header_value(line.text, "side") is not None:
                try:
                    side = Color.parse(self._header_value(line.text, "side") or "")
                except ValueError as exc:
                    self._error(line, str(exc))
                index += 1
                continue
            if line.indent == 0 and line.text in {"flags:", "flags{"}:
                index = self._parse_flags(lines, index + 1, flags)
                continue
            if line.indent == 0 and line.text in {"conditions:", "conditions{"}:
                index = self._parse_conditions(lines, index + 1, conditions)
                continue
            if line.indent == 0 and line.text.endswith(":"):
                candidate = line.text[:-1].strip()
                if candidate not in _PIECE_CODES:
                    self._error(line, f"Unknown flow piece code: {candidate!r}")
                owner = candidate
                index += 1
                continue
            if owner is not None and line.indent > 0 and line.text.endswith(":"):
                rule, index = self._parse_rule(lines, index, owner, len(rules))
                rules.append(rule)
                continue
            self._error(line, "Unexpected flow syntax")

        if not name:
            raise FlowSyntaxError("Missing flow header")
        if not version:
            raise FlowSyntaxError("Missing version header")
        if side is None:
            raise FlowSyntaxError("Missing side header")
        if side is not Color.WHITE:
            raise FlowSyntaxError(
                "Version 0.1 currently supports white-side flows only"
            )
        self._validate(flags, conditions, rules)
        return FlowDefinition(
            name, version, side, frozenset(flags), conditions, tuple(rules)
        )

    def _parse_flags(self, lines: list[_Line], index: int, flags: set[str]) -> int:
        while index < len(lines):
            line = lines[index]
            if line.text == "}":
                return index + 1
            if line.indent == 0:
                return index
            for flag in re.split(r"[\s,]+", line.text):
                if flag:
                    if flag in flags:
                        self._error(line, f"Duplicate flag: {flag!r}")
                    flags.add(flag)
            index += 1
        return index

    def _parse_conditions(
        self, lines: list[_Line], index: int, conditions: dict[str, Expression]
    ) -> int:
        while index < len(lines):
            line = lines[index]
            if line.text == "}":
                return index + 1
            if line.indent == 0:
                return index
            if "=" not in line.text:
                self._error(line, "Condition must use 'name = expression'")
            name, first = (part.strip() for part in line.text.split("=", maxsplit=1))
            if name in conditions:
                self._error(line, f"Duplicate condition: {name!r}")
            expression_parts = [first] if first else []
            index += 1
            while index < len(lines):
                continuation = lines[index]
                if continuation.text == "}" or continuation.indent <= line.indent:
                    break
                expression_parts.append(continuation.text)
                index += 1
            try:
                conditions[name] = parse_expression(" ".join(expression_parts))
            except ValueError as exc:
                self._error(line, f"Invalid condition {name!r}: {exc}")
        return index

    def _parse_rule(
        self, lines: list[_Line], index: int, owner: str, source_order: int
    ) -> tuple[RuleDefinition, int]:
        line = lines[index]
        rule_indent = line.indent
        action = self._parse_action(owner, line.text[:-1], line)
        values: dict[str, str] = {}
        index += 1
        while index < len(lines):
            field = lines[index]
            if field.indent <= rule_indent or field.text == "}":
                break
            if ":" not in field.text:
                self._error(field, "Rule field must use 'name: value'")
            key, value = (part.strip() for part in field.text.split(":", maxsplit=1))
            if key not in {"when", "until", "if", "set", "why", "terminal"}:
                self._error(field, f"Unknown rule field: {key!r}")
            if key in values:
                self._error(field, f"Duplicate rule field: {key!r}")
            index += 1
            continuation = [value] if value else []
            while index < len(lines) and lines[index].indent > field.indent:
                continuation.append(lines[index].text)
                index += 1
            values[key] = " ".join(continuation)

        def expression(key: str) -> Expression | None:
            value = values.get(key)
            if value is None:
                return None
            try:
                return parse_expression(value)
            except ValueError as exc:
                self._error(line, f"Invalid {key!r} expression: {exc}")

        set_flags = tuple(
            part for part in re.split(r"[\s,]+", values.get("set", "")) if part
        )
        return (
            RuleDefinition(
                action=action,
                when=expression("when"),
                until=expression("until"),
                if_condition=expression("if"),
                set_flags=set_flags,
                why=values.get("why") or None,
                terminal=values.get("terminal") or None,
                source_order=source_order,
            ),
            index,
        )

    def _parse_action(self, owner: str, value: str, line: _Line) -> Action:
        parts = value.strip().split(".")
        if len(parts) != 2:
            self._error(line, "Rule name must be '<action>.<target>'")
        try:
            kind = ActionKind.parse(parts[0])
            if kind is ActionKind.CASTLE:
                return Action(owner, kind, castle_side=CastleSide.parse(parts[1]))
            return Action(
                owner, kind, target_square=chess.parse_square(parts[1].lower())
            )
        except ValueError as exc:
            self._error(line, str(exc))

    def _validate(
        self,
        flags: set[str],
        conditions: dict[str, Expression],
        rules: list[RuleDefinition],
    ) -> None:
        keys: set[str] = set()
        for rule in rules:
            key = rule.action.canonical_key
            if key in keys:
                raise FlowSyntaxError(f"Duplicate rule action: {key}")
            keys.add(key)
            unknown = set(rule.set_flags) - flags
            if unknown:
                raise FlowSyntaxError(
                    f"Rule {key} sets undeclared flags: {sorted(unknown)}"
                )
        overlap = flags & conditions.keys()
        if overlap:
            raise FlowSyntaxError(
                f"Names cannot be both flags and conditions: {sorted(overlap)}"
            )
        allowed_names = flags | conditions.keys() | {"true", "false", "open"}
        for name, condition_expression in conditions.items():
            self._validate_expression(
                condition_expression, allowed_names, keys, f"condition {name!r}"
            )
        for rule in rules:
            for field_name, rule_expression in (
                ("when", rule.when),
                ("until", rule.until),
                ("if", rule.if_condition),
            ):
                if rule_expression is not None:
                    self._validate_expression(
                        rule_expression,
                        allowed_names,
                        keys,
                        f"{field_name} on {rule.action.canonical_key}",
                    )

    def _validate_expression(
        self,
        expression: Expression,
        allowed_names: set[str],
        rule_keys: set[str],
        location: str,
    ) -> None:
        if isinstance(expression, Name):
            if expression.value not in allowed_names:
                raise FlowSyntaxError(
                    f"Unknown condition or flag {expression.value!r} in {location}"
                )
            return
        if isinstance(expression, Not):
            self._validate_expression(
                expression.operand, allowed_names, rule_keys, location
            )
            return
        if isinstance(expression, BooleanOperation):
            self._validate_expression(
                expression.left, allowed_names, rule_keys, location
            )
            self._validate_expression(
                expression.right, allowed_names, rule_keys, location
            )
            return
        if not isinstance(expression, Call):
            raise FlowSyntaxError(f"Unsupported expression in {location}")
        contextual_arities: dict[str, set[int]] = {
            "at": {1, 2},
            "moved": {0},
            "developed": {0},
            "unmoved": {1},
            "captured": {1},
            "controls": {1},
            "attacked": {0, 1, 2},
            "defended": {0, 1, 2},
            "played": {1},
            "canmoveto": {1},
            "cancaptureon": {1},
            "flag": {1},
        }
        call_parts = expression.name.lower().rsplit(".", maxsplit=1)
        receiver = call_parts[0] if len(call_parts) == 2 else None
        predicate = call_parts[-1]
        if receiver is None:
            arities = contextual_arities
        elif receiver.startswith("square."):
            arities = {"has": {1}, "empty": {0}}
            try:
                chess.parse_square(receiver.removeprefix("square."))
            except ValueError as exc:
                raise FlowSyntaxError(
                    f"Invalid square receiver {receiver!r} in {location}"
                ) from exc
        else:
            arities = {
                "moved": {0},
                "developed": {0},
                "controls": {1},
                "attacked": {0},
                "defended": {0},
                "canmoveto": {1},
                "cancaptureon": {1},
            }
        if predicate not in arities:
            raise FlowSyntaxError(
                f"Unknown predicate {expression.name}() in {location}"
            )
        if len(expression.arguments) not in arities[predicate]:
            expected = sorted(arities[predicate])
            raise FlowSyntaxError(
                f"{expression.name}() has {len(expression.arguments)} arguments in {location}; "
                f"expected one of {expected}"
            )
        if any(not isinstance(argument, Name) for argument in expression.arguments):
            raise FlowSyntaxError(f"Predicate arguments must be names in {location}")
        arguments = [
            argument.value
            for argument in expression.arguments
            if isinstance(argument, Name)
        ]
        if predicate == "played" and arguments[0] not in rule_keys:
            raise FlowSyntaxError(
                f"Unknown rule reference {arguments[0]!r} in {location}"
            )
        if predicate == "flag" and arguments[0] not in allowed_names:
            raise FlowSyntaxError(f"Unknown flag {arguments[0]!r} in {location}")

    @staticmethod
    def _header_value(text: str, name: str) -> str | None:
        match = re.fullmatch(rf"{name}(?::|\s+)\s*(.+)", text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _lines(source: str) -> list[_Line]:
        result: list[_Line] = []
        for number, raw in enumerate(textwrap.dedent(source).splitlines(), start=1):
            without_comment = raw.split("#", maxsplit=1)[0].rstrip()
            if not without_comment.strip():
                continue
            expanded = without_comment.expandtabs(4)
            indent = len(expanded) - len(expanded.lstrip())
            result.append(_Line(number, indent, expanded.strip()))
        return result

    @staticmethod
    def _error(line: _Line, message: str) -> Never:
        raise FlowSyntaxError(f"Line {line.number}: {message}: {line.text!r}")


def parse_flow(source: str) -> FlowDefinition:
    return FlowParser().parse(source)
