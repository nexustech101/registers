"""Optional presentation and runtime helpers for :mod:`registers.cli`."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from dataclasses import dataclass
import asyncio
import csv
import io
import json
import logging
import sys
from typing import Any, Awaitable


@dataclass(frozen=True)
class Theme:
    primary: str = "bold cyan"
    success: str = "bold green"
    warning: str = "bold yellow"
    error: str = "bold red"
    tag: str = "bold magenta"
    panel_border: str = "cyan"


DEFAULT_THEME = Theme()


class Context:
    """Base class for CLI context objects."""


class _StyleProxy:
    primary = DEFAULT_THEME.primary
    success = DEFAULT_THEME.success
    warning = DEFAULT_THEME.warning
    error = DEFAULT_THEME.error
    tag = DEFAULT_THEME.tag


style = _StyleProxy()


class _FallbackStatus:
    def __init__(self, message: str) -> None:
        self.message = message

    def __enter__(self) -> "_FallbackStatus":
        if self.message:
            print(self.message)
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def update(self, message: str) -> None:
        if message:
            print(message)


class _FallbackProgress:
    def __enter__(self) -> "_FallbackProgress":
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def add_task(self, _description: str, total: int | None = None) -> int:
        return 0

    def advance(self, _task_id: int, advance: int = 1) -> None:
        return None


class _LazyConsole:
    def _rich_console(self, **kwargs: Any) -> Any | None:
        try:
            from rich.console import Console
        except Exception:
            return None
        return Console(**kwargs)

    def print(self, *objects: Any, **kwargs: Any) -> None:
        rich_console = self._rich_console()
        if rich_console is not None:
            rich_console.print(*objects, **kwargs)
            return
        print(*objects)

    def status(self, message: str, **kwargs: Any) -> Any:
        rich_console = self._rich_console()
        if rich_console is not None:
            return rich_console.status(message, **kwargs)
        return _FallbackStatus(message)


console = _LazyConsole()


class Progress:
    """Lazy Rich Progress wrapper with a no-op fallback."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._args = args
        self._kwargs = kwargs
        self._impl: Any | None = None

    def __enter__(self) -> Any:
        try:
            from rich.progress import Progress as RichProgress
        except Exception:
            self._impl = _FallbackProgress()
        else:
            self._impl = RichProgress(*self._args, **self._kwargs)
        return self._impl.__enter__()

    def __exit__(self, *exc: Any) -> Any:
        if self._impl is None:
            return None
        return self._impl.__exit__(*exc)


def has_rich() -> bool:
    try:
        import rich  # noqa: F401
    except Exception:
        return False
    return True


def print_result(result: Any, *, output: str | None, rich: bool, render: bool = True) -> None:
    if result is None:
        return

    mode = output or ("rich" if rich else "plain")
    text = format_result(result, mode=mode, render=render)
    if text is None:
        return

    if mode == "rich" and has_rich():
        rich_console = _LazyConsole()._rich_console()
        if rich_console is not None:
            rich_console.print(text)
            return
    print(text)


def format_result(result: Any, *, mode: str = "plain", render: bool = True) -> str | Any | None:
    if result is None:
        return None
    if not render or mode == "plain":
        return str(result)
    if mode == "json":
        return json.dumps(result, indent=2, sort_keys=True, default=str)
    if mode == "csv":
        return _to_csv(result)
    if mode == "rich" and has_rich():
        rendered = _to_rich_renderable(result)
        if rendered is not None:
            return rendered
    return _to_plain_structured(result)


def format_error(title: str, message: str, *, rich: bool = False) -> str:
    if rich and has_rich():
        try:
            from rich.panel import Panel
            from rich.text import Text
        except Exception:
            pass
        else:
            rich_console = _LazyConsole()._rich_console(stderr=False)
            buffer = io.StringIO()
            rich_console.file = buffer
            rich_console.print(Panel(Text(message), title=title, border_style="red"))
            return buffer.getvalue().rstrip()
    return f"Error: {message}" if title.lower() != "error" else f"Error: {message}"


def run_awaitable(awaitable: Awaitable[Any], *, event_loop: Any | None = None) -> Any:
    if event_loop is not None:
        return event_loop.run_until_complete(awaitable)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("run() cannot execute an async command while an event loop is already running; use run_async().")


async def await_if_needed(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, Awaitable):
        return await value
    return value


@contextmanager
def capture_logs(enabled: bool, *, level: str | int | None = None) -> Any:
    if not enabled:
        yield ""
        return

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    old_level = root.level
    if level is not None:
        root.setLevel(level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO))
    root.addHandler(handler)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _to_csv(result: Any) -> str:
    rows: list[dict[str, Any]]
    if isinstance(result, list) and all(isinstance(item, dict) for item in result):
        rows = result
    elif isinstance(result, dict):
        rows = [result]
    else:
        return str(result)
    if not rows:
        return ""
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().rstrip("\r\n")


def _to_plain_structured(result: Any) -> str:
    if isinstance(result, dict):
        return "\n".join(f"{key}: {value}" for key, value in result.items())
    if isinstance(result, list):
        if all(isinstance(item, dict) for item in result):
            return _plain_table(result)
        return "\n".join(f"- {item}" for item in result)
    return str(result)


def _plain_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    headers = list(dict.fromkeys(key for row in rows for key in row))
    widths = {
        header: max(len(str(header)), *(len(str(row.get(header, ""))) for row in rows))
        for header in headers
    }
    lines = ["  ".join(str(header).ljust(widths[header]) for header in headers)]
    lines.append("  ".join("-" * widths[header] for header in headers))
    for row in rows:
        lines.append("  ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers))
    return "\n".join(lines)


def _to_rich_renderable(result: Any) -> Any | None:
    if hasattr(result, "__rich_console__"):
        return result
    try:
        from rich.table import Table
        from rich.panel import Panel
        from rich.syntax import Syntax
    except Exception:
        return None

    if isinstance(result, dict):
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        for key, value in result.items():
            table.add_row(str(key), str(value))
        return table
    if isinstance(result, list) and all(isinstance(item, dict) for item in result):
        table = Table()
        headers = list(dict.fromkeys(key for row in result for key in row))
        for header in headers:
            table.add_column(str(header))
        for row in result:
            table.add_row(*(str(row.get(header, "")) for header in headers))
        return table
    if isinstance(result, (list, tuple)):
        return "\n".join(f"- {item}" for item in result)
    if isinstance(result, str) and result.lstrip().startswith(("{", "[")):
        return Syntax(result, "json")
    return Panel(str(result), title="Result")
