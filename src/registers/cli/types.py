"""Extended argument type helpers for :mod:`registers.cli`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum as PyEnum
import json
from pathlib import Path as _Path
from typing import Any, Callable


class CliTypeError(ValueError):
    """Raised when an extended CLI type cannot parse a raw value."""


class CliType:
    """Base protocol-ish class for parser-friendly extended types."""

    label = "value"

    def parse(self, raw: str) -> Any:
        raise NotImplementedError

    def describe(self) -> str:
        return self.label


@dataclass(frozen=True)
class Choice(CliType):
    choices: list[Any]

    def __init__(self, choices: list[Any] | tuple[Any, ...]) -> None:
        object.__setattr__(self, "choices", list(choices))

    def parse(self, raw: str) -> Any:
        for choice in self.choices:
            if raw == str(choice):
                return choice
        allowed = ", ".join(repr(choice) for choice in self.choices)
        raise CliTypeError(f"Allowed values: {allowed}.")

    def describe(self) -> str:
        return "choice[" + "|".join(str(choice) for choice in self.choices) + "]"


@dataclass(frozen=True)
class Int(CliType):
    min: int | None = None
    max: int | None = None

    def parse(self, raw: str) -> int:
        try:
            value = int(raw)
        except ValueError as exc:
            raise CliTypeError(f"Expected integer, got {raw!r}.") from exc
        _validate_bounds(value, self.min, self.max)
        return value

    def describe(self) -> str:
        return _bounded_label("int", self.min, self.max)


@dataclass(frozen=True)
class Float(CliType):
    min: float | None = None
    max: float | None = None

    def parse(self, raw: str) -> float:
        try:
            value = float(raw)
        except ValueError as exc:
            raise CliTypeError(f"Expected float, got {raw!r}.") from exc
        _validate_bounds(value, self.min, self.max)
        return value

    def describe(self) -> str:
        return _bounded_label("float", self.min, self.max)


@dataclass(frozen=True)
class Path(CliType):
    exists: bool = False
    readable: bool = False
    writable: bool = False

    def parse(self, raw: str) -> _Path:
        value = _Path(raw)
        if self.exists and not value.exists():
            raise CliTypeError(f"Path does not exist: {raw!r}.")
        if self.readable and value.exists() and not value.is_file() and not value.is_dir():
            raise CliTypeError(f"Path is not readable: {raw!r}.")
        if self.writable:
            target = value if value.exists() and value.is_dir() else value.parent
            if not target.exists():
                raise CliTypeError(f"Parent path does not exist: {str(target)!r}.")
        return value

    def describe(self) -> str:
        checks = []
        if self.exists:
            checks.append("exists")
        if self.readable:
            checks.append("readable")
        if self.writable:
            checks.append("writable")
        return "path" if not checks else f"path[{','.join(checks)}]"


@dataclass(frozen=True)
class Date(CliType):
    fmt: str = "%Y-%m-%d"

    def parse(self, raw: str) -> date:
        try:
            return datetime.strptime(raw, self.fmt).date()
        except ValueError as exc:
            raise CliTypeError(f"Expected date matching {self.fmt!r}, got {raw!r}.") from exc

    def describe(self) -> str:
        return f"date[{self.fmt}]"


@dataclass(frozen=True)
class List(CliType):
    item_type: Any = str
    separator: str = ","

    def parse(self, raw: str) -> list[Any]:
        if raw == "":
            return []
        parser = _coercer(self.item_type)
        return [parser(part.strip()) for part in raw.split(self.separator)]

    def describe(self) -> str:
        label = getattr(self.item_type, "__name__", str(self.item_type))
        return f"list[{label}]"


class _JSON(CliType):
    def parse(self, raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CliTypeError(f"Invalid JSON: {exc.msg}.") from exc

    def describe(self) -> str:
        return "json"


JSON = _JSON()


@dataclass(frozen=True)
class Enum(CliType):
    enum_type: type[PyEnum]

    def parse(self, raw: str) -> PyEnum:
        try:
            return self.enum_type(raw)
        except ValueError:
            try:
                return self.enum_type[raw]
            except KeyError as exc:
                allowed = ", ".join(str(member.value) for member in self.enum_type)
                raise CliTypeError(f"Allowed values: {allowed}.") from exc

    def describe(self) -> str:
        return self.enum_type.__name__


def _validate_bounds(value: Any, lower: Any | None, upper: Any | None) -> None:
    if lower is not None and value < lower:
        raise CliTypeError(f"Value must be >= {lower}.")
    if upper is not None and value > upper:
        raise CliTypeError(f"Value must be <= {upper}.")


def _bounded_label(label: str, lower: Any | None, upper: Any | None) -> str:
    pieces = []
    if lower is not None:
        pieces.append(f"min={lower}")
    if upper is not None:
        pieces.append(f"max={upper}")
    return label if not pieces else f"{label}[{', '.join(pieces)}]"


def _coercer(target: Any) -> Callable[[str], Any]:
    parser = getattr(target, "parse", None)
    if callable(parser):
        return parser
    return target
