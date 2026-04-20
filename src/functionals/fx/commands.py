"""
Public FX command surface.

This module owns the FX command registry and runtime entrypoints. Command
implementations are split into plugin modules under ``functionals.fx.plugins``.
"""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version as resolve_distribution_version
from threading import Lock
from typing import Any

from functionals.cli.plugins import load_plugins
from functionals.cli.registry import CommandRegistry, MISSING

_registry = CommandRegistry()
_FX_DISTRIBUTION_NAME = "decorates"
_PLUGINS_PACKAGE = "functionals.fx.plugins"
_REQUIRED_COMMANDS = frozenset(
    {
        "init",
        "status",
        "module",
        "plugin",
        "version",
        "cron",
        "run",
        "install",
        "update",
        "pull",
        "health",
        "history",
    }
)
_plugins_lock = Lock()
_plugins_loaded = False
_plugin_load_error: Exception | None = None


def _resolve_fx_version() -> str:
    try:
        return resolve_distribution_version(_FX_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "dev"


FX_VERSION = _resolve_fx_version()


def argument(
    name: str,
    *,
    type: Any = str,
    help: str = "",
    default: Any = MISSING,
):
    def decorator(fn):
        _registry.stage_argument(fn, name, arg_type=type, help_text=help, default=default)
        return fn

    return decorator


def option(flag: str, *, help: str = ""):
    def decorator(fn):
        _registry.stage_option(fn, flag, help_text=help)
        return fn

    return decorator


def register(name: str | None = None, *, description: str = "", help: str = ""):
    def decorator(fn):
        _registry.finalize_command(fn, name=name, description=description, help_text=help)
        return fn

    return decorator


def ensure_plugins_loaded() -> None:
    global _plugins_loaded, _plugin_load_error

    if _plugins_loaded:
        return
    if _plugin_load_error is not None:
        raise RuntimeError("FX command plugins failed to load.") from _plugin_load_error

    with _plugins_lock:
        if _plugins_loaded:
            return
        if _plugin_load_error is not None:
            raise RuntimeError("FX command plugins failed to load.") from _plugin_load_error

        try:
            load_plugins(_PLUGINS_PACKAGE, _registry)
            missing = sorted(name for name in _REQUIRED_COMMANDS if not _registry.has(name))
            if missing:
                raise RuntimeError(
                    "FX command plugins loaded incompletely. Missing commands: "
                    + ", ".join(missing)
                )
            _plugins_loaded = True
        except Exception as exc:
            _plugin_load_error = exc
            raise


def run(
    argv: Sequence[str] | None = None,
    *,
    print_result: bool = True,
    shell_prompt: str = "fx > ",
    shell_input_fn=None,
    shell_banner: bool = True,
    shell_banner_text: str | None = None,
    shell_title: str = "Functionals FX",
    shell_description: str = "Manage Functionals projects, modules, and plugin structures.",
    shell_colors: bool | None = None,
    shell_usage: bool = True,
) -> Any:
    ensure_plugins_loaded()
    return _registry.run(
        argv,
        print_result=print_result,
        shell_prompt=shell_prompt,
        shell_input_fn=shell_input_fn,
        shell_banner=shell_banner,
        shell_banner_text=shell_banner_text,
        shell_title=shell_title,
        shell_description=shell_description,
        shell_version=f"Version: {FX_VERSION}",
        shell_colors=shell_colors,
        shell_usage=shell_usage,
    )


def get_registry() -> CommandRegistry:
    ensure_plugins_loaded()
    return _registry


def main(argv: Sequence[str] | None = None) -> int:
    run(argv)
    return 0


__all__ = [
    "FX_VERSION",
    "argument",
    "option",
    "register",
    "ensure_plugins_loaded",
    "run",
    "get_registry",
    "main",
]
