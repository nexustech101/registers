# `registers.cli`

Decorator-first CLI runtime for Python applications, operator consoles, plugin surfaces, async workflows, and agent-invokable tools.

`registers.cli` keeps the original small-script ergonomics:

```python
import registers.cli as cli

@cli.register(description="Greet a user")
@cli.argument("name", type=str, help="Name to greet")
@cli.alias("--greet")
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    cli.run()
```

Run:

```bash
python app.py greet Ada
python app.py --greet Ada
python app.py greet --name Ada
```

Expected output:

```text
Hello, Ada!
```

## Install

Core `registers.cli` uses the standard library and existing framework dependencies. Rich and prompt_toolkit are optional presentation extras:

```bash
pip install registers
pip install "registers[cli]"
```

The `cli` extra installs:

- `rich>=15,<16` for styled help, tables, panels, spinners, progress, and structured output.
- `prompt_toolkit>=3.0.52,<4` for optional interactive completion, history, and multiline input.

When optional packages are missing, the runtime falls back to plain text.

## Architecture

Use the module-level facade for one command surface:

```python
import registers.cli as cli
```

Use an explicit registry for tests, plugins, isolated scopes, grouped command surfaces, and embedded runtimes:

```python
from registers import CommandRegistry

registry = CommandRegistry()
```

Both expose the same decorator vocabulary: `register`, `argument`, `option`, `alias`, `group`, `spinner`, `progress`, `confirm`, `dry_run`, and `context_factory`.

## Command Registration

```python
@cli.register(
    name="add",
    description="Add a todo item",
    tags=["todo"],
    examples=['add "Buy milk"', 'add "Buy milk" --description "2%"'],
    deprecated=False,
    render=True,
    default_output=None,
    pager=False,
    error_hints={"TimeoutError": "Check the network and retry."},
    capture_logs=False,
)
@cli.argument("title", type=str, help="Todo title")
@cli.argument("description", type=str, default="", help="Optional description")
@cli.alias("--add")
@cli.alias("-a")
def add(title: str, description: str = "") -> str:
    return f"Added: {title} | {description}"
```

Name rules:

- `name=` wins when provided.
- Otherwise the first long alias becomes the command name, for example `--add` becomes `add`.
- Otherwise the function name is used.

Parsing forms:

```bash
python app.py add "Buy milk" "2%"
python app.py --add "Buy milk" "2%"
python app.py -a --title "Buy milk" --description "2%"
python app.py add "Buy milk" --description "2%"
```

Boolean arguments are flag-style:

```python
@cli.register(description="Run sync")
@cli.argument("verbose", type=bool, default=False)
def run(verbose: bool = False) -> bool:
    return verbose
```

```bash
python app.py run
python app.py run --verbose
```

Duplicate equal values are accepted; duplicate conflicting values fail with exit code `2`.

## Command Groups

Groups create multi-token commands while preserving the same decorators:

```python
from registers import CommandRegistry

registry = CommandRegistry()
users = registry.group("users", description="User commands", aliases=["u"], tags=["users"])
ops = registry.group("ops", description="Operational workflows", aliases=["o"])
deploy = ops.group("deploy", aliases=["d"])

@users.register("list", description="List users", examples=["users list"])
def list_users() -> list[dict]:
    return [{"id": 1, "email": "ada@example.com"}]

@deploy.register("service", description="Deploy a service")
@deploy.argument("name", type=str)
def deploy_service(name: str) -> str:
    return f"deployed:{name}"
```

Run:

```bash
python app.py users list
python app.py u list
python app.py ops deploy service api
python app.py o d service api
python app.py help users
python app.py help users list
```

The resolver uses longest-match command lookup, so flat commands and grouped commands can coexist safely.

## Extended Types

Use `registers.cli.types` for validated parsing:

```python
from pathlib import Path
import registers.cli as cli
from registers.cli import types as t

@cli.register(description="Process records")
@cli.argument("input", type=t.Path(exists=True, readable=True), help="Input file")
@cli.argument("count", type=t.Int(min=1, max=500), default=100)
@cli.argument("ratio", type=t.Float(min=0.0, max=1.0), default=1.0)
@cli.argument("env", type=t.Choice(["dev", "staging", "prod"]), default="dev")
@cli.argument("day", type=t.Date("%Y-%m-%d"))
@cli.argument("tags", type=t.List(str), default=[])
@cli.argument("config", type=t.JSON, default={})
def process(input: Path, count: int, ratio: float, env: str, day, tags: list[str], config: dict) -> dict:
    return {"input": input.name, "count": count, "env": env}
```

Available helpers:

- `Choice([...])`
- `Path(exists=False, readable=False, writable=False)`
- `Int(min=None, max=None)`
- `Float(min=None, max=None)`
- `Date(fmt="%Y-%m-%d")`
- `List(item_type=str, separator=",")`
- `JSON`
- `Enum(MyEnum)`

Invalid values raise parse errors and exit with status code `2`.

## Prompts And Safety Gates

Prompt for missing values only when interactive input is available:

```python
@cli.register(description="Create user")
@cli.argument("email", type=str)
@cli.argument("password", type=str, prompt=True, secret=True, confirm=True)
def create_user(email: str, password: str) -> str:
    return f"created:{email}"
```

Require command confirmation:

```python
@cli.register(description="Drop database", tags=["danger"])
@cli.argument("db_name", type=str)
@cli.confirm(
    "This will permanently drop {db_name}.",
    danger=True,
    confirm_phrase="drop {db_name}",
)
def drop_database(db_name: str) -> str:
    return f"dropped:{db_name}"
```

Run:

```bash
python app.py drop-database prod
python app.py drop-database prod --force
```

Dry-run flags are decorator-driven:

```python
@cli.register(description="Migrate users")
@cli.dry_run()
def migrate_users(dry_run: bool = False) -> str:
    if dry_run:
        return "[dry-run] Would migrate users."
    return "Migration complete."
```

```bash
python app.py migrate-users --dry-run
```

## Async Commands

Async handlers run transparently from sync CLIs:

```python
@cli.register(description="Fetch user")
@cli.argument("user_id", type=int)
async def fetch_user(user_id: int) -> dict:
    return {"id": user_id}

if __name__ == "__main__":
    cli.run()
```

For an already-async caller, use `run_async`:

```python
result = await cli.run_async(["fetch-user", "1"], print_result=False)
```

Explicit dispatch also has an async path:

```python
result = await registry.dispatch_async("fetch-user", {"user_id": 1})
```

## Context Injection

Context factories build session/run-level state once and inject it into commands by `ctx`, `context`, or type annotation.

```python
from registers.cli import Context

class AppContext(Context):
    def __init__(self, env: str) -> None:
        self.env = env

registry = cli.CommandRegistry()

@registry.context_factory
def build_context(env: str = "prod") -> AppContext:
    return AppContext(env)

@registry.register(description="Health")
async def health(ctx: AppContext) -> dict:
    return {"env": ctx.env, "status": "ok"}
```

Run:

```bash
python app.py --env staging health
```

The `--env` flag is consumed by the context factory, not by the command handler.

## Output Modes

Default output preserves backward-compatible `str(result)` behavior. Opt into structured output with runtime flags:

```bash
python app.py users list --output json
python app.py users list --output csv
python app.py users list --output rich
python app.py users list --output plain
python app.py users list --quiet
python app.py users list --no-color
```

Framework-reserved aliases are available when a command owns the same argument name:

```bash
python app.py export --output report.csv
python app.py export --output report.csv --cli-output json
```

Rendering rules:

- `str`: unchanged in plain mode.
- `dict`: JSON, key/value table, or plain key/value lines.
- `list[dict]`: JSON, CSV, Rich table, or plain table.
- `list[str]`: JSON or bullet/plain lines.
- Rich renderables: passed to Rich when available.
- `None`: prints nothing.

Per-command defaults:

```python
@cli.register(description="Export users", default_output="csv")
def export_users() -> list[dict]:
    return [{"id": 1, "email": "ada@example.com"}]
```

## Rich, Progress, And Logging

Enable Rich at runtime:

```python
registry.run(
    rich=True,
    theme="default",
    shell_title="Control Plane",
    shell_description="Operate account workflows.",
)
```

Use spinners and progress decorators:

