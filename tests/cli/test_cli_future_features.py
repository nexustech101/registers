from __future__ import annotations

import enum
import json
from pathlib import Path

import pytest

import registers.cli as cli
from registers.cli import Context
from registers.cli import types as t


@pytest.fixture(autouse=True)
def _reset_registry():
    cli.reset_registry()
    yield
    cli.reset_registry()


def _input_from_lines(lines: list[str]):
    iterator = iter(lines)

    def _read(_prompt: str) -> str:
        return next(iterator)

    return _read


def test_grouped_commands_support_longest_match_aliases_and_group_help(capsys):
    registry = cli.CommandRegistry()
    users = registry.group("users", description="User commands", aliases=["u"], tags=["users"])
    deploy = users.group("deploy", description="Deployment commands", aliases=["d"])

    @users.register("list", description="List users", examples=["users list"], tags=["read"])
    def list_users() -> str:
        return "users"

    @deploy.register("service", description="Deploy service")
    @deploy.argument("name", type=str)
    def deploy_service(name: str) -> str:
        return f"deploy:{name}"

    assert registry.run(["users", "list"], print_result=False) == "users"
    assert registry.run(["u", "list"], print_result=False) == "users"
    assert registry.run(["users", "deploy", "service", "api"], print_result=False) == "deploy:api"
    assert registry.run(["u", "d", "service", "api"], print_result=False) == "deploy:api"

    registry.run(["help", "users"], print_result=False)
    out = capsys.readouterr().out
    assert "Command group: users" in out
    assert "users list" in out
    assert "users deploy service" in out

    registry.run(["help", "users", "list"], print_result=False)
    out = capsys.readouterr().out
    assert "Examples" in out
    assert "users list" in out
    assert "Tags" in out


def test_output_modes_render_structured_results(capsys):
    registry = cli.CommandRegistry()

    @registry.register(description="Rows")
    def rows() -> list[dict[str, object]]:
        return [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]

    assert registry.run(["rows", "--output", "json"], print_result=True) == [
        {"id": 1, "name": "Ada"},
        {"id": 2, "name": "Grace"},
    ]
    out = capsys.readouterr().out
    assert json.loads(out) == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]

    registry.run(["rows", "--output", "csv"], print_result=True)
    out = capsys.readouterr().out
    assert "id,name" in out
    assert "1,Ada" in out


def test_command_argument_named_output_wins_over_framework_output_flag(capsys):
    registry = cli.CommandRegistry()

    @registry.register(description="Echo output")
    @registry.argument("output", type=str)
    def echo(output: str) -> str:
        return output

    assert registry.run(["echo", "--output", "value"], print_result=False) == "value"
    registry.run(["echo", "value", "--cli-output", "json"], print_result=True)
    assert json.loads(capsys.readouterr().out) == "value"


def test_extended_types_cover_choices_bounds_paths_dates_lists_json_and_enums(tmp_path: Path):
    registry = cli.CommandRegistry()
    input_file = tmp_path / "input.txt"
    input_file.write_text("ok", encoding="utf-8")

    class Role(enum.Enum):
        admin = "admin"
        member = "member"

    @registry.register(description="Typed")
    @registry.argument("env", type=t.Choice(["dev", "prod"]))
    @registry.argument("count", type=t.Int(min=1, max=5))
    @registry.argument("ratio", type=t.Float(min=0.0, max=1.0))
    @registry.argument("path", type=t.Path(exists=True))
    @registry.argument("day", type=t.Date())
    @registry.argument("tags", type=t.List(str))
    @registry.argument("payload", type=t.JSON)
    @registry.argument("role", type=t.Enum(Role))
    def typed(env, count, ratio, path, day, tags, payload, role):
        return env, count, ratio, path.name, day.isoformat(), tags, payload["ok"], role.value

    assert registry.run(
        [
            "typed",
            "prod",
            "3",
            "0.5",
            str(input_file),
            "2026-05-09",
            "a,b",
            '{"ok": true}',
            "admin",
        ],
        print_result=False,
    ) == ("prod", 3, 0.5, "input.txt", "2026-05-09", ["a", "b"], True, "admin")

    with pytest.raises(SystemExit) as exc:
        registry.run(["typed", "qa"], print_result=False)
    assert exc.value.code == 2


def test_prompt_confirmation_and_dry_run(capsys):
    registry = cli.CommandRegistry()

    @registry.register(description="Create")
    @registry.argument("name", type=str, prompt=True)
    def create(name: str) -> str:
        return f"created:{name}"

    assert registry.run(["create"], print_result=False, shell_input_fn=_input_from_lines(["Ada"])) == "created:Ada"

    @registry.register(description="Drop")
    @registry.argument("db_name", type=str)
    @registry.confirm("Drop {db_name}?", confirm_phrase="drop {db_name}")
    def drop(db_name: str) -> str:
        return f"dropped:{db_name}"

    assert registry.run(
        ["drop", "prod"],
        print_result=False,
        shell_input_fn=_input_from_lines(["drop prod"]),
    ) == "dropped:prod"
    assert registry.run(["drop", "prod", "--force"], print_result=False) == "dropped:prod"

    @registry.register(description="Migrate")
    @registry.dry_run()
    def migrate(dry_run: bool = False) -> bool:
        return dry_run

    assert registry.run(["migrate", "--dry-run"], print_result=False) is True


def test_async_commands_context_and_dispatch_async():
    registry = cli.CommandRegistry()

    class AppContext(Context):
        def __init__(self, env: str) -> None:
            self.env = env

    @registry.context_factory
    def build_context(env: str = "prod") -> AppContext:
        return AppContext(env)

    @registry.register(description="Health")
    async def health(ctx: AppContext) -> dict[str, str]:
        return {"env": ctx.env}

    assert registry.run(["--env", "staging", "health"], print_result=False) == {"env": "staging"}

    @registry.register(description="Echo")
    @registry.argument("value", type=str)
    async def echo(value: str) -> str:
        return value

    assert registry.run(["echo", "ok"], print_result=False) == "ok"

    async def _call() -> str:
        return await registry.run_async(["echo", "async"], print_result=False)

    import asyncio

    assert asyncio.run(_call()) == "async"


def test_shell_watch_and_pipe_builtins(capsys):
    registry = cli.CommandRegistry()

    @registry.register(description="Rows")
    def rows() -> list[dict[str, object]]:
        return [
            {"id": 2, "role": "member"},
            {"id": 1, "role": "admin"},
        ]

    registry.run_shell(
        input_fn=_input_from_lines(
            [
                "watch rows --count 1 --interval 0",
                "pipe rows | filter role=admin | count",
                "quit",
            ]
        ),
        print_result=True,
        banner=False,
        colors=False,
        output="json",
    )

    out = capsys.readouterr().out
    assert '"role": "admin"' in out
    assert "1" in out


def test_public_exports_include_future_helpers():
    assert cli.Theme
    assert cli.Context
    assert cli.console
    assert cli.style
    assert cli.Progress
    assert cli.types.Choice
