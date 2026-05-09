"""
Command-spec parser for module-first CLI commands.
"""

from __future__ import annotations

from enum import Enum
import inspect
import types
from typing import Any, Literal, Union, get_args, get_origin

from registers.cli.registry import ArgumentEntry, CommandEntry, MISSING
from registers.cli.types import CliTypeError


class ParseError(ValueError):
    """Raised when command arguments cannot be parsed."""


def parse_command_args(
    entry: CommandEntry,
    tokens: list[str],
    *,
    allow_missing_prompts: bool = False,
) -> dict[str, Any]:
    """Parse raw CLI tokens (after command token) into handler kwargs."""

    named_flags = _named_argument_flags(entry.arguments)
    positional_pool = [arg for arg in entry.arguments if not _is_bool_annotation(arg.type)]

    values: dict[str, Any] = {}

    def set_value(arg: ArgumentEntry, value: Any, *, source: str) -> None:
        existing = values.get(arg.name, MISSING)
        if existing is not MISSING:
            if existing != value:
                raise ParseError(
                    f"Argument '{arg.name}' was provided multiple times with different values."
                )
            return

        values[arg.name] = value

    pos_index = 0
    idx = 0

    while idx < len(tokens):
        token = tokens[idx]

        if token in named_flags:
            arg = named_flags[token]

            if _is_bool_annotation(arg.type):
                set_value(arg, True, source=token)
                idx += 1
                continue

            idx += 1
            if idx >= len(tokens):
                raise ParseError(f"Missing value for option '{token}'.")

            raw_value = tokens[idx]
            if raw_value in named_flags:
                raise ParseError(f"Missing value for option '{token}'.")

            coerced = _coerce_value(raw_value, arg.type, arg.name)
            set_value(arg, coerced, source=token)
            idx += 1
            continue

        if token.startswith("--"):
            raise ParseError(f"Unknown option '{token}'.")

        while pos_index < len(positional_pool) and positional_pool[pos_index].name in values:
            pos_index += 1

        if pos_index >= len(positional_pool):
            raise ParseError(f"Unexpected argument '{token}'.")

        target = positional_pool[pos_index]
        coerced = _coerce_value(token, target.type, target.name)
        set_value(target, coerced, source="positional")
        pos_index += 1
        idx += 1

    for arg in entry.arguments:
        if arg.name in values:
            continue

        if arg.default is not MISSING:
            values[arg.name] = arg.default
            continue

        if _is_bool_annotation(arg.type):
            values[arg.name] = False
            continue

        if not arg.required:
            values[arg.name] = None
            continue

        if allow_missing_prompts and arg.prompt:
            continue

        raise ParseError(f"Missing required argument '{arg.name}'.")

    return values


def render_command_usage(entry: CommandEntry, program_name: str | None = None) -> str:
    """Render a compact usage string for parse failures."""

    parts: list[str] = []
    for arg in entry.arguments:
        flag = f"--{arg.name.replace('_', '-')}"
        if _is_bool_annotation(arg.type):
            parts.append(f"[{flag}]")
            continue

        if arg.required:
            parts.append(f"<{arg.name}>")
            continue

        parts.append(f"[<{arg.name}> | {flag} VALUE]")

    suffix = " ".join(parts)
    command_label = f"{program_name} {entry.name}".strip() if program_name else entry.name
    if suffix:
        return f"usage: {command_label} {suffix}"
    return f"usage: {command_label}"


def _named_argument_flags(arguments: tuple[ArgumentEntry, ...]) -> dict[str, ArgumentEntry]:
    flags: dict[str, ArgumentEntry] = {}
    for arg in arguments:
        dashed = arg.name.replace("_", "-")
        tokens = [f"--{arg.name}", f"--{dashed}"]
        for token in tokens:
            flags[token] = arg
    return flags


def named_argument_flags(arguments: tuple[ArgumentEntry, ...]) -> dict[str, ArgumentEntry]:
    """Public helper for registry runtime option conflict checks."""
    return _named_argument_flags(arguments)


def coerce_value(raw: str, annotation: Any, arg_name: str) -> Any:
    """Public helper for context/prompt parsing."""
    return _coerce_value(raw, annotation, arg_name)


def _coerce_value(raw: str, annotation: Any, arg_name: str) -> Any:
    target = _unwrap_optional(annotation)
    if isinstance(target, str):
        target = {"str": str, "int": int, "float": float, "bool": bool}.get(target, str)
    parser = getattr(target, "parse", None)
    if callable(parser):
        try:
            return parser(raw)
        except CliTypeError as exc:
            raise ParseError(f"Invalid value for '{arg_name}'. {exc}") from exc

    if target in (Any, inspect.Parameter.empty):
        return raw

    origin = get_origin(target)
    if origin is Literal:
        choices = get_args(target)
        for choice in choices:
            if raw == str(choice):
                return choice
        allowed = ", ".join(repr(choice) for choice in choices)
        raise ParseError(f"Invalid value for '{arg_name}'. Allowed values: {allowed}.")

    if inspect.isclass(target) and issubclass(target, Enum):
        try:
            return target(raw)
        except ValueError:
            try:
                return target[raw]
            except KeyError as exc:
                allowed = ", ".join(member.value for member in target)  # type: ignore[arg-type]
                raise ParseError(
                    f"Invalid value for '{arg_name}'. Allowed values: {allowed}."
                ) from exc

    if target is str:
        return raw

    if target is bool:
        lowered = raw.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ParseError(f"Invalid boolean value for '{arg_name}': {raw!r}.")

    try:
        return target(raw)
    except Exception as exc:
        raise ParseError(f"Invalid value for '{arg_name}': {raw!r}.") from exc


def _is_bool_annotation(annotation: Any) -> bool:
    target = _unwrap_optional(annotation)
    return target is bool


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation
