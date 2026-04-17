"""
Internal command registry for the module-level CLI decorators.

The public DX entrypoints live in ``functionals.cli.decorators``. This module
stores command specs and executes commands from those specs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
import inspect
import logging
from pathlib import Path
import sys
from collections.abc import Callable
from typing import Any, Sequence, get_args, get_origin

from functionals.cli.exceptions import CommandExecutionError, DuplicateCommandError, FrameworkError, UnknownCommandError
from functionals.cli.utils.reflection import get_params
from functionals.cli.utils.typing import is_bool_flag, is_optional

logger = logging.getLogger(__name__)
HELP_COMMAND_NAME = "help"
HELP_ALIASES = ("help", "--help", "-h")
HELP_RESERVED = frozenset({"help", "h"})
INTERACTIVE_ALIASES = ("--interactive", "-i")
INTERACTIVE_RESERVED = frozenset({"interactive", "i"})


class _MissingType:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _MissingType()


@dataclass(frozen=True)
class ArgumentEntry:
    """Typed metadata for one command argument."""

    name: str
    type: Any = str
    help_text: str = ""
    required: bool = True
    default: Any = MISSING


@dataclass(frozen=True)
class CommandEntry:
    """All metadata needed to parse and execute a command."""

    name: str
    handler: Callable[..., Any]
    help_text: str = ""
    description: str = ""
    options: tuple[str, ...] = field(default_factory=tuple)
    arguments: tuple[ArgumentEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _StagedArgument:
    name: str
    arg_type: Any = str
    help_text: str = ""
    default: Any = MISSING


@dataclass(frozen=True)
class _StagedOption:
    flag: str
    help_text: str = ""


class CommandRegistry:
    """Internal state container for staged decorators and finalized commands."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandEntry] = {}
        self._aliases: dict[str, str] = {}
        self._pending_args: dict[Callable[..., Any], list[_StagedArgument]] = {}
        self._pending_options: dict[Callable[..., Any], list[_StagedOption]] = {}

    # ------------------------------------------------------------------
    # Decorator staging + finalization
    # ------------------------------------------------------------------

    def stage_argument(
        self,
        fn: Callable[..., Any],
        name: str,
        *,
        arg_type: Any = str,
        help_text: str = "",
        default: Any = MISSING,
    ) -> None:
        if not name:
            raise ValueError("argument() requires a non-empty argument name.")

        staged = self._pending_args.setdefault(fn, [])
        if any(item.name == name for item in staged):
            raise ValueError(f"Argument '{name}' was declared more than once for '{fn.__name__}'.")

        # Decorators execute bottom-up; prepend to preserve top-down source order.
        staged.insert(0, _StagedArgument(name=name, arg_type=arg_type, help_text=help_text, default=default))

    def stage_option(
        self,
        fn: Callable[..., Any],
        flag: str,
        *,
        help_text: str = "",
    ) -> None:
        if not flag or not flag.startswith("-"):
            raise ValueError("option() expects a CLI flag such as '-a' or '--add'.")

        staged = self._pending_options.setdefault(fn, [])
        if any(item.flag == flag for item in staged):
            raise ValueError(f"Option '{flag}' was declared more than once for '{fn.__name__}'.")

        # Decorators execute bottom-up; prepend to preserve top-down source order.
        staged.insert(0, _StagedOption(flag=flag, help_text=help_text))

    def finalize_command(
        self,
        fn: Callable[..., Any],
        *,
        name: str | None = None,
        description: str = "",
        help_text: str = "",
    ) -> None:
        staged_args = self._pending_args.pop(fn, [])
        staged_options = self._pending_options.pop(fn, [])

        options = tuple(item.flag for item in staged_options)
        command_name = (name or "").strip() or self._derive_command_name(options, fn.__name__)
        if not command_name:
            raise ValueError("register() could not determine a command name.")

        summary = description or help_text
        arguments = tuple(self._build_arguments(fn, staged_args))

        self._assert_command_slot_available(command_name)
        self._assert_options_available(command_name, options)

        entry = CommandEntry(
            name=command_name,
            handler=fn,
            help_text=summary,
            description=description,
            options=options,
            arguments=arguments,
        )

        self._commands[command_name] = entry
        for flag in options:
            normalized = self._normalize_alias(flag)
            if normalized:
                self._aliases[normalized] = command_name

    # ------------------------------------------------------------------
    # Lookup + runtime
    # ------------------------------------------------------------------

    def get(self, name: str) -> CommandEntry:
        if name in self._commands:
            return self._commands[name]

        normalized = self._normalize_alias(name)
        if normalized in self._aliases:
            return self._commands[self._aliases[normalized]]

        raise UnknownCommandError(name)

    def all(self) -> dict[str, CommandEntry]:
        return dict(self._commands)

    def has(self, name: str) -> bool:
        try:
            self.get(name)
            return True
        except UnknownCommandError:
            return False

    def list_commands(self) -> None:
        if not self._commands:
            print("No commands registered.")
            return

        print("Available commands:")
        for entry in self._commands.values():
            aliases = f" [{', '.join(entry.options)}]" if entry.options else ""
            summary = entry.help_text or entry.description or "(no description)"
            print(f"  {entry.name}{aliases}: {summary}")

    def print_help(self, command_name: str | None = None, *, program_name: str | None = None) -> None:
        """Print comprehensive CLI help for all commands or one specific command."""
        if command_name is None:
            print(self._render_global_help(program_name=program_name))
            return

        normalized = self._normalize_alias(command_name)
        if normalized in HELP_RESERVED:
            print(self._render_builtin_help_detail(HELP_COMMAND_NAME, program_name=program_name))
            return
        if normalized in INTERACTIVE_RESERVED:
            print(self._render_builtin_help_detail("interactive", program_name=program_name))
            return

        entry = self.get(command_name)
        print(self._render_command_help(entry, program_name=program_name))

    def run(
        self,
        argv: Sequence[str] | None = None,
        *,
        print_result: bool = True,
        shell_prompt: str = "> ",
        shell_input_fn: Callable[[str], str] | None = None,
        shell_banner: bool = True,
        shell_banner_text: str | None = None,
        shell_title: str = "Functionals CLI",
        shell_description: str = "Type 'help' for shell help and 'exit' to quit.",
        shell_colors: bool | None = None,
    ) -> Any:
        from functionals.cli.parser import ParseError, parse_command_args, render_command_usage

        program_name = Path(sys.argv[0]).name or "app.py"
        raw = list(sys.argv[1:] if argv is None else argv)
        if not raw:
            if self._stdin_is_interactive():
                return self.run_shell(
                    print_result=print_result,
                    prompt=shell_prompt,
                    program_name=program_name,
                    input_fn=shell_input_fn,
                    banner=shell_banner,
                    banner_text=shell_banner_text,
                    shell_title=shell_title,
                    shell_description=shell_description,
                    colors=shell_colors,
                )
            self.print_help(program_name=program_name)
            return None

        token = raw[0]
        if token in INTERACTIVE_ALIASES:
            if len(raw) > 1:
                print(f"Error: {token} does not take additional arguments.")
                raise SystemExit(2)
            return self.run_shell(
                print_result=print_result,
                prompt=shell_prompt,
                program_name=program_name,
                input_fn=shell_input_fn,
                banner=shell_banner,
                banner_text=shell_banner_text,
                shell_title=shell_title,
                shell_description=shell_description,
                colors=shell_colors,
            )

        if self._is_builtin_help_token(token):
            if len(raw) > 2:
                print("Error: help accepts at most one command name.")
                raise SystemExit(2)

            if len(raw) == 2:
                target = raw[1]
                try:
                    self.print_help(target, program_name=program_name)
                except UnknownCommandError:
                    suggestion = self.suggest(target)
                    if suggestion:
                        print(f"Did you mean '{suggestion}'?")
                    else:
                        print(f"Unknown command '{target}'.")
                    raise SystemExit(2)
            else:
                self.print_help(program_name=program_name)
            return None

        try:
            entry = self.get(token)
        except UnknownCommandError:
            suggestion = self.suggest(token)
            if suggestion:
                print(f"Did you mean '{suggestion}'?")
            else:
                print("Unknown command")
            raise SystemExit(2)

        try:
            kwargs = parse_command_args(entry, raw[1:])
        except ParseError as exc:
            print(f"Error: {exc}")
            print(render_command_usage(entry, program_name=program_name))
            raise SystemExit(2)

        try:
            result = entry.handler(**kwargs)
        except FrameworkError:
            raise
        except Exception as exc:
            logger.exception("Unhandled command failure in run() for '%s'.", entry.name)
            raise CommandExecutionError(entry.name, str(exc)) from exc

        if print_result and result is not None:
            print(result)

        return result

    def run_shell(
        self,
        *,
        print_result: bool = True,
        prompt: str = "> ",
        program_name: str | None = None,
        input_fn: Callable[[str], str] | None = None,
        banner: bool = True,
        banner_text: str | None = None,
        shell_title: str = "Functionals CLI",
        shell_description: str = "Type 'help' for shell help and 'exit' to quit.",
        colors: bool | None = None,
    ) -> None:
        """Run this registry in interactive REPL mode."""
        from functionals.cli.shell import InteractiveShell

        title = banner_text if banner_text is not None else shell_title
        shell = InteractiveShell(
            self,
            print_result=print_result,
            prompt=prompt,
            program_name=program_name,
            input_fn=input_fn,
            banner=banner,
            title=title,
            description=shell_description,
            colors=colors,
        )
        shell.run()
        return None

    def clear(self) -> None:
        self._commands.clear()
        self._aliases.clear()
        self._pending_args.clear()
        self._pending_options.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_alias(token: str) -> str:
        return token.lstrip("-").strip()

    def _assert_command_slot_available(self, command_name: str) -> None:
        if self._normalize_alias(command_name) in HELP_RESERVED:
            raise ValueError(
                "The command name 'help' is reserved for the built-in help command."
            )

        if command_name in self._commands:
            raise DuplicateCommandError(command_name)

        if command_name in self._aliases:
            raise DuplicateCommandError(command_name)

    def _assert_options_available(self, command_name: str, options: Sequence[str]) -> None:
        for flag in options:
            normalized = self._normalize_alias(flag)
            if not normalized:
                raise ValueError(f"Invalid option '{flag}'.")

            if normalized in HELP_RESERVED:
                raise ValueError(
                    f"Option '{flag}' is reserved for the built-in help command."
                )

            if normalized in INTERACTIVE_RESERVED:
                raise ValueError(
                    f"Option '{flag}' is reserved for interactive mode entry."
                )

            if normalized in self._commands and normalized != command_name:
                raise DuplicateCommandError(flag)

            existing = self._aliases.get(normalized)
            if existing is not None and existing != command_name:
                raise DuplicateCommandError(flag)

    @staticmethod
    def _derive_command_name(options: Sequence[str], fallback: str) -> str:
        for flag in options:
            if flag.startswith("--") and len(flag) > 2:
                return flag[2:]
        return fallback

    def _build_arguments(
        self,
        fn: Callable[..., Any],
        staged_args: Sequence[_StagedArgument],
    ) -> list[ArgumentEntry]:
        params = get_params(fn)
        params_by_name = {param.name: param for param in params}

        for staged in staged_args:
            if staged.name not in params_by_name:
                raise ValueError(
                    f"@argument('{staged.name}') does not match any parameter on '{fn.__name__}'."
                )

        explicit_by_name = {item.name: item for item in staged_args}
        ordered: list[ArgumentEntry] = []

        # Explicit @argument entries are authoritative and preserve decorator order.
        for staged in staged_args:
            param = params_by_name[staged.name]
            annotation = self._resolve_annotation(staged.arg_type, param.annotation)
            required, default = self._resolve_requirement(
                annotation=annotation,
                param_has_default=param.has_default,
                param_default=param.default,
                explicit_default=staged.default,
            )
            ordered.append(
                ArgumentEntry(
                    name=staged.name,
                    type=annotation,
                    help_text=staged.help_text,
                    required=required,
                    default=default,
                )
            )

        # Fallback for undeclared params uses function signature inference.
        for param in params:
            if param.name in explicit_by_name:
                continue

            annotation = self._resolve_annotation(MISSING, param.annotation)
            required, default = self._resolve_requirement(
                annotation=annotation,
                param_has_default=param.has_default,
                param_default=param.default,
                explicit_default=MISSING,
            )
            ordered.append(
                ArgumentEntry(
                    name=param.name,
                    type=annotation,
                    help_text="",
                    required=required,
                    default=default,
                )
            )

        return ordered

    @staticmethod
    def _resolve_annotation(explicit_type: Any, annotation: Any) -> Any:
        if explicit_type is not MISSING:
            return explicit_type
        if annotation is inspect.Parameter.empty:
            return str
        return annotation

    @staticmethod
    def _resolve_requirement(
        *,
        annotation: Any,
        param_has_default: bool,
        param_default: Any,
        explicit_default: Any,
    ) -> tuple[bool, Any]:
        if explicit_default is not MISSING:
            return False, explicit_default

        if param_has_default:
            return False, param_default

        if is_bool_flag(annotation):
            return False, False

        if is_optional(annotation):
            return False, None

        return True, MISSING

    def _suggest(self, token: str) -> str | None:
        candidates = set(self._commands)
        candidates.update(self._aliases)
        candidates.update({HELP_COMMAND_NAME})
        matches = get_close_matches(self._normalize_alias(token), sorted(candidates), n=1)
        if not matches:
            return None

        guess = matches[0]
        if guess in self._aliases:
            return self._aliases[guess]
        return guess

    def suggest(self, token: str) -> str | None:
        """Return the closest known command/alias for *token*, if any."""
        return self._suggest(token)

    @staticmethod
    def _is_builtin_help_token(token: str) -> bool:
        return token in HELP_ALIASES

    @staticmethod
    def _stdin_is_interactive() -> bool:
        isatty = getattr(sys.stdin, "isatty", None)
        if callable(isatty):
            try:
                return bool(isatty())
            except Exception:
                return False
        return False

    @staticmethod
    def _render_argument_type(annotation: Any) -> str:
        if annotation in (inspect.Parameter.empty, Any):
            return "str"
        origin = get_origin(annotation)
        if origin is not None:
            args = ", ".join(
                CommandRegistry._render_argument_type(a) for a in get_args(annotation)
            )
            return f"{origin.__name__}[{args}]"
        return getattr(annotation, "__name__", None) or str(annotation)

    def _render_global_help(self, *, program_name: str | None = None) -> str:
        from functionals.cli.parser import render_command_usage

        prog = program_name or "app.py"
        lines: list[str] = []

        lines += [
            "--------------------------------",
            "Decorates CLI Help",
            "--------------------------------",
            "",
            "Overview",
            "  Build commands with @register, @argument, and @option decorators.",
            "",
            "Usage",
            f"  {prog} <command> [arguments]",
            f"  {prog} {HELP_COMMAND_NAME} [command]",
            f"  {prog} --help | -h",
            f"  {prog} --interactive | -i",
            "",
            "Built-in Commands",
            f"  {HELP_COMMAND_NAME}, --help, -h    Show this menu or help for one command.",
            f"  --interactive, -i               Start interactive REPL mode.",
            "",
        ]

        if not self._commands:
            lines += ["Commands", "  No commands are currently registered."]
            return "\n".join(lines)

        lines.append("Commands")
        for entry in self._commands.values():
            summary = entry.help_text or entry.description or "No description provided."
            aliases = ", ".join(entry.options) if entry.options else "none"
            lines += [
                f"  {entry.name}",
                f"    {summary}",
                f"    Aliases: {aliases}",
                f"    Usage:   {render_command_usage(entry, program_name=prog)}",
            ]

        lines += [
            "",
            f"Tip: run '{prog} {HELP_COMMAND_NAME} <command>' for argument-level details.",
        ]
        return "\n".join(lines)

    def _render_command_help(self, entry: CommandEntry, *, program_name: str | None = None) -> str:
        from functionals.cli.parser import render_command_usage

        prog = program_name or "app.py"
        summary = entry.help_text or entry.description or "No description provided."
        aliases = ", ".join(entry.options) if entry.options else "none"

        lines: list[str] = [
            f"Command: {entry.name}",
            "=" * (9 + len(entry.name)),
            f"Description: {summary}",
            f"Usage: {render_command_usage(entry, program_name=prog)}",
            f"Aliases: {aliases}",
            "",
            "Arguments",
        ]

        if not entry.arguments:
            lines.append("  This command does not accept arguments.")
            return "\n".join(lines)

        for arg in entry.arguments:
            type_name = self._render_argument_type(arg.type)
            qualifier = "required" if arg.required else "optional"
            default   = f", default={arg.default!r}" if arg.default is not MISSING else ""
            help_text = arg.help_text or "No description provided."

            lines += [
                f"  {arg.name} ({type_name}, {qualifier}{default})",
                f"    {help_text}",
                f"    Accepted: {self._render_argument_forms(arg)}",
            ]

        return "\n".join(lines)

    @staticmethod
    def _render_argument_forms(arg: ArgumentEntry) -> str:
        dashed = arg.name.replace("_", "-")
        tokens = [f"--{arg.name}", f"--{dashed}"] if dashed != arg.name else [f"--{arg.name}"]

        if is_bool_flag(arg.type):
            return "flag: " + " or ".join(tokens)

        named = " or ".join(f"{token} VALUE" for token in tokens)
        return f"<{arg.name}> or {named}"

    def _render_builtin_help_detail(self, target: str, *, program_name: str | None = None) -> str:
        prog = program_name or "app.py"

        if target == HELP_COMMAND_NAME:
            name        = "help"
            description = "Show the global help menu or detailed help for one command."
            usage_lines = [f"{prog} help", f"{prog} help <command>", f"{prog} --help", f"{prog} -h"]
        else:
            name        = "interactive"
            description = "Start interactive REPL mode."
            usage_lines = [f"{prog} --interactive", f"{prog} -i"]

        header = f"Built-in Command: {name}"
        lines  = [header, "=" * len(header), "", description, "", "Usage"]
        lines += [f"  {line}" for line in usage_lines]
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._commands)

    def __repr__(self) -> str:
        names = ", ".join(self._commands)
        return f"CommandRegistry([{names}])"