```python
@cli.register(description="Sync records")
@cli.spinner("Syncing records...")
def sync_records() -> str:
    return "Sync complete."

@cli.register(description="Process records")
@cli.progress("Processing records")
def process_records(progress) -> str:
    task = progress.add_task("Processing", total=2)
    progress.advance(task)
    progress.advance(task)
    return "Processed."
```

Capture command logs:

```python
@cli.register(description="Sync", capture_logs=True)
def sync() -> str:
    logger.warning("retrying")
    return "done"

registry.run(["sync"], log_level="WARNING", log_panel=True)
```

## Interactive Shell

Interactive mode starts when no argv is passed and stdin is a TTY, or explicitly:

```bash
python app.py --interactive
python app.py -i
```

Shell built-ins:

- `help`
- `help <command>`
- `commands`
- `exec <shell command>`
- `watch <command> --interval 5 --count 3`
- `pipe <command> | filter FIELD=VALUE | sort FIELD | count`
- `exit` / `quit`

Runtime configuration:

```python
registry.run(
    ["--interactive"],
    shell_title="Admin Console",
    shell_description="Operate production workflows.",
    shell_banner=True,
    shell_usage=True,
    completion=True,
    history=True,
    multiline=True,
    rich=True,
)
```

The prompt_toolkit features activate only when prompt_toolkit is installed and builtin input is used.

## Plugins

Discovery loading:

```python
registry = cli.CommandRegistry()
registry.load_plugins("app.plugins")
registry.run()
```

Explicit composition:

```python
from app.plugins.users import cli as users_cli
from app.plugins.ops import cli as ops_cli

registry = cli.CommandRegistry()
registry.register_plugin(users_cli)
registry.register_plugin(ops_cli)
registry.run()
```

Duplicate command names or aliases fail during registration; no silent overwrite occurs.

## DI And Middleware

Explicit dispatch remains available for service injection and non-argv runtimes:

```python
container = cli.DIContainer()
container.register(UserService, UserService())

result = registry.dispatch(
    "create-user",
    {"email": "ada@example.com"},
    container=container,
)
```

Middleware hooks still run through `MiddlewareChain`.

## Error Model

- Registration-time duplicate names and aliases raise `DuplicateCommandError`.
- Reserved built-ins such as `help`, `--help`, `-h`, `--interactive`, and `-i` are rejected.
- Parse errors print a message, print usage, and exit with status `2`.
- Unknown commands suggest the closest command or alias when possible.
- Unexpected handler failures are wrapped as `CommandExecutionError`.
- Framework errors preserve structured context through `to_dict()`.

## Public API Index

Module-level:

- `register`, `argument`, `option`, `alias`
- `group`, `spinner`, `progress`, `confirm`, `dry_run`, `context_factory`
- `run`, `run_async`, `run_shell`
- `list_commands`, `get_registry`, `reset_registry`

Registry:

- `CommandRegistry`
- `registry.register`, `registry.argument`, `registry.option`, `registry.alias`
- `registry.group`, `registry.spinner`, `registry.progress`, `registry.confirm`, `registry.dry_run`
- `registry.context_factory`
- `registry.run`, `registry.run_async`, `registry.run_shell`
- `registry.dispatch`, `registry.dispatch_async`
- `registry.load_plugins`, `registry.register_plugin`
- `registry.list_commands`, `registry.print_help`, `registry.has`, `registry.get`, `registry.all`

Runtime helpers:

- `Theme`, `Context`, `console`, `style`, `Progress`
- `types`
- `DIContainer`, `Dispatcher`, `MiddlewareChain`
- `load_plugins`, `parse_command_args`, `ParseError`

Exceptions:

- `RegistrationError`
- `DuplicateCommandError`
- `UnknownCommandError`
- `DependencyNotFoundError`
- `CommandExecutionError`
- `PluginLoadError`

## Production Checklist

- Use explicit `CommandRegistry()` for applications, tests, and plugin hosts.
- Declare public arguments with `@argument(...)`.
- Use groups once command names need hierarchy.
- Prefer `types.*` for validated public inputs.
- Use `--cli-output` when a command owns an `output` argument.
- Keep Rich and prompt_toolkit optional in libraries.
- Test parse errors, output modes, help, group aliases, async handlers, prompts, confirmations, and shell built-ins.
