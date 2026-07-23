from __future__ import annotations

from dataclasses import dataclass
import re


class ExpressionSyntaxError(ValueError):
    pass


class Expression:
    pass


@dataclass(frozen=True, slots=True)
class Name(Expression):
    value: str


@dataclass(frozen=True, slots=True)
class Call(Expression):
    name: str
    arguments: tuple[Expression, ...]


@dataclass(frozen=True, slots=True)
class Not(Expression):
    operand: Expression


@dataclass(frozen=True, slots=True)
class BooleanOperation(Expression):
    operator: str
    left: Expression
    right: Expression


_TOKEN = re.compile(r"\s*(?:(\&\&|\|\||[!(),])|([A-Za-z][A-Za-z0-9_.-]*))")


def _tokenize(source: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(source):
        match = _TOKEN.match(source, position)
        if match is None:
            raise ExpressionSyntaxError(
                f"Unexpected expression text at column {position + 1}: {source[position:]!r}"
            )
        tokens.append(match.group(1) or match.group(2))
        position = match.end()
    return tokens


class _ExpressionParser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = _tokenize(source)
        self.position = 0

    def parse(self) -> Expression:
        if not self.tokens:
            raise ExpressionSyntaxError("Expression cannot be empty")
        expression = self._or()
        if self._peek() is not None:
            raise ExpressionSyntaxError(f"Unexpected token: {self._peek()!r}")
        return expression

    def _or(self) -> Expression:
        result = self._and()
        while self._peek() == "||":
            self._take()
            result = BooleanOperation("||", result, self._and())
        return result

    def _and(self) -> Expression:
        result = self._unary()
        while self._peek() == "&&":
            self._take()
            result = BooleanOperation("&&", result, self._unary())
        return result

    def _unary(self) -> Expression:
        if self._peek() == "!":
            self._take()
            return Not(self._unary())
        return self._primary()

    def _primary(self) -> Expression:
        token = self._take()
        if token == "(":
            result = self._or()
            self._expect(")")
            return result
        if token in {None, ")", ",", "&&", "||"}:
            raise ExpressionSyntaxError(f"Expected a name, got {token!r}")
        if self._peek() != "(":
            return Name(token)
        self._take()
        arguments: list[Expression] = []
        if self._peek() != ")":
            while True:
                arguments.append(self._or())
                if self._peek() != ",":
                    break
                self._take()
        self._expect(")")
        return Call(token, tuple(arguments))

    def _peek(self) -> str | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def _take(self) -> str | None:
        token = self._peek()
        if token is not None:
            self.position += 1
        return token

    def _expect(self, expected: str) -> None:
        actual = self._take()
        if actual != expected:
            raise ExpressionSyntaxError(f"Expected {expected!r}, got {actual!r}")


def parse_expression(source: str) -> Expression:
    return _ExpressionParser(source).parse()
