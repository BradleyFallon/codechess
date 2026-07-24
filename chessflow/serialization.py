from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from typing import TypeAlias


JsonData: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonData"]
    | dict[str, "JsonData"]
)


def to_json_data(value: object) -> JsonData:
    """Convert domain dataclasses and enums to explicit JSON-safe data."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return to_json_data(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_json_data(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [to_json_data(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {
            key: to_json_data(item) for key, item in value.items()
        }
    raise TypeError(
        f"Unsupported JSON value: {type(value).__name__}"
    )
