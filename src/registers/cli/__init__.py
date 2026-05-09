"""
Decorator-driven CLI tooling.

Public, ergonomic entrypoints are module-level decorators and helpers:

    import registers.cli as cli

    @cli.register(description="Say hello")
    @cli.argument("name")
    @cli.option("--hello")
    def hello(name: str) -> str:
        return f"Hello, {name}!"

    if __name__ == "__main__":
        cli.run()

Instance-mode is also supported for isolated command scopes:

    registry = cli.CommandRegistry()

    @registry.register(description="Say hello")
    @registry.argument("name")
    def hello(name: str) -> str:
        return f"Hello, {name}!"

    if __name__ == "__main__":
        registry.run()
"""

from registers.cli.container import DIContainer
from registers.cli.decorators import (
    argument,
    confirm,
    context_factory,
    dry_run,
    group,
    get_registry,
    list_commands,
    option,
    alias,
    progress,
    register,
    reset_registry,
    run,
    run_async,
    run_shell,
    spinner,
)
from registers.cli.dispatcher import Dispatcher
from registers.cli.exceptions import (
    CommandExecutionError,
    DependencyNotFoundError,
    DuplicateCommandError,
    RegistrationError,
    PluginLoadError,
    UnknownCommandError,
)
from registers.cli.middleware import (
    MiddlewareChain,
    logging_middleware_post,
    logging_middleware_pre,
)
from registers.cli.parser import ParseError, parse_command_args
from registers.cli.plugins import load_plugins
from registers.cli.registry import ArgumentEntry, CommandEntry, CommandRegistry, MISSING
from registers.cli.ux import Context, Progress, Theme, console, style
from registers.cli import types

__all__ = [
    # Module-level command API
    "register",
    "argument",
    "option",
    "alias",
    "group",
    "spinner",
    "progress",
    "confirm",
    "dry_run",
    "context_factory",
    "run",
    "run_async",
    "run_shell",
    "list_commands",
    "get_registry",
    "reset_registry",

    # Internal / advanced surfaces
    "CommandRegistry",
    "CommandEntry",
    "ArgumentEntry",
    "MISSING",
    "Theme",
    "Context",
    "console",
    "style",
    "Progress",
    "types",
    "parse_command_args",
    "ParseError",

    # Legacy advanced runtime components
    "DIContainer",
    "Dispatcher",
    "MiddlewareChain",
    "load_plugins",
    "logging_middleware_pre",
    "logging_middleware_post",

    # Exceptions
    "CommandExecutionError",
    "DependencyNotFoundError",
    "DuplicateCommandError",
    "RegistrationError",
    "PluginLoadError",
    "UnknownCommandError",
]
