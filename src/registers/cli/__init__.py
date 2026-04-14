"""
A lightweight, registers-based CLI framework.

Public API surface::

    from registers.cli import (
        CommandRegistry,
        DIContainer,
        MiddlewareChain,
        Dispatcher,
        build_parser,
        load_plugins,
        logging_middleware_pre,
        logging_middleware_post,
    )
"""

from registers.cli.dispatcher import Dispatcher
from registers.cli.middleware import (
    MiddlewareChain,
    logging_middleware_post,
    logging_middleware_pre,
)
from registers.cli.parser import build_parser
from registers.cli.container import DIContainer
from registers.cli.exceptions import (
    DependencyNotFoundError,
    DuplicateCommandError,
    FrameworkError,
    PluginLoadError,
    UnknownCommandError,
)
from registers.cli.registry import CommandRegistry
from registers.cli.plugins import load_plugins

__all__ = [
    # Core framework
    "CommandRegistry",
    "DIContainer",
    "Dispatcher",
    "MiddlewareChain",
    "build_parser",
    "load_plugins",
    "logging_middleware_pre",
    "logging_middleware_post",

    # Exceptions
    "DependencyNotFoundError",
    "DuplicateCommandError",
    "FrameworkError",
    "PluginLoadError",
    "UnknownCommandError",
]
